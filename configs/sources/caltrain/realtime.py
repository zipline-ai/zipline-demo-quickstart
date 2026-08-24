from ai.chronon.types import EventSource, Query, selects


vehicle_positions = EventSource(
    table="public_demo_caltrain_raw.vehicle_positions_raw",
    query=Query(
        selects=selects(
            "vehicle_id",
            "trip_id",
            "route_id",
            "stop_id",
            "current_stop_sequence",
            "latitude",
            "longitude",
            "bearing",
            "speed",
            "occupancy_status",
        ),
        time_column="ingested_at",
        start_partition="2026-08-24",
    ),
)


trip_updates = EventSource(
    table="public_demo_caltrain_raw.trip_updates_raw",
    query=Query(
        selects=selects(
            "vehicle_id",
            "trip_id",
            "route_id",
            "start_date",
            "schedule_relationship",
        ),
        time_column="ingested_at",
        start_partition="2026-08-24",
    ),
)
