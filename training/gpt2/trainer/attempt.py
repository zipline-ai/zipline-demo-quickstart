"""Platform #1461 training-v1 publication, owned by the single GPU task."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from .storage import read_bytes, upload, write_json

IDENTITIES = (
    "trial_id",
    "experiment_id",
    "workflow_id",
    "step_id",
    "attempt_id",
    "conf_hash",
    "dataset_manifest_hash",
    "split_manifest_hash",
    "model_conf_name",
)


def context_from_env(model_dir):
    uri = os.environ["ZIPLINE_RUN_CONTEXT_URI"]  # No legacy/shared-output fallback.
    context = json.loads(read_bytes(uri))
    if context.get("schema_version") != 1 or any(
        not context.get(k) for k in IDENTITIES
    ):
        raise ValueError("Invalid run context")
    for key in (
        "trial_id",
        "experiment_id",
        "workflow_id",
        "step_id",
        "attempt_id",
        "artifact_root",
    ):
        if os.environ["ZIPLINE_" + key.upper()].rstrip("/") != context[key].rstrip("/"):
            raise ValueError("Environment/context identity mismatch: " + key)
    root = context["artifact_root"]
    if model_dir.rstrip("/") != root.rstrip("/") or not root.startswith(
        "s3://zipline-artifacts-crucible/gpt2-s6e11/runs/"
    ):
        raise ValueError("Unexpected or conflicting attempt root")
    if not root.endswith(
        f"/{context['workflow_id']}/{context['step_id']}/{context['attempt_id'].rsplit('-', 1)[-1]}/"
    ):
        raise ValueError("Attempt root does not match identity")
    return context


class Publisher:
    def __init__(self, context, local):
        self.context, self.local = context, Path(local)
        self.root = context["artifact_root"].rstrip("/") + "/"
        self.sequence, self.last = 0, 0.0
        self.checkpoint = None

    def artifact(self, path, relative):
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("Invalid artifact path")
        upload(path, self.root + relative, immutable=True)
        return relative

    def progress(self, phase, force=False, **values):
        if not force and time.monotonic() - self.last < 20:
            return
        self.sequence += 1
        record = {
            "attempt_id": self.context["attempt_id"],
            "sequence": self.sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            **values,
        }
        if self.checkpoint:
            record["checkpoint"] = self.checkpoint
        batch = {
            "schema_version": 1,
            "attempt_id": self.context["attempt_id"],
            "sequence": self.sequence,
            "records": [record],
        }
        path = self.local / "progress.json"
        write_json(path, batch)
        if path.stat().st_size > 8192:
            raise ValueError("Progress record too large")
        upload(path, self.root + f"progress/{self.sequence:012d}.json", immutable=True)
        write_json(
            path, {k: batch[k] for k in ("schema_version", "attempt_id", "sequence")}
        )
        upload(path, self.root + "progress/latest.json")
        self.last = time.monotonic()

    def checkpoint_saved(self, path, stage, step):
        self.checkpoint = self.artifact(path, f"checkpoints/{stage}-{step:08d}.pt")
        # Accompany the checkpoint with its exact training recipe so a new attempt
        # can explicitly resume it without writing into the parent's root.
        self.artifact(self.local / "resume_config.json", self.checkpoint + ".json")
        self.progress(stage, force=True, step=step)

    def report(self, metrics, scope, artifacts):
        result = {k: self.context[k] for k in IDENTITIES}
        result.update(
            schema_version=1,
            complete=True,
            evaluation_scope=scope,
            metrics=metrics,
            artifacts=artifacts,
        )
        path = self.local / "experiment_report.json"
        write_json(path, result)
        upload(path, self.root + path.name, immutable=True)
