"""Score rows with a finished fold checkpoint: batch benchmark or full test set.

Same encoder, 30 feature orders (order_seed) and log-likelihood math as the
validation scorer in train.py. "fp32" reproduces it exactly; "tf32", "bf16" and
"fp16" trade small numeric drift for speed in the transformer body only (the
vocabulary head stays fp32 and sums stay fp64).
"""

import argparse
import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import pandas as pd
from .storage import download, fingerprint, read_bytes, write_json
from .attempt import Publisher, context_from_env
from .data import REVISION, load
from .train import validate_recipe

TEST_ROWS = 299984
CHUNK = 512
PRECISIONS = ("fp32", "tf32", "bf16", "fp16")


@contextmanager
def precision(model, name):
    """Run the transformer body in the requested precision; restore afterwards."""
    import torch

    body = model.transformer

    class Autocast(torch.nn.Module):
        def __init__(self, dtype):
            super().__init__()
            self.body, self.dtype = body, dtype

        def forward(self, **kwargs):
            with torch.autocast("cuda", dtype=self.dtype):
                return self.body(**kwargs)

    torch.backends.cuda.matmul.allow_tf32 = name == "tf32"
    torch.backends.cudnn.allow_tf32 = name == "tf32"
    if name in ("bf16", "fp16"):
        model.transformer = Autocast(torch.bfloat16 if name == "bf16" else torch.float16)
    try:
        yield
    finally:
        model.transformer = body
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False


def md5(path):
    h = hashlib.md5()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def feature_orders(recipe, n_features):
    rng = np.random.default_rng(recipe["order_seed"])
    return [rng.permutation(n_features) for _ in range(recipe["orders"])]


def likelihoods(model, encoder, lo, hi, orders, batch):
    """[row, order, label] summed field-token log-likelihoods for rows lo..hi."""
    from .core import conditional_log_likelihood

    ll = np.zeros((hi - lo, len(orders), 2), dtype=np.float64)
    for o, order in enumerate(orders):
        for start in range(lo, hi, batch):
            stop = min(start + batch, hi)
            rows = range(start, stop)
            seqs = [encoder.build(r, y, order) for y in (0, 1) for r in rows]
            prefixes = [len(encoder.prefix[y]) for y in (0, 1) for _ in rows]
            values = conditional_log_likelihood(
                model, seqs, prefixes, encoder.tok.eos_token_id, "cuda"
            )
            ll[start - lo : stop - lo, o] = values.reshape(2, -1).T
    return ll


def log_odds(ll):
    from scipy.special import logsumexp

    return logsumexp(ll[:, :, 1], axis=1) - logsumexp(ll[:, :, 0], axis=1)


def validate_scoring(scoring, recipe):
    if scoring["mode"] not in ("benchmark", "test") or scoring["fold"] != recipe["fold"]:
        raise ValueError("Invalid scoring mode/fold")
    if not scoring["checkpoint_uri"].endswith(".pt") or "/runs/" not in scoring["checkpoint_uri"]:
        raise ValueError("Invalid checkpoint URI")
    if scoring["mode"] == "benchmark":
        b = scoring["benchmark"]
        runs = b["runs"]
        if b["rows"] != CHUNK or not runs or runs[0] != {
            "precision": "fp32", "score_batch": recipe["score_batch"]}:
            raise ValueError("Benchmark must start with the exact validation setting on one chunk")
        for r in runs:
            if r["precision"] not in PRECISIONS or not 0 < r["score_batch"] <= 256:
                raise ValueError("Invalid benchmark run")
    elif type(scoring["score_batch"]) is not int or not 0 < scoring["score_batch"] <= 256:
        raise ValueError("Invalid test score_batch")
    elif scoring["precision"] not in PRECISIONS:
        raise ValueError("Invalid test precision")


