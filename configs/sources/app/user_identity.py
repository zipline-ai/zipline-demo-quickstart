from ai.chronon.types import EntitySource, Query, selects


user_identity_snapshots = EntitySource(
    snapshot_table="public_demo_app.app_user_identity_user_identity_snapshots_iceberg__0",
    query=Query(
        selects=selects(
            "user_id",
            "email_hash",
            "first_seen_ts",
            "last_seen_ts",
            "last_seen_time_iso",
            "last_event",
        ),
        start_partition="2026-08-25",
    ),
)
