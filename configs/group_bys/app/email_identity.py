from sources.app.user_identity import email_identity_snapshots

from ai.chronon.types import Accuracy, GroupBy


email_identity = GroupBy(
    sources=[email_identity_snapshots],
    keys=["email_hash"],
    online=True,
    accuracy=Accuracy.SNAPSHOT,
    aggregations=None,
    version=2,
    step_days=7,
)
