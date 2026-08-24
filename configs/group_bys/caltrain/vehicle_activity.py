from sources.caltrain.realtime import vehicle_positions

from ai.chronon.types import Aggregation, GroupBy, Operation, TimeUnit, Window


daily_windows = [
    Window(length=1, time_unit=TimeUnit.DAYS),
    Window(length=7, time_unit=TimeUnit.DAYS),
]


vehicle_activity_by_route = GroupBy(
    sources=[vehicle_positions],
    keys=["route_id"],
    online=True,
    aggregations=[
        Aggregation(
            input_column="vehicle_id",
            operation=Operation.COUNT,
            windows=daily_windows,
        ),
        Aggregation(
            input_column="speed",
            operation=Operation.AVERAGE,
            windows=daily_windows,
        ),
        Aggregation(
            input_column="stop_id",
            operation=Operation.LAST_K(5),
        ),
    ],
    version=0,
)
