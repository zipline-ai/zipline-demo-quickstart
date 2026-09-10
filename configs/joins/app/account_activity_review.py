from group_bys.app import email_identity, email_request_activity
from sources.app.user_identity import email_profile_requests

from ai.chronon.types import Derivation, Join, JoinPart


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
    version=4,
    step_days=14,
)
