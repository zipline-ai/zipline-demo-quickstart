from group_bys.caltrain.schedule_file_activity import schedule_file_activity

from ai.chronon.types import EventSource, Join, JoinPart, Query, selects


schedule_file_snapshot_events = EventSource(
    table="public_demo_caltrain.schedule_files",
    query=Query(
        selects=selects("file_name", "row_count", "content_sha256", "downloaded_at"),
        time_column="downloaded_at",
        start_partition="2026-08-25",
    ),
)


v1 = Join(
    left=schedule_file_snapshot_events,
    right_parts=[JoinPart(group_by=schedule_file_activity)],
    row_ids=["file_name", "content_sha256"],
    version=0,
)
