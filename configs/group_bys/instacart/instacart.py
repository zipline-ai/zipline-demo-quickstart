"""Offline shopper-product, shopper, and product history for next-basket prediction.

Purchase times are BIGINT epoch milliseconds computed by the purchases staging
query. Only prior baskets enter these features. Counts span 7, 14, 45, 90, and
365 days; rates, distinct counts, and recency use the 365-day window.
"""

from staging_queries.instacart import instacart

from ai.chronon.types import (
    Aggregation,
    EventSource,
    GroupBy,
    Operation,
    Query,
    TimeUnit,
    Window,
    selects,
)

_WINDOWS = [Window(length=days, time_unit=TimeUnit.DAYS) for days in [7, 14, 45, 90, 365]]
_LONG = [Window(length=365, time_unit=TimeUnit.DAYS)]

def _source(**extra):
    return EventSource(
        table=instacart.purchases.table,
        query=Query(
            selects=selects(
                user_id="user_id",
                product_id="product_id",
                order_id="order_id",
                add_to_cart_order="add_to_cart_order",
                reordered="reordered",
                purchased_at_ms="purchased_at_ms",
                item="product_id",
                **extra,
            ),
            time_column="purchased_at_ms",
        ),
    )

user_product = GroupBy(
    sources=[_source()],
    keys=["user_id", "product_id"],
    aggregations=[
        Aggregation(input_column="order_id", operation=Operation.COUNT, windows=_WINDOWS),
        Aggregation(input_column="add_to_cart_order", operation=Operation.AVERAGE, windows=_LONG),
        Aggregation(input_column="reordered", operation=Operation.AVERAGE, windows=_LONG),
        Aggregation(input_column="purchased_at_ms", operation=Operation.MAX, windows=_LONG),
    ],
    online=False,
    offline_schedule="@never",
    output_namespace="public_demo_data",
    version=1,
)

user = GroupBy(
    sources=[_source()],
    keys=["user_id"],
    aggregations=[
        Aggregation(input_column="order_id", operation=Operation.APPROX_UNIQUE_COUNT, windows=_WINDOWS),
        Aggregation(input_column="item", operation=Operation.APPROX_UNIQUE_COUNT, windows=_LONG),
        Aggregation(input_column="item", operation=Operation.COUNT, windows=_LONG),
        Aggregation(input_column="reordered", operation=Operation.AVERAGE, windows=_LONG),
    ],
    online=False,
    offline_schedule="@never",
    output_namespace="public_demo_data",
    version=1,
)

product = GroupBy(
    sources=[_source()],
    keys=["product_id"],
    aggregations=[
        Aggregation(input_column="user_id", operation=Operation.COUNT, windows=_LONG),
        Aggregation(input_column="user_id", operation=Operation.APPROX_UNIQUE_COUNT, windows=_LONG),
        Aggregation(input_column="reordered", operation=Operation.AVERAGE, windows=_LONG),
        Aggregation(input_column="add_to_cart_order", operation=Operation.AVERAGE, windows=_LONG),
    ],
    online=False,
    offline_schedule="@never",
    output_namespace="public_demo_data",
    version=1,
)
