from sources.app.ui_logs import email_access_logs

from ai.chronon.types import Aggregation, EnvironmentVariables, GroupBy, Operation


activity_windows = ["1d", "6d"]


email_request_activity = GroupBy(
    sources=[email_access_logs],
    keys=["email_hash"],
    online=True,
    aggregations=[
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=activity_windows),
        Aggregation(input_column="error_event", operation=Operation.SUM, windows=activity_windows),
        Aggregation(input_column="write_event", operation=Operation.SUM, windows=activity_windows),
        Aggregation(input_column="client_ip", operation=Operation.APPROX_UNIQUE_COUNT, windows=activity_windows),
        Aggregation(input_column="user_agent", operation=Operation.APPROX_UNIQUE_COUNT, windows=activity_windows),
        Aggregation(input_column="route_family", operation=Operation.APPROX_UNIQUE_COUNT, windows=activity_windows),
        Aggregation(input_column="client_ip", operation=Operation.LAST_K(5), windows=["6d"]),
        Aggregation(input_column="user_agent", operation=Operation.LAST_K(5), windows=["6d"]),
        Aggregation(input_column="path", operation=Operation.LAST_K(5), windows=["6d"]),
        Aggregation(input_column="activity_event", operation=Operation.LAST_K(10), windows=["6d"]),
        Aggregation(input_column="freshness_lag_seconds", operation=Operation.LAST, windows=["6d"]),
        Aggregation(input_column="freshness_lag_seconds", operation=Operation.MAX, windows=["1d"]),
    ],
    version=3,
    step_days=14,
    env_vars=EnvironmentVariables(
        common={
            "CHRONON_ONLINE_ARGS": "-Ztasks=1",
            "ENABLE_KINESIS": "true",
        }
    ),
)
