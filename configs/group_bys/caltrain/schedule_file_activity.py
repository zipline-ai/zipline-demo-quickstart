from sources.caltrain.realtime import schedule_files

from ai.chronon.types import Aggregation, GroupBy, Operation, TimeUnit, Window


daily_windows = [
    Window(length=1, time_unit=TimeUnit.DAYS),
    Window(length=7, time_unit=TimeUnit.DAYS),
]


schedule_file_activity = GroupBy(
    sources=[schedule_files],
    keys=["file_name"],
    online=True,
    aggregations=[
        Aggregation(
            input_column="content_sha256",
            operation=Operation.COUNT,
            windows=daily_windows,
        ),
        Aggregation(
            input_column="row_count",
            operation=Operation.AVERAGE,
            windows=daily_windows,
        ),
        Aggregation(
            input_column="snapshot_hour",
            operation=Operation.LAST_K(5),
        ),
    ],
    version=16,
)
