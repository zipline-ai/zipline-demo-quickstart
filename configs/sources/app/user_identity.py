from ai.chronon.types import EntitySource, Query, selects


user_identity_snapshots = EntitySource(
    snapshot_table="public_demo_app.user_identity_snapshots",
    query=Query(
        selects=selects(
            "user_id",
            "email_hash",
            "first_seen_ts",
            "last_seen_ts",
            "last_seen_time_iso",
            "last_event",
        ),
        partition_column="snapshot_date",
        start_partition="2026-09-02",
    ),
)
