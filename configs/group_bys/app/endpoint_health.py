from sources.app.ui_logs import access_logs

from ai.chronon.types import Accuracy, Aggregation, GroupBy, Operation


freshness_windows = ["1d"]


endpoint_health = GroupBy(
    sources=[access_logs],
    keys=["route_family"],
    online=True,
    accuracy=Accuracy.SNAPSHOT,
    aggregations=[
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="success_event", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="client_error_event", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="server_error_event", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="not_found_event", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="write_event", operation=Operation.SUM, windows=freshness_windows),
        Aggregation(input_column="request_time_seconds", operation=Operation.AVERAGE, windows=freshness_windows),
        Aggregation(input_column="request_time_seconds", operation=Operation.MAX, windows=freshness_windows),
        Aggregation(input_column="freshness_lag_seconds", operation=Operation.LAST),
        Aggregation(input_column="freshness_lag_seconds", operation=Operation.MAX, windows=freshness_windows),
        Aggregation(input_column="access_event_struct", operation=Operation.LAST_K(10)),
    ],
    version=4,
)
