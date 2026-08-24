from ai.chronon.repo.constants import RunMode
from ai.chronon.types import ConfigProperties, EnvironmentVariables, Team

default = Team(
    description="Default team",
    email="you@example.com",
    outputNamespace="data",
    conf=ConfigProperties(
        common={
            "spark.chronon.table_write.format": "iceberg",
            "spark.chronon.partition.column": "ds",
            "spark.chronon.partition.format": "yyyy-MM-dd",
            "spark.chronon.table.format_provider.class": "ai.chronon.integrations.cloud_gcp.GcpFormatProvider",
            "spark.chronon.cloud_provider": "gcp",
            "spark.sql.catalog.spark_catalog.warehouse": "gs://zipline-warehouse-canary/data/tables/",
            "spark.sql.catalog.default_iceberg.warehouse": "gs://zipline-warehouse-canary/data/tables/",
            "spark.chronon.table_write.prefix": "gs://zipline-warehouse-canary/data/tables/",
        },
    ),
    env=EnvironmentVariables(
        common={
            "CUSTOMER_ID": "canary",
            "GCP_PROJECT_ID": "canary-443022",
            "GCP_REGION": "us-central1",
            "GCP_BIGTABLE_INSTANCE_ID": "zipline-canary-instance",
            "ARTIFACT_PREFIX": "gs://zipline-artifacts-canary",
            "WAREHOUSE_PREFIX": "gs://zipline-warehouse-canary",
            "CLOUD_PROVIDER": "gcp",
            "VERSION": "latest",
            "FLINK_STATE_URI": "gs://zipline-warehouse-canary/flink-state",
        },
        modeEnvironments={
            RunMode.BACKFILL: {},
            RunMode.UPLOAD: {},
            RunMode.STREAMING: {},
        },
    ),
)

caltrain = Team(
    description="Caltrain test team",
    email="you@example.com",
    outputNamespace="data",
    env=EnvironmentVariables(
        common={},
        modeEnvironments={
            RunMode.BACKFILL: {},
            RunMode.UPLOAD: {},
            RunMode.STREAMING: {},
        },
    ),
)
