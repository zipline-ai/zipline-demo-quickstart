"""Fold-1 test predictions: final fold-1 checkpoint, all 299,984 test rows."""

import json
from pathlib import Path
from ai.chronon.types import (
    ConfigProperties,
    EnvironmentVariables,
    ExecutionInfo,
    EntitySource,
    InferenceSpec,
    Model,
    ModelBackend,
    Query,
    ResourceConfig,
    TrainingSpec,
    Window,
    TimeUnit,
)

artifacts = json.loads(
    (Path(__file__).resolve().parents[3] / "manifests/artifacts-testscore-f1.json").read_text()
)
testscore = Model(
    version=artifacts["trainer_code_version"],
    environments=["prod"],
    inference_spec=InferenceSpec(
        model_backend=ModelBackend.RAY,
        model_backend_params={"model_name": "s6e11_gpt2_testscore_f1", "model_type": "custom"},
    ),
    model_artifact_base_uri="s3://zipline-artifacts-crucible/gpt2-s6e11",
    training_conf=TrainingSpec(
        # Real unpartitioned external CSV, registered in existing Glue database.
        # No event clock, feature pipeline, or synthetic partition is introduced.
        training_data_source=EntitySource(
            snapshot_table="data.s6e11_gpt2_train_87eaa10b", query=Query()
        ),
        training_data_window=Window(length=0, time_unit=TimeUnit.DAYS),
        schedule="@never",
        image=artifacts["training_image"],
        python_module="trainer.score_test",
        resource_config=ResourceConfig(min_replica_count=1, max_replica_count=1),
        job_configs={
            "trainer-manifest-uri": artifacts["trainer_manifest_uri"],
            "trainer-manifest-sha256": artifacts["trainer_manifest_sha256"],
        },
    ),
)

# Scoring only: the parent attempt is the fold-1 run that wrote the checkpoint.
testscore.metaData.executionInfo = ExecutionInfo(
    conf=ConfigProperties(common={"ray.timeout.seconds": "151200"}),
    env=EnvironmentVariables(
        common={"ZIPLINE_PARENT_ATTEMPT_ID": "a404bc49-01db-4a84-9ff2-9038d4b0ceb4-1"}
    ),
)