def worker(context, manifest, manifest_sha):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Scoring requires exactly one visible CUDA GPU")
    for key in ("trainer_code_version", "training_image"):
        if manifest[key] != context[key]:
            raise ValueError("Trainer/context provenance mismatch: " + key)
    recipe, scoring = manifest["recipe"], manifest["scoring"]
    validate_recipe(recipe)
    validate_scoring(scoring, recipe)
    if context.get("parent_attempt_id") != scoring["parent_attempt_id"]:
        raise ValueError("Checkpoint lineage must be declared to Hub")
    out = Path("/tmp/s6e11-attempts") / context["attempt_id"]
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    publisher = Publisher(context, out)
    publisher.progress("setup", force=True, measurements={"visible_gpus": 1})

    raw = read_bytes(manifest["dataset_manifest_uri"])
    if hashlib.sha256(raw).hexdigest() != context["dataset_manifest_hash"]:
        raise ValueError("Dataset manifest does not match Hub context")
    dataset = json.loads(raw)
    if (
        dataset["model"]["revision"] != REVISION
        or dataset["files"]["split"]["sha256"] != context["split_manifest_hash"]
    ):
        raise ValueError("Model/split revision mismatch")
    (out / "dataset.json").write_bytes(raw)

    # The checkpoint must come from the same data, split, model, image and recipe.
    trained = json.loads(read_bytes(scoring["checkpoint_uri"] + ".json"))
    expected = {
        "recipe": recipe,
        "dataset_manifest_hash": context["dataset_manifest_hash"],
        "split_manifest_hash": context["split_manifest_hash"],
        "model_revision": REVISION,
        "training_image": manifest["training_image"],
    }
    if {k: trained[k] for k in expected} != expected:
        raise ValueError("Checkpoint provenance differs from scoring recipe")
    cp = out / "checkpoint.pt"
    from urllib.parse import urlparse
    import boto3

    u = urlparse(scoring["checkpoint_uri"])
    boto3.client("s3").download_file(u.netloc, u.path.lstrip("/"), str(cp))
    if md5(cp) != scoring["checkpoint_md5"]:
        raise ValueError("Checkpoint MD5 differs from pinned S3 ETag")
    checkpoint_sha = fingerprint(cp)

    source, training, valid, paths = load(dataset, out / "data", recipe["fold"], False)
    weights = Path("/opt/gpt2")
    for name, sha in dataset["model"]["sha256"].items():
        if fingerprint(weights / name) != sha:
            raise ValueError("Pretrained file checksum mismatch: " + name)
    tok = AutoTokenizer.from_pretrained(weights, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        weights, local_files_only=True, dtype=torch.float32, attn_implementation="sdpa"
    ).to("cuda")
    state = torch.load(cp, map_location="cpu", weights_only=True)
    if state["next_step"] != 139992:
        raise ValueError("Checkpoint is not the final classifier step")
    model.load_state_dict(state["model"])
    del state
    cp.unlink()
    model.eval()
    lineage = {
        "fold": recipe["fold"],
        "recipe": recipe,
        "checkpoint_uri": scoring["checkpoint_uri"],
        "checkpoint_sha256": checkpoint_sha,
        "parent_attempt_id": scoring["parent_attempt_id"],
        "checkpoint_trainer_code_version": trained["trainer_code_version"],
        "scoring_trainer_code_version": manifest["trainer_code_version"],
        "training_image": manifest["training_image"],
        "dataset_manifest_hash": context["dataset_manifest_hash"],
        "scoring_precision": "transformer per run/test precision; float32 head; float64 sums",
        "prior": "none (reference_no_prior); logit = logsumexp_o ll(True) - logsumexp_o ll(False)",
        "trainer_manifest_sha256": manifest_sha,
    }

    if scoring["mode"] == "benchmark":
        return benchmark(model, tok, valid, dataset, recipe, scoring, lineage, out, publisher)
    return score_test(model, tok, paths, dataset, recipe, scoring, lineage, out, publisher)


def benchmark(model, tok, valid, dataset, recipe, scoring, lineage, out, publisher):
    import torch
    from .core import RowEncoder

    b = scoring["benchmark"]
    ref_path = download(b["reference_uri"], out / "reference.npz", b["reference_sha256"])
    ref = np.load(ref_path)
    if not np.array_equal(ref["id"], valid.id.iloc[:CHUNK].to_numpy()):
        raise ValueError("Reference chunk ids differ from fold validation rows")
    encoder = RowEncoder(tok, valid.iloc[:CHUNK].reset_index(drop=True), dataset["features"])
    encoder.check()
    orders = feature_orders(recipe, len(encoder.features))
    if not np.array_equal(np.array(orders), ref["orders"]):
        raise ValueError("Feature orders differ from the validation scorer")
    ref_odds = log_odds(ref["ll"])
    results, measured = [], {"benchmark_rows": CHUNK}
    for run in b["runs"]:
        batch, name = run["score_batch"], run["precision"]
        tag = f"{name}_b{batch}"
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.perf_counter()
        try:
            with precision(model, name):
                ll = likelihoods(model, encoder, 0, CHUNK, orders, batch)
        except (torch.cuda.OutOfMemoryError, ValueError) as e:
            results.append({**run, "error": type(e).__name__ + ": " + str(e)[:200]})
            print(json.dumps(results[-1]), flush=True)
            continue
        torch.cuda.synchronize()
        seconds = time.perf_counter() - started
        odds = log_odds(ll)
        row = {
            **run,
            "seconds": seconds,
            "rows_per_second": CHUNK / seconds,
            "max_abs_ll_diff": float(np.abs(ll - ref["ll"]).max()),
            "max_abs_logodds_diff": float(np.abs(odds - ref_odds).max()),
            "max_abs_prob_diff": float(
                np.abs(1 / (1 + np.exp(-odds)) - 1 / (1 + np.exp(-ref_odds))).max()
            ),
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        }
        results.append(row)
        print(json.dumps(row), flush=True)
        publisher.progress("benchmark", force=True, measurements={
            f"{tag}_rows_per_second": row["rows_per_second"],
            f"{tag}_max_abs_logodds_diff": row["max_abs_logodds_diff"],
        })
        for k in ("rows_per_second", "max_abs_logodds_diff", "max_abs_prob_diff",
                  "gpu_peak_allocated_bytes"):
            measured[f"{tag}_{k}"] = float(row[k])
    write_json(out / "benchmark.json", {**lineage, "reference_uri": b["reference_uri"],
                                         "device": torch.cuda.get_device_name(),
                                         "results": results})
    publisher.artifact(out / "benchmark.json", "benchmark.json")
    publisher.progress("complete", force=True, measurements=measured)
    publisher.report(
        measured,
        f"score_batch_benchmark;fold={recipe['fold']};rows={CHUNK};orders={recipe['orders']};purpose=throughput",
        [{"id": "benchmark", "kind": "profile", "path": "benchmark.json"}],
    )
    return measured


