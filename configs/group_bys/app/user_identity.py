from sources.app.user_identity import user_identity_snapshots

from ai.chronon.types import Accuracy, GroupBy


user_identity = GroupBy(
    sources=[user_identity_snapshots],
    keys=["user_id"],
    online=True,
    accuracy=Accuracy.SNAPSHOT,
    aggregations=None,
    version=2,
    step_days=1,
)
