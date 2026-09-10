from group_bys.app import user_identity
from sources.app.ui_logs import client_access_logs

from ai.chronon.types import Derivation, Join, JoinPart


user_request_identity = Join(
    left=client_access_logs,
    row_ids=["event_id"],
    right_parts=[
        JoinPart(group_by=user_identity.user_identity, prefix="identity"),
    ],
    derivations=[
        Derivation(name="*", expression="*"),
        Derivation(
            name="has_authenticated_identity",
            expression="CASE WHEN identity_user_id_email_hash IS NOT NULL THEN 1 ELSE 0 END",
        ),
    ],
    online=True,
    check_consistency=True,
    consistency_sample_percent=100.0,
    enable_stats_compute=True,
    output_namespace="public_demo_data",
    version=9,
)