def score_test(model, tok, paths, dataset, recipe, scoring, lineage, out, publisher):
    import torch
    from .core import RowEncoder

    test = pd.read_csv(paths["test"])
    if len(test) != TEST_ROWS or test.id.duplicated().any() or "is_fraud" in test:
        raise ValueError("Unexpected test table")
    encoder = RowEncoder(tok, test, dataset["features"])
    encoder.check()
    orders = feature_orders(recipe, len(encoder.features))
    batch = scoring["score_batch"]
    started, chunks = time.perf_counter(), []
    for lo in range(0, len(test), CHUNK):
        hi = min(lo + CHUNK, len(test))
        with precision(model, scoring["precision"]):
            ll = likelihoods(model, encoder, lo, hi, orders, batch)
        path = out / f"likelihoods-{lo:06d}.npz"
        np.savez_compressed(path, id=test.id.iloc[lo:hi].to_numpy(), ll=ll,
                            orders=np.array(orders))
        publisher.artifact(path, "test_evaluation/" + path.name)
        path.unlink()
        chunks.append(ll)
        publisher.progress("scoring", rows=hi, total_steps=len(test))
    seconds = time.perf_counter() - started
    logit = log_odds(np.concatenate(chunks))
    if not np.isfinite(logit).all() or len(logit) != len(test):
        raise ValueError("Nonfinite or incomplete test log-odds")
    predictions = pd.DataFrame({"id": test.id, "logit": logit,
                                "prediction": 1 / (1 + np.exp(-logit))})
    pred_path = out / "test.csv"
    predictions.to_csv(pred_path, index=False, float_format="%.10g")
    write_json(pred_path.with_suffix(".json"), {
        **lineage, "complete": True, "scope": "test", "rows": len(test),
        "score_batch": batch, "precision": scoring["precision"], "test_sha256": dataset["files"]["test"]["sha256"],
        "predictions_sha256": fingerprint(pred_path),
    })
    measured = {
        "test_rows": len(test),
        "scoring_seconds": seconds,
        "rows_per_second": len(test) / seconds,
        "mean_prediction": float(predictions.prediction.mean()),
        "mean_logit": float(logit.mean()),
        "gpu_peak_allocated_bytes": float(torch.cuda.max_memory_allocated()),
    }
    publisher.artifact(pred_path, "predictions/test.csv")
    publisher.artifact(pred_path.with_suffix(".json"), "predictions/test.json")
    publisher.artifact(out / "dataset.json", "manifests/dataset.json")
    publisher.progress("complete", force=True, measurements=measured)
    publisher.report(
        measured,
        f"test;fold={recipe['fold']};prior={recipe['prior_mode']};orders={recipe['orders']};purpose=test_prediction",
        [{"id": "test", "kind": "predictions", "path": "predictions/test.csv"},
         {"id": "coverage", "kind": "manifest", "path": "predictions/test.json"},
         {"id": "dataset", "kind": "dataset_manifest", "path": "manifests/dataset.json"}],
    )
    return measured


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer-manifest-uri", "trainer-manifest-sha256", "model-dir"):
        p.add_argument("--" + name, required=True)
    for name in ("input-table", "start-ds", "end-ds"):
        p.add_argument("--" + name)
    a = p.parse_args()
    if a.input_table != "data.s6e11_gpt2_train_87eaa10b":
        raise ValueError("Unexpected training source: use the audited external table")
    context = context_from_env(a.model_dir)
    raw = read_bytes(a.trainer_manifest_uri)
    if hashlib.sha256(raw).hexdigest() != a.trainer_manifest_sha256:
        raise ValueError("Trainer manifest checksum mismatch")
    manifest = json.loads(raw)
    validate_recipe(manifest["recipe"])
    validate_scoring(manifest["scoring"], manifest["recipe"])
    import ray

    if ray.__version__ != "2.55.1":
        raise RuntimeError("Ray runtime must match Platform 2.55.1")
    ray.init(address="auto")
    task = ray.remote(num_gpus=1, num_cpus=2, max_retries=0)(worker)
    print(json.dumps(ray.get(task.remote(context, manifest, a.trainer_manifest_sha256)),
                     allow_nan=False))


if __name__ == "__main__":
    main()
