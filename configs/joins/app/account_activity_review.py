from group_bys.app import email_identity, email_request_activity
from sources.app.user_identity import email_profile_requests

from ai.chronon.types import Derivation, Join, JoinPart


last_visit_age_ms = "GREATEST(ts - activity_email_hash_visit_ts_last_6d, 0)"


account_activity_review = Join(
    left=email_profile_requests,
    row_ids=[],
    right_parts=[
        JoinPart(group_by=email_identity.email_identity, prefix="identity"),
        JoinPart(group_by=email_request_activity.email_request_activity, prefix="activity"),
    ],
    derivations=[
        Derivation(name="*", expression="*"),
        Derivation(
            name="last_5_hub_requests",
            expression="activity_email_hash_path_last5_6d",
        ),
        Derivation(
            name="last_visit_ts",
            expression="activity_email_hash_visit_ts_last_6d",
        ),
        Derivation(
            name="seconds_since_last_visit",
            expression=(
                "CASE WHEN activity_email_hash_visit_ts_last_6d IS NULL THEN NULL "
                f"ELSE CAST({last_visit_age_ms} / 1000 AS BIGINT) END"
            ),
        ),
        Derivation(
            name="time_since_last_visit",
            expression=(
                "CASE WHEN activity_email_hash_visit_ts_last_6d IS NULL THEN NULL "
                f"WHEN {last_visit_age_ms} < 60000 THEN 'just now' "
                f"WHEN {last_visit_age_ms} < 120000 THEN '1 minute ago' "
                f"WHEN {last_visit_age_ms} < 3600000 THEN "
                f"CONCAT(CAST(FLOOR({last_visit_age_ms} / 60000) AS BIGINT), ' minutes ago') "
                f"WHEN {last_visit_age_ms} < 7200000 THEN '1 hour ago' "
                f"WHEN {last_visit_age_ms} < 86400000 THEN "
                f"CONCAT(CAST(FLOOR({last_visit_age_ms} / 3600000) AS BIGINT), ' hours ago') "
                f"WHEN {last_visit_age_ms} < 172800000 THEN '1 day ago' "
                f"ELSE CONCAT(CAST(FLOOR({last_visit_age_ms} / 86400000) AS BIGINT), ' days ago') END"
            ),
        ),
        Derivation(
            name="has_recent_activity",
            expression=(
                "CASE WHEN activity_email_hash_request_count_sum_1d > 0 "
                "THEN 1 ELSE 0 END"
            ),
        ),
        Derivation(
            name="ip_velocity_flag",
            expression=(
                "CASE WHEN activity_email_hash_client_ip_approx_unique_count_1d >= 3 "
                "THEN 1 ELSE 0 END"
            ),
        ),
    ],
    online=True,
    check_consistency=True,
    consistency_sample_percent=100.0,
    enable_stats_compute=True,
    output_namespace="public_demo_data",
    version=7,
    step_days=14,
)
