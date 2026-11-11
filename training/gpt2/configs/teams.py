"""Isolated local Crucible compile root; repository public-demo defaults stay intact."""

from ai.chronon.types import ConfigProperties, EnvironmentVariables, Team
from ai.chronon.repo.spark_catalog_confs import GlueConfiguration

default = Team(
    description="Local Crucible GPT-2 smoke",
    email="demo@zipline.ai",
    outputNamespace="data",
    conf=ConfigProperties(
        common={
            **GlueConfiguration(
                {
                    "spark.sql.catalog.spark_catalog.warehouse": "s3://zipline-warehouse-crucible/data/tables/"
                }
            ),
            "spark.chronon.table_write.format": "parquet",
            "ray.worker.gpus": "1",
            "ray.worker.cpu": "2",
            "ray.worker.memory": "24Gi",
            "ray.head.cpu": "1",
            "ray.head.memory": "4Gi",
            "ray.worker.shm": "8Gi",
            "ray.worker.ephemeral-storage": "50Gi",
            "ray.placement.profile": "s6e11-l40s",
            "ray.architecture": "amd64",
            "ray.region": "us-west-2",
            "ray.timeout.seconds": "3600",
        }
    ),
    env=EnvironmentVariables(
        common={
            "CUSTOMER_ID": "crucible",
            "CLOUD_PROVIDER": "aws",
            "AWS_REGION": "us-west-2",
            "HUB_URL": "http://localhost:3000/services/hub",
            "FRONTEND_URL": "http://localhost:3000",
            "EVAL_URL": "http://localhost:3904",
            "ARTIFACT_PREFIX": "s3://zipline-artifacts-crucible/gpt2-s6e11",
            "WAREHOUSE_PREFIX": "s3://zipline-warehouse-crucible",
            "VERSION": "latest",
            "ZIPLINE_TRAINING_OBSERVABILITY": "v1",
            "ZIPLINE_DATASET_MANIFEST_HASH": "802675cfd652bea99179b2f47402f906d581969773e3f57e6defca4689fc32ea",
            "ZIPLINE_SPLIT_MANIFEST_HASH": "d6d82738950e9a4b5984910934fd2e526ece481603358f8cb8b017585affd6a1",
        }
    ),
)
