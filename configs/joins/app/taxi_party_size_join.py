from ai.chronon.types import Derivation, EntitySource, Join, JoinPart, Query, selects
from group_bys.app.benchmark_taxi import benchmark_taxi

# Public 500-ride snapshot. A derived signal, keyed by demo ride index.
taxi_party_size = Join(
    left=EntitySource(
        snapshot_table="public_demo_app.featurestore_benchmark_taxi",
        query=Query(selects=selects("id")),
    ),
    row_ids=["id"],
    right_parts=[JoinPart(group_by=benchmark_taxi)],
    derivations=[
        Derivation("passenger_count", "id_passenger_count"),
        Derivation("multi_passenger_ride", "CAST(id_passenger_count > 1 AS INT)"),
    ],
    online=True,
    online_schedule="@never",
    offline_schedule="@never",
    version=1,
)
