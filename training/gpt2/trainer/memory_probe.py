"""Bounded fold-0 memory probe using the production loader, encoders and math."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .attempt import Publisher, context_from_env
from .data import REVISION, load
from .storage import fingerprint, read_bytes, write_json


def cgroup_memory():
    """Kernel peaks include Ray processes and transient tokenizer/checkpoint memory."""
    paths = {
        "current_bytes": ["memory.current", "memory/memory.usage_in_bytes"],
        "peak_bytes": ["memory.peak", "memory/memory.max_usage_in_bytes"],
        "limit_bytes": ["memory.max", "memory/memory.limit_in_bytes"],
    }
    result = {}
    for key, candidates in paths.items():
        for relative in candidates:
            path = Path("/sys/fs/cgroup") / relative
            if path.exists():
                value = path.read_text().strip()
                result[key] = int(value) if value != "max" else None
                break
    events = Path("/sys/fs/cgroup/memory.events")
    if events.exists():
        result["events"] = dict((k, int(v)) for k, v in
                                (line.split() for line in events.read_text().splitlines()))
    return result


def longest_rows(encoder, count, source=False):
    """Upper-bound row lengths across feature orders without materializing sequences."""
    lengths = np.zeros(len(encoder.frame), dtype=np.int32)
    for codes, plain, first, later in encoder.tables:
        sizes = np.maximum.reduce([np.array([len(x) for x in variants], dtype=np.int32)
                                   for variants in (plain, first, later)])
        lengths += sizes[codes]
    lengths += (max(len(x) for variants in encoder.target.values() for x in variants)
                if source else max(map(len, encoder.prefix))) + 1
    count = min(count, len(lengths))
    indices = np.argsort(lengths, kind="stable")[-count:][::-1].copy()
    return indices, int(lengths.max())


class SelectedRows:
    """Keep the full encoder resident while exercising selected long rows."""

    def __init__(self, encoder, indices):
        self.encoder, self.indices = encoder, indices
        self.tok = encoder.tok
        self.features = encoder.features

    def build(self, row, *args, **kwargs):
        return self.encoder.build(int(self.indices[row]), *args, **kwargs)


def worker(context, manifest, manifest_sha):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from .core import RowEncoder, conditional_log_likelihood, memory, train_stage

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Probe requires exactly one visible CUDA GPU")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("Native BF16 is required")
    for key in ("trainer_code_version", "training_image"):
        if manifest[key] != context[key]:
            raise ValueError("Trainer/context provenance mismatch: " + key)
    if manifest["probe"] != {"fold": 0, "steps_per_stage": 20, "orders": 30}:
        raise ValueError("Only the bounded fold-0 memory probe is supported")
    out = Path("/tmp/s6e11-attempts") / context["attempt_id"]
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    publisher = Publisher(context, out)
    snapshots = []

    def snapshot(phase):
        torch.cuda.synchronize()
        point = {"phase": phase, "cgroup": cgroup_memory(), "process": memory("cuda"),
                 "gpu_allocated_bytes": torch.cuda.memory_allocated(),
                 "gpu_reserved_bytes": torch.cuda.memory_reserved(),
                 "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                 "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved()}
        snapshots.append(point)
        publisher.progress(phase, force=True, measurements={
            "worker_memory_bytes": point["cgroup"].get("current_bytes", 0),
            "worker_peak_memory_bytes": point["cgroup"].get("peak_bytes", 0),
            "gpu_peak_allocated_bytes": point["gpu_peak_allocated_bytes"]})
        print(json.dumps(point), flush=True)
        return point

    snapshot("setup")
    raw = read_bytes(manifest["dataset_manifest_uri"])
    if hashlib.sha256(raw).hexdigest() != context["dataset_manifest_hash"]:
        raise ValueError("Dataset manifest mismatch")
    dataset = json.loads(raw)
    if (dataset["model"]["revision"] != REVISION or
            dataset["files"]["split"]["sha256"] != context["split_manifest_hash"]):
        raise ValueError("Model/split identity mismatch")
    write_json(out / "dataset.json", dataset)
    snapshot("loading_full_fold")
    source, training, valid, _ = load(dataset, out / "data", fold=0, sampled=False)
    if (len(source), len(training), len(valid)) != (20000, 559968, 139992):
        raise ValueError("Full fold dimensions differ")
    snapshot("full_fold_loaded")
    weights = Path("/opt/gpt2")
    for name, sha in dataset["model"]["sha256"].items():
        if fingerprint(weights / name) != sha:
            raise ValueError("Pretrained checksum mismatch: " + name)
    tok = AutoTokenizer.from_pretrained(weights, local_files_only=True)
    frames = {"source": source, "competition": training, "validation": valid}
    encoders = {}
    for name, frame in frames.items():
        snapshot("encoding_" + name)
        encoders[name] = RowEncoder(tok, frame, dataset["features"])
        encoders[name].check()
        snapshot("encoded_" + name)
    model = AutoModelForCausalLM.from_pretrained(
        weights, local_files_only=True, dtype=torch.float32,
        attn_implementation="sdpa").to("cuda")
    snapshot("model_loaded")
    reports, length_bounds = {}, {}
    for name, accumulation in [("source", 1), ("competition", 2)]:
        indices, length_bounds[name] = longest_rows(
            encoders[name], 20 * 16 * accumulation, source=name == "source")
        args = SimpleNamespace(output=out, device="cuda", epochs=1, microbatch=16,
                               accumulation=accumulation, lr=5e-5, bf16=True,
                               checkpoint_steps=10000)
        snapshot("training_" + name)
        reports[name] = train_stage(model, SelectedRows(encoders[name], indices),
                                   frames[name].is_fraud.to_numpy(dtype=int)[indices],
                                   name, args)
        if reports[name]["optimizer_steps"] != 20:
            raise ValueError("Probe training step bound violated")
        snapshot("checkpoint_saved_" + name)
    # Retain both the accumulated 30-order likelihoods and concatenation copy,
    # as the normal scorer does before calculating full-fold probabilities.
    likelihoods = np.ones((len(valid), 30, 2), dtype=np.float64)
    concatenated = likelihoods.copy()
    indices, length_bounds["validation"] = longest_rows(encoders["validation"], 8)
    model.eval()
    snapshot("scoring_buffers_allocated")
    rng = np.random.default_rng(2025)
    for _ in range(30):
        feature_order = rng.permutation(len(encoders["validation"].features))
        seqs = [encoders["validation"].build(int(row), label, feature_order)
                for label in (0, 1) for row in indices]
        prefixes = [len(encoders["validation"].prefix[label])
                    for label in (0, 1) for _ in indices]
        values = conditional_log_likelihood(model, seqs, prefixes, tok.eos_token_id, "cuda")
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite probe likelihood")
    point = snapshot("scoring_complete")
    if point["cgroup"].get("events", {}).get("oom_kill", 0):
        raise RuntimeError("Worker cgroup recorded an OOM kill")
    # Missing kernel accounting must never produce a claim that host memory fits.
    peak, limit = point["cgroup"].get("peak_bytes"), point["cgroup"].get("limit_bytes")
    if not peak or not limit or peak >= limit:
        raise RuntimeError("Cannot verify worker peak below its memory limit")
    profile = {"scope": "full_fold_0_memory_probe_not_full_training",
               "device": torch.cuda.get_device_name(), "snapshots": snapshots,
               "rows_loaded": {k: len(v) for k, v in frames.items()},
               "training_probes": reports, "row_length_upper_bounds": length_bounds,
               "scoring_rows": len(indices), "scoring_orders": 30,
               "scoring_precision": "FP32", "bf16_training": True,
               "full_fold_scoring_buffer_bytes": likelihoods.nbytes + concatenated.nbytes,
               "trainer_manifest_sha256": manifest_sha,
               "limitations": ["Only fold 0 loaded", "20 optimizer steps per stage",
                               "Longest-row probe is not a multi-day stability test",
                               "No complete validation predictions or predictive metrics"]}
    measured = {"source_rows_loaded": len(source), "training_rows_loaded": len(training),
                "validation_rows_loaded": len(valid), "training_probe_steps": 40,
                "worker_peak_memory_bytes": peak, "worker_memory_limit_bytes": limit,
                "worker_memory_headroom_bytes": limit - peak,
                "gpu_peak_allocated_bytes": point["gpu_peak_allocated_bytes"],
                "gpu_peak_reserved_bytes": point["gpu_peak_reserved_bytes"]}
    write_json(out / "memory_profile.json", profile)
    publisher.artifact(out / "memory_profile.json", "memory_profile.json")
    publisher.artifact(out / "dataset.json", "manifests/dataset.json")
    publisher.progress("complete", force=True, measurements=measured)
    publisher.report(measured, "full_fold0_memory_probe;purpose=memory_fit;predictive_evaluation=false", [
        {"id": "memory_profile", "kind": "profile", "path": "memory_profile.json"},
        {"id": "dataset", "kind": "dataset_manifest", "path": "manifests/dataset.json"}])
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer-manifest-uri", "trainer-manifest-sha256", "model-dir"):
        parser.add_argument("--" + name, required=True)
    for name in ("input-table", "start-ds", "end-ds"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.input_table != "data.s6e11_gpt2_train_87eaa10b":
        raise ValueError("Unexpected training source")
    context = context_from_env(args.model_dir)
    raw = read_bytes(args.trainer_manifest_uri)
    if hashlib.sha256(raw).hexdigest() != args.trainer_manifest_sha256:
        raise ValueError("Trainer manifest checksum mismatch")
    import ray
    if ray.__version__ != "2.55.1":
        raise RuntimeError("Ray version mismatch")
    ray.init(address="auto")
    task = ray.remote(num_gpus=1, num_cpus=2, max_retries=0)(worker)
    print(json.dumps(ray.get(task.remote(context, json.loads(raw),
                                        args.trainer_manifest_sha256)), allow_nan=False))


if __name__ == "__main__":
    main()
