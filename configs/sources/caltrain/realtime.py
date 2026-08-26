from ai.chronon.types import EventSource, Query, selects
from staging_queries.caltrain import schedule_files_import


vehicle_positions = EventSource(
    table="public_demo_caltrain.vehicle_positions",
    query=Query(
        selects=selects(
            "payload",
            "snapshot_date",
            "snapshot_hour",
        ),
        time_column="snapshot_date",
        partition_column="ds",
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
        partition_column="snapshot_date",
        start_partition="2026-08-25",
    ),
)


schedule_files = EventSource(
    table=schedule_files_import.v1.table,
    query=Query(
        selects=selects(
            "file_name",
            "row_count",
            "content_sha256",
            "downloaded_at",
            "downloaded_at_iso",
            "snapshot_date",
            "snapshot_hour",
        ),
        time_column="downloaded_at",
        partition_column="snapshot_date",
        start_partition="2026-08-25",
    ),
)
