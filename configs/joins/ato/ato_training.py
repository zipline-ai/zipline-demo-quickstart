"""Session-level ATO training set: one row per session, scored when it closes.

Features are read 1 ms after a session's last request, so they include the
session's own requests and all earlier history. The left side carries the
``is_ato`` label and the ``scenario`` ground truth; neither is a model feature.

Derivations add the hand-written rules used by the rules baseline, plus the
novelty and session-context signals the XGBoost variants learn from.
"""

from group_bys.ato import ato_features
from staging_queries.ato import ato_data

from ai.chronon.types import ConfigProperties, Derivation, EventSource, Join, JoinPart, Query, selects

_left = EventSource(
    table=ato_data.sessions.table,
    query=Query(
        selects=selects(
            "session_id",
            "account_id",
            "client_ip",
            "user_agent",
            "session_start_ts",
            "session_requests",
            "scenario",
            "is_ato",
        ),
        time_column="session_end_ts + 1",
    ),
)

_HOUR_MS = "3600000D"

_ip_age_hours = f"(ts - account_id_client_ip_seen_at_ms_min_14d) / {_HOUR_MS}"
_agent_age_hours = f"(ts - account_id_user_agent_seen_at_ms_min_14d) / {_HOUR_MS}"
_automation_agent = (
    "LOWER(user_agent) RLIKE 'python|curl|wget|go-http|httpx|okhttp|java/|libwww|scrapy|bot'"
)

_account_age_hours = f"(ts - account_id_seen_at_ms_min_14d) / {_HOUR_MS}"

# A typical hand-tuned ATO rule set. Each rule targets one attack pattern.
_RULES = {
    # An account older than a day appears from an IP and a device it has never used.
    "rule_new_ip_and_device": (
        f"{_account_age_hours} >= 24 AND {_ip_age_hours} < 1 AND {_agent_age_hours} < 1"
    ),
    # Repeated failed logins within the hour: password guessing or stuffing.
    "rule_auth_failures": "account_id_auth_failure_event_sum_1h >= 3",
    # A script changed something on the account.
    "rule_scripted_writes": f"{_automation_agent} AND account_id_write_event_sum_1h >= 1",
    # The IP has served several different accounts this week.
    "rule_shared_ip": "client_ip_account_id_approx_unique_count_7d >= 3",
}


def _flag(condition):
    # A rule whose inputs are missing does not fire.
    return f"CAST(COALESCE({condition}, FALSE) AS INT)"


v1 = Join(
    left=_left,
    row_ids=["session_id"],
    right_parts=[
        JoinPart(group_by=ato_features.account),
        JoinPart(group_by=ato_features.account_ip),
        JoinPart(group_by=ato_features.account_user_agent),
        JoinPart(group_by=ato_features.ip),
    ],
    derivations=[
        Derivation(name="*", expression="*"),
        Derivation(name="hours_since_ip_first_seen", expression=_ip_age_hours),
        Derivation(name="hours_since_agent_first_seen", expression=_agent_age_hours),
        Derivation(name="account_age_hours", expression=_account_age_hours),
        Derivation(
            name="prior_account_requests_7d",
            expression="account_id_request_count_sum_7d - account_id_request_count_sum_1h",
        ),
        Derivation(
            name="session_write_share",
            expression="account_id_write_event_sum_1h / NULLIF(account_id_request_count_sum_1h, 0)",
        ),
        Derivation(
            name="session_requests_per_minute",
            expression="session_requests * 60000D / GREATEST(ts - session_start_ts, 60000)",
        ),
        Derivation(name="session_hour_utc", expression="CAST(PMOD(ts DIV 3600000, 24) AS INT)"),
        Derivation(name="is_automation_agent", expression=f"CAST({_automation_agent} AS INT)"),
        *[Derivation(name=name, expression=_flag(rule)) for name, rule in _RULES.items()],
        Derivation(
            name="rule_score",
            expression=" + ".join(_flag(rule) for rule in _RULES.values()),
        ),
    ],
    online=False,
    offline_schedule="@never",
    enable_stats_compute=True,
    conf=ConfigProperties(common={"spark.sql.session.timeZone": "UTC"}),
    output_namespace="public_demo_data",
    version=1,
)
