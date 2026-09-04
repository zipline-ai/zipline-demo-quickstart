from ai.chronon.repo.constants import RunMode
from ai.chronon.repo.spark_catalog_confs import GlueConfiguration
from ai.chronon.types import ConfigProperties, EnvironmentVariables, Team

PUBLIC_DEMO_NLB = "https://try.zipline.ai"
WAREHOUSE_PREFIX = "s3://zipline-public-demo-warehouse"

default = Team(
    description="Public AWS demo default team",
    email="demo@zipline.ai",
    outputNamespace="public_demo_data",
    conf=ConfigProperties(
        common={
            **GlueConfiguration(
                {
                    "spark.sql.catalog.spark_catalog.warehouse": f"{WAREHOUSE_PREFIX}/data/tables/",
                }
            ),
            "spark.sql.catalog.glue": "org.apache.iceberg.spark.SparkCatalog",
            "spark.sql.catalog.glue.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog",
            "spark.sql.catalog.glue.warehouse": f"{WAREHOUSE_PREFIX}/data/tables/",
            "spark.sql.defaultCatalog": "glue",
            "spark.chronon.table_write.format": "iceberg",
            "spark.chronon.table_write.upload.format": "ion",
            "spark.chronon.table_write.upload.location": f"{WAREHOUSE_PREFIX}/data/ion_uploads/",
            "spark.chronon.partition.column": "ds",
            "spark.chronon.partition.format": "yyyy-MM-dd",
            "spark.chronon.coalesce.factor": "2",
            "spark.default.parallelism": "4",
            "spark.scheduler.maxRegisteredResourcesWaitingTime": "120s",
            "spark.sql.catalogImplementation": "hive",
            "spark.sql.shuffle.partitions": "4",
        },
    ),
    env=EnvironmentVariables(
        common={
            "CUSTOMER_ID": "public-demo",
            "CLOUD_PROVIDER": "aws",
            "AWS_REGION": "us-west-2",
            "ARTIFACT_PREFIX": "s3://zipline-public-demo-artifacts",
            "WAREHOUSE_PREFIX": WAREHOUSE_PREFIX,
            "FLINK_STATE_URI": f"{WAREHOUSE_PREFIX}/flink-state",
            "FRONTEND_URL": PUBLIC_DEMO_NLB,
            "HUB_URL": f"{PUBLIC_DEMO_NLB}/services/hub",
            "EVAL_URL": f"{PUBLIC_DEMO_NLB}/services/eval",
            "FETCHER_URL": f"{PUBLIC_DEMO_NLB}/services/fetcher",
            "VERSION": "latest",
        },
        modeEnvironments={
            RunMode.BACKFILL: {},
            RunMode.UPLOAD: {},
            RunMode.STREAMING: {},
        },
    ),
)

app = Team(
    description="Public demo UI and Hub access-log features",
    email="demo@zipline.ai",
    outputNamespace="public_demo_data",
    env=EnvironmentVariables(
        common={
            "FRONTEND_URL": PUBLIC_DEMO_NLB,
            "HUB_URL": f"{PUBLIC_DEMO_NLB}/services/hub",
            "EVAL_URL": f"{PUBLIC_DEMO_NLB}/services/eval",
            "FETCHER_URL": f"{PUBLIC_DEMO_NLB}/services/fetcher",
        },
        modeEnvironments={
            RunMode.BACKFILL: {},
            RunMode.UPLOAD: {},
            RunMode.STREAMING: {},
        },
    ),
)
