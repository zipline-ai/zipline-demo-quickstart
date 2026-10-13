"""Stage the Instacart Online Grocery Shopping Dataset 2017 (via Kaggle).

Instacart provides this dataset for non-commercial use. Inputs are static,
unpartitioned Parquet files; see docs/data_sources.md for attribution and schemas.
Calendar dates are reconstructed from real inter-order gaps, anchored at 2026-08-24.
Shopper IDs spread final baskets over seven days so the holdout contains whole
shoppers. Only prior baskets feed history; train baskets provide labels.
"""

from ai.chronon.types import ConfigProperties, EngineType, StagingQuery, TableDependency

_PARQUET = "s3://zipline-public-demo-curated/kaggle_instacart/iceberg"

# Fixed tutorial calendar; the seven label partitions end on this date.
_ANCHOR = "2026-08-24"

_HOLDOUT_SPREAD_DAYS = 7

# Use the full static population.
_SAMPLE_PERCENT = 100
_SAMPLE = f"PMOD(o.user_id, 100) < {_SAMPLE_PERCENT}"

orders = StagingQuery(
    query=f"""
WITH raw AS (
    SELECT
        order_id,
        user_id,
        eval_set,
        order_number,
        order_dow,
        order_hour_of_day,
        COALESCE(days_since_prior_order, 0) AS days_since_prior_order
    FROM parquet.`{_PARQUET}/orders/data/`
),
sequenced AS (
    SELECT
        *,
        SUM(days_since_prior_order) OVER (
            PARTITION BY user_id ORDER BY order_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS days_from_first
    FROM raw
),
spans AS (
    SELECT user_id, MAX(days_from_first) AS total_days FROM sequenced GROUP BY user_id
)
SELECT
    s.order_id,
    s.user_id,
    s.eval_set,
    s.order_number,
    s.order_dow,
    s.order_hour_of_day,
    s.days_since_prior_order,
    DATE_FORMAT(
        DATE_SUB(
            DATE('{_ANCHOR}'),
            CAST(p.total_days - s.days_from_first
                 + PMOD(s.user_id, {_HOLDOUT_SPREAD_DAYS}) AS INT)
        ),
        'yyyy-MM-dd'
    ) AS ds
FROM sequenced s
JOIN spans p ON s.user_id = p.user_id
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    dependencies=[TableDependency(table=f"parquet.`{_PARQUET}/orders/data/`", time_partitioned=False)],
    step_days=3650,
    version=1,
)

products = StagingQuery(
    query=f"""
SELECT
    product_id,
    product_name,
    aisle_id,
    department_id,
    DATE_FORMAT(DATE('{_ANCHOR}'), 'yyyy-MM-dd') AS ds
FROM parquet.`{_PARQUET}/products/data/`
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    dependencies=[TableDependency(table=f"parquet.`{_PARQUET}/products/data/`", time_partitioned=False)],
    version=1,
)

purchases = StagingQuery(
    query=f"""
WITH items AS (
    SELECT
        order_id,
        product_id,
        add_to_cart_order,
        reordered
    FROM parquet.`{_PARQUET}/order_products_prior/data/`
)
SELECT
    o.user_id,
    i.product_id,
    i.order_id,
    i.add_to_cart_order,
    i.reordered,
    o.order_number,
    o.order_dow,
    o.order_hour_of_day,
    -- Midnight plus the hour the basket was placed, in epoch millis, which is what a
    -- temporal join reads.
    UNIX_TIMESTAMP(TO_TIMESTAMP(o.ds, 'yyyy-MM-dd')) * 1000
        + o.order_hour_of_day * 3600000 AS purchased_at_ms,
    o.ds
FROM items i
JOIN {orders.table} o ON i.order_id = o.order_id
WHERE o.eval_set = 'prior'
  AND {_SAMPLE}
  AND o.ds BETWEEN {{{{ start_date }}}} AND {{{{ end_date }}}}
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    dependencies=[
        TableDependency(table=f"parquet.`{_PARQUET}/order_products_prior/data/`", time_partitioned=False),
        TableDependency(table=orders.table, partition_column="ds", start_offset=0, end_offset=0),
    ],
    step_days=400,
    version=1,
)

candidates = StagingQuery(
    query=f"""
WITH train_items AS (
    SELECT
        order_id,
        product_id
    FROM parquet.`{_PARQUET}/order_products_train/data/`
),
next_basket AS (
    SELECT o.user_id, t.product_id, o.ds
    FROM train_items t
    JOIN {orders.table} o ON t.order_id = o.order_id
    WHERE o.eval_set = 'train' AND {_SAMPLE}
),
labelled_users AS (
    SELECT user_id, MAX(ds) AS ds FROM next_basket GROUP BY user_id
),
catalogue AS (
    -- Read all prior baskets, independent of materialized feature history.
    SELECT DISTINCT o.user_id, i.product_id
    FROM parquet.`{_PARQUET}/order_products_prior/data/` i
    JOIN parquet.`{_PARQUET}/orders/data/` o ON i.order_id = o.order_id
    WHERE o.eval_set = 'prior' AND {_SAMPLE}
)
SELECT
    c.user_id,
    c.product_id,
    CONCAT(CAST(c.user_id AS STRING), '-', CAST(c.product_id AS STRING)) AS candidate_id,
    IF(n.product_id IS NOT NULL, 1, 0) AS in_next_basket,
    u.ds
FROM catalogue c
JOIN labelled_users u ON c.user_id = u.user_id
LEFT JOIN next_basket n
       ON n.user_id = c.user_id AND n.product_id = c.product_id
WHERE u.ds BETWEEN {{{{ start_date }}}} AND {{{{ end_date }}}}
""",
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    offline_schedule="@never",
    dependencies=[
        TableDependency(table=orders.table, partition_column="ds", start_offset=0, end_offset=0),
        TableDependency(table=f"parquet.`{_PARQUET}/orders/data/`", time_partitioned=False),
        TableDependency(table=f"parquet.`{_PARQUET}/order_products_prior/data/`", time_partitioned=False),
        TableDependency(table=f"parquet.`{_PARQUET}/order_products_train/data/`", time_partitioned=False),
    ],
    step_days=400,
    version=1,
)
