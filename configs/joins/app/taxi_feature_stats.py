from ai.chronon.types import EntitySource, Join, JoinPart, Query, selects
from group_bys.app.benchmark_taxi import benchmark_taxi
from sources.app.benchmark_taxi import benchmark_taxi_snapshots


# A bounded, offline-only exercise over the 500-ride snapshot on 2026-09-17.
# Start without advanced stats; docs/tutorials/advanced-feature-stats.md adds them.
taxi_feature_stats = Join(
    left=EntitySource(
        snapshot_table=benchmark_taxi_snapshots.entities.snapshotTable,
        query=Query(selects=selects("id")),
    ),
    row_ids=["id"],
    right_parts=[JoinPart(group_by=benchmark_taxi)],
    online=False,
    offline_schedule="@never",
    output_namespace="public_demo_data",
    version=1,
)
