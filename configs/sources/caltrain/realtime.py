from ai.chronon.types import EventSource, Query, selects


vehicle_positions = EventSource(
    table="public_demo_caltrain.vehicle_positions",
    query=Query(
        selects=selects(
            "payload",
            "snapshot_date",
            "snapshot_hour",
        ),
        time_column="snapshot_date",
        start_partition="2026-08-25",
    ),
)


trip_updates = EventSource(
    table="public_demo_caltrain.trip_updates",
    query=Query(
        selects=selects(
            "payload",
            "snapshot_date",
            "snapshot_hour",
        ),
        time_column="snapshot_date",
        start_partition="2026-08-25",
    ),
)


schedule_files = EventSource(
    table="public_demo_caltrain.schedule_files",
    query=Query(
        selects=selects(
            "file_name",
            "row_count",
            "content_sha256",
            "downloaded_at",
            "snapshot_date",
            "snapshot_hour",
        ),
        time_column="downloaded_at",
        start_partition="2026-08-25",
    ),
)
