from ai.chronon.types import EntitySource, Query, selects


FEATURE_COLUMNS = (
    "ride_id", "pickup_datetime", "pickup_longitude", "dropoff_longitude",
    "pickup_latitude", "dropoff_latitude", "passenger_count", "taxi_id",
    "driver_id", "distance", "pickup_distance_to_jfk", "dropoff_distance_to_jfk",
    "pickup_distance_to_ewr", "dropoff_distance_to_ewr", "pickup_distance_to_lgr",
    "dropoff_distance_to_lgr", "year", "weekday", "hour",
)

benchmark_taxi_snapshots = EntitySource(
    snapshot_table="public_demo_app.featurestore_benchmark_taxi",
    query=Query(selects=selects("id", *FEATURE_COLUMNS)),
)
