from group_bys.app import email_identity
from sources.app.user_identity import email_profile_requests

from ai.chronon.types import Derivation, Join, JoinPart


email_activity_profile = Join(
    left=email_profile_requests,
    row_ids=[],
    right_parts=[
        JoinPart(group_by=email_identity.email_identity, prefix="profile"),
    ],
    derivations=[
        Derivation(
            name="user_id_suffix",
            expression="profile_email_hash_user_id_suffix",
        ),
        Derivation(name="first_seen_ts", expression="profile_email_hash_first_seen_ts"),
        Derivation(name="last_seen_ts", expression="profile_email_hash_last_seen_ts"),
        Derivation(name="last_seen_time_iso", expression="profile_email_hash_last_seen_time_iso"),
        Derivation(name="last_event", expression="profile_email_hash_last_event"),
        Derivation(
            name="is_returning_user",
            expression=(
                "CASE WHEN profile_email_hash_last_seen_ts > profile_email_hash_first_seen_ts "
                "THEN 1 ELSE 0 END"
            ),
        ),
    ],
    online=True,
    check_consistency=True,
    consistency_sample_percent=100.0,
    enable_stats_compute=True,
    output_namespace="public_demo_data",
    version=2,
)
