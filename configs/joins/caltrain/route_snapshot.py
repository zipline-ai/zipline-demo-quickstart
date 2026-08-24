from group_bys.caltrain.vehicle_activity import vehicle_activity_by_route

from ai.chronon.types import EventSource, Join, JoinPart, Query, selects


route_snapshot_events = EventSource(
    table="public_demo_caltrain_raw.vehicle_positions_raw",
    query=Query(
        selects=selects("route_id", "vehicle_id", "trip_id"),
        time_column="ingested_at",
        start_partition="2026-08-24",
    ),
)


v1 = Join(
    left=route_snapshot_events,
    right_parts=[JoinPart(group_by=vehicle_activity_by_route)],
    row_ids=["route_id", "vehicle_id", "trip_id"],
    version=0,
)
