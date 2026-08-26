from ai.chronon.types import ConfigProperties, EngineType, StagingQuery


v1 = StagingQuery(
    setups=[
        """
        CREATE OR REPLACE TEMPORARY VIEW schedule_files_flat
        USING json
        OPTIONS (path 's3a://zipline-public-demo-caltrain-curated/caltrain/schedules/_files_flat/')
        """
    ],
    query="""
    SELECT
        file_name,
        row_count,
        content_sha256,
        CAST(
            unix_timestamp(downloaded_at, "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX") * 1000
            AS BIGINT
        ) AS downloaded_at,
        downloaded_at AS downloaded_at_iso,
        snapshot_date,
        snapshot_hour,
        snapshot_date AS ds
    FROM schedule_files_flat
    WHERE snapshot_date BETWEEN {{ start_date }} AND {{ end_date }}
    """,
    output_namespace="public_demo_data",
    engine_type=EngineType.SPARK,
    dependencies=[],
    conf=ConfigProperties(common={"spark.chronon.partition.column": "snapshot_date"}),
    version=8,
    step_days=1,
)
