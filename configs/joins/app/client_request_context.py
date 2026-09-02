from group_bys.app import client_activity, endpoint_health
from sources.app.ui_logs import client_access_logs

from ai.chronon.types import Derivation, Join, JoinPart


client_request_context = Join(
    left=client_access_logs,
    row_ids=["event_id"],
    right_parts=[
        JoinPart(group_by=client_activity.client_activity),
        JoinPart(group_by=endpoint_health.endpoint_health),
    ],
    derivations=[
        Derivation(name="*", expression="*"),
        Derivation(
            name="freshness_risk",
            expression=(
                "CASE "
                "WHEN client_ip_freshness_lag_seconds_last > 3600 THEN 'stale' "
                "WHEN client_ip_freshness_lag_seconds_last > 900 THEN 'warming' "
                "ELSE 'fresh' "
                "END"
            ),
        ),
    ],
    online=True,
    check_consistency=True,
    consistency_sample_percent=100.0,
    output_namespace="public_demo_data",
    version=2,
)
