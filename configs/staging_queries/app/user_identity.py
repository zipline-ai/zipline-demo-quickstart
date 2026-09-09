from ai.chronon.types import EngineType, StagingQuery


user_identity_snapshots_iceberg = StagingQuery(
    query="""
    SELECT
        user_id,
        email_hash,
        first_seen_ts,
        last_seen_ts,
        last_seen_time_iso,
        last_event,
        source_event_id,
        ingestion_id,
        ingested_at,
        snapshot_date AS ds
    FROM public_demo_app.user_identity_snapshots
    WHERE snapshot_date BETWEEN {{ start_date }} AND {{ end_date }}
    """,
    output_namespace="public_demo_app",
    engine_type=EngineType.SPARK,
    dependencies=[],
    version=0,
    step_days=7,
)
