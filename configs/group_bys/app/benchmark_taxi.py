from ai.chronon.types import Accuracy, GroupBy
from sources.app.benchmark_taxi import benchmark_taxi_snapshots


benchmark_taxi = GroupBy(
    sources=[benchmark_taxi_snapshots],
    keys=["id"],
    online=True,
    accuracy=Accuracy.SNAPSHOT,
    aggregations=None,
    online_schedule="@never",
    offline_schedule="@never",
    version=0,
)
