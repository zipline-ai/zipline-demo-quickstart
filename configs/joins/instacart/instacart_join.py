"""Offline next-basket training set, keyed by a unique shopper-product candidate.

Labels use only train baskets; history uses only prior baskets. Features are
read at midnight UTC on each label day, matching the canary's date-based cutoff.
Derivations retain all original features alongside cross-entity ratios.
"""

from group_bys.instacart import instacart as history
from staging_queries.instacart import instacart as tables

from ai.chronon.types import ConfigProperties, Derivation, EventSource, Join, JoinPart, Query, selects

_left = EventSource(
    table=tables.candidates.table,
    query=Query(
        selects=selects(
            user_id="user_id",
            product_id="product_id",
            candidate_id="candidate_id",
            in_next_basket="in_next_basket",
        ),
        time_column="UNIX_TIMESTAMP(TO_TIMESTAMP(ds, 'yyyy-MM-dd')) * 1000",
    ),
)

v1 = Join(
    left=_left,
    row_ids=["candidate_id"],
    right_parts=[
        JoinPart(group_by=history.user_product),
        JoinPart(group_by=history.user),
        JoinPart(group_by=history.product),
    ],
    derivations=[
        Derivation(name="*", expression="*"),
        Derivation(
            name="share_of_orders_with_product",
            expression=(
                "user_id_product_id_order_id_count_365d / "
                "NULLIF(user_id_order_id_approx_unique_count_365d, 0)"
            ),
        ),
        Derivation(
            name="recent_share_of_product_purchases",
            expression=(
                "user_id_product_id_order_id_count_14d / "
                "NULLIF(user_id_product_id_order_id_count_365d, 0)"
            ),
        ),
        Derivation(
            name="days_since_last_purchase",
            expression=(
                "(UNIX_TIMESTAMP(TO_TIMESTAMP(ds, 'yyyy-MM-dd')) * 1000 - "
                "user_id_product_id_purchased_at_ms_max_365d) / 86400000.0"
            ),
        ),
        Derivation(
            name="product_share_of_basket",
            expression=(
                "user_id_product_id_order_id_count_365d / "
                "NULLIF(user_id_item_count_365d, 0)"
            ),
        ),
    ],
    online=False,
    offline_schedule="@never",
    enable_stats_compute=True,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    output_namespace="public_demo_data",
    version=1,
)
