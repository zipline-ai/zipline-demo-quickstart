"""Account-takeover features over real plus simulated demo activity.

All four GroupBys read the ``activity`` staging table, never its ``scenario``
column. They are temporally accurate, so a session scored at its last request
sees every earlier request, including the session's own.

* ``account``: velocity, auth failures, and device/IP spread per account.
* ``account_ip`` and ``account_user_agent``: when this account first used the
  IP or user agent within 14 days. Joined at session close, a first-seen time
  inside the session means the IP or device is new to the account.
* ``ip``: how many accounts and failed logins an IP has served.
"""

from staging_queries.ato import ato_data

from ai.chronon.types import Accuracy, Aggregation, EventSource, GroupBy, Operation, Query, selects

_SHORT = ["1h", "1d", "7d"]
_SPREAD = ["1d", "7d"]
_HISTORY = ["14d"]

_activity = EventSource(
    table=ato_data.activity.table,
    query=Query(
        selects=selects(
            "account_id",
            "client_ip",
            "user_agent",
            request_count="1",
            write_event="IF(http_method IN ('POST', 'PUT', 'PATCH', 'DELETE'), 1, 0)",
            auth_failure_event="IF(status_code IN (401, 403), 1, 0)",
            seen_at_ms="event_ts",
        ),
        time_column="event_ts",
    ),
)


def _group_by(keys, aggregations):
    return GroupBy(
        sources=[_activity],
        keys=keys,
        aggregations=aggregations,
        accuracy=Accuracy.TEMPORAL,
        online=False,
        offline_schedule="@never",
        output_namespace="public_demo_data",
        version=1,
    )


account = _group_by(
    ["account_id"],
    [
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=_SHORT),
        Aggregation(input_column="write_event", operation=Operation.SUM, windows=_SHORT),
        Aggregation(input_column="auth_failure_event", operation=Operation.SUM, windows=_SHORT),
        Aggregation(input_column="client_ip", operation=Operation.APPROX_UNIQUE_COUNT, windows=_SPREAD),
        Aggregation(input_column="user_agent", operation=Operation.APPROX_UNIQUE_COUNT, windows=_SPREAD),
        Aggregation(input_column="seen_at_ms", operation=Operation.MIN, windows=_HISTORY),
    ],
)

account_ip = _group_by(
    ["account_id", "client_ip"],
    [
        Aggregation(input_column="seen_at_ms", operation=Operation.MIN, windows=_HISTORY),
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=_HISTORY),
    ],
)

account_user_agent = _group_by(
    ["account_id", "user_agent"],
    [
        Aggregation(input_column="seen_at_ms", operation=Operation.MIN, windows=_HISTORY),
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=_HISTORY),
    ],
)

ip = _group_by(
    ["client_ip"],
    [
        Aggregation(input_column="account_id", operation=Operation.APPROX_UNIQUE_COUNT, windows=_SPREAD),
        Aggregation(input_column="auth_failure_event", operation=Operation.SUM, windows=_SPREAD),
        Aggregation(input_column="request_count", operation=Operation.SUM, windows=["1d"]),
    ],
)
