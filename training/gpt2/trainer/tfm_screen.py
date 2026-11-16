"""Fold-k screen of in-context tabular foundation models (Kumo-Tabular, TabICLv2).

Context per bag: every training-fold fraud plus random training-fold non-frauds up to
`context_rows` (numpy default_rng(seed)); validation labels never enter a context or a
query table (query labels are replaced by a placeholder before any table is built).
Row logit = mean over bags of log(p / (1 - p)).

Arms: "a" raw columns; "b" raw columns plus, as categorical strings, the cents
(round(value mod 1, 2)) and leading digit of amount_usd, hours_since_last_txn,
velocity_score and distance_from_home_km.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from .storage import fingerprint, read_bytes, write_json
from .attempt import Publisher, context_from_env
from .data import REVISION, load

MODELS = ("kumo_tabular", "tabicl_v2")
ARMS = ("a", "b")
DIGIT_COLUMNS = ("amount_usd", "hours_since_last_txn", "velocity_score", "distance_from_home_km")
QUERY_CHUNK = 35000
WEIGHTS = Path("/opt/tfm")


def cents(x):
    # value mod 1 rounded to 2 places, computed on integer cents to avoid float drift
    return (np.rint(np.abs(np.asarray(x, dtype=np.float64)) * 100).astype(np.int64) % 100)


def leading_digit(x):
    v = np.abs(np.asarray(x, dtype=np.float64))
    out = np.zeros(len(v), dtype=np.int64)
    pos = v > 0
    e = np.floor(np.log10(v[pos]))
    d = np.floor(v[pos] / 10.0 ** e + 1e-9).astype(np.int64)
    out[pos] = np.clip(d, 1, 9)
    return out


def arm_frame(frame, features, arm):
    x = frame[list(features)].copy()
    for c in x.columns:
        if x[c].dtype == bool:
            x[c] = x[c].astype(np.int64)
    if arm == "b":
        for c in DIGIT_COLUMNS:
            x[c + "_cents"] = pd.Series(cents(frame[c]), index=x.index).map("c{:02d}".format)
            x[c + "_lead"] = pd.Series(leading_digit(frame[c]), index=x.index).map("d{}".format)
    elif arm != "a":
        raise ValueError("Unknown arm")
    return x


def categorical_columns(x):
    return [c for c in x.columns if x[c].dtype == object or str(x[c].dtype) in ("string", "str", "category")]


def context_index(labels, rows, seed):
    """Positions of all frauds plus random non-frauds up to `rows` (sorted)."""
    labels = np.asarray(labels)
    pos, neg = np.where(labels == 1)[0], np.where(labels == 0)[0]
    if len(pos) >= rows:
        raise ValueError("Context cannot hold every fraud")
    rng = np.random.default_rng(seed)
    take = rng.choice(neg, rows - len(pos), replace=False)
    return np.sort(np.concatenate([pos, take]))


def logit(p):
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


class TabICLRunner:
    name = "tabicl_v2"

    def __init__(self, cfg, device):
        from tabicl import TabICLClassifier
        self.cls, self.cfg, self.device = TabICLClassifier, cfg, device

    def fit(self, xc, yc, seed):
        self.model = self.cls(
            n_estimators=self.cfg["n_estimators"], model_path=self.cfg["model_path"],
            allow_auto_download=False, checkpoint_version=self.cfg["checkpoint"],
            device=self.device, use_amp=self.cfg["precision"] == "amp", random_state=seed,
            batch_size=self.cfg.get("estimator_batch", 8), kv_cache=self.cfg.get("kv_cache", False),
        )
        # string columns go through TabICL's own OrdinalEncoder (unknown -> -1)
        self.model.fit(xc, np.asarray(yc, dtype=np.int64))
        return self

    def predict(self, xq):
        proba = self.model.predict_proba(xq)
        cls = list(self.model.classes_)
        return proba[:, cls.index(1)]


class KumoRunner:
    name = "kumo_tabular"

    def __init__(self, cfg, device):
        import torch
        import sdm
        import sdm.models.kumo.tabular.model as kumo_model
        self.torch, self.sdm, self.cfg, self.device = torch, sdm, cfg, torch.device(device)
        pinned = cfg["model_path"]                 # checksum-verified local file; never download
        kumo_model.download_checkpoint = lambda **_: pinned
        self.model = sdm.models.KumoTabular(task="classification", size=cfg["size"], device=self.device)

    def fit(self, xc, yc, seed):
        self.xc, self.yc, self.seed = xc, np.asarray(yc, dtype=np.int64), seed
        return self

    def predict(self, xq):
        torch, sdm = self.torch, self.sdm
        nc = len(self.xc)
        df = pd.concat([self.xc, xq], ignore_index=True)
        df["is_fraud"] = np.concatenate([self.yc, np.zeros(len(xq), dtype=np.int64)])  # placeholder, never read
        overrides = {c: "categorical" for c in categorical_columns(df)}
        overrides["is_fraud"] = "categorical"
        table = sdm.TableTensor.from_pandas(df=df, stypes=sdm.infer_stypes(df, overrides=overrides), device=self.device)
        g = torch.Generator(device=self.device).manual_seed(int(self.seed))
        amp = self.cfg["precision"] == "fp16" and self.device.type == "cuda"
        with torch.inference_mode(), torch.amp.autocast(self.device.type, dtype=torch.float16, enabled=amp):
            out = self.model(
                x_context=table[:nc].drop_columns("is_fraud"), y_context=table[:nc, "is_fraud"],
                x_query=table[nc:].drop_columns("is_fraud"), num_estimators=self.cfg["n_estimators"],
                generator=g,
            )
        probs = out.numerical if hasattr(out, "numerical") else out
        probs = probs.float().cpu().numpy() if hasattr(probs, "cpu") else np.asarray(probs)
        probs = probs.reshape(len(xq), -1)
        return probs[:, 1] if probs.shape[1] >= 2 else probs[:, 0]


def make_runner(cfg, device):
    return {"tabicl_v2": TabICLRunner, "kumo_tabular": KumoRunner}[cfg["model"]](cfg, device)


def run_arm(runner, training, valid, features, arm, cfg, publisher=None, out=None, budget=None):
    """Return (mean logit over bags, per-bag logits, timings)."""
    xt, xv = arm_frame(training, features, arm), arm_frame(valid, features, arm)
    yt = training.is_fraud.to_numpy().astype(np.int64)
    bags, timings, started = [], [], time.perf_counter()
    n_chunks = -(-len(xv) // QUERY_CHUNK)
    for b, seed in enumerate(cfg["seeds"]):
        t0 = time.perf_counter()
        idx = context_index(yt, cfg["context_rows"], seed)
        runner.fit(xt.iloc[idx].reset_index(drop=True), yt[idx], seed)
        preds = []
        for k in range(n_chunks):
            q = xv.iloc[k * QUERY_CHUNK:(k + 1) * QUERY_CHUNK].reset_index(drop=True)
            preds.append(runner.predict(q))
            if budget is not None and b == 0 and k == 0:
                per_chunk = time.perf_counter() - t0
                projected = per_chunk * n_chunks * len(cfg["seeds"]) * budget["arms"]
                if publisher:
                    publisher.progress("projection", force=True,
                                       measurements={"first_chunk_seconds": per_chunk, "projected_seconds": projected})
                if projected > budget["max_seconds"]:
                    raise RuntimeError(f"Projected {projected:.0f}s exceeds budget {budget['max_seconds']}s")
            if publisher:
                publisher.progress("scoring", rows=min((k + 1) * QUERY_CHUNK, len(xv)), total_steps=len(xv))
        p = np.concatenate(preds)
        if len(p) != len(xv) or not np.isfinite(p).all():
            raise ValueError("Incomplete or nonfinite predictions")
        bags.append(logit(p))
        timings.append({"seed": seed, "context_rows": int(len(idx)), "context_frauds": int(yt[idx].sum()),
                        "seconds": time.perf_counter() - t0})
        if out is not None and publisher is not None:
            path = out / f"{cfg['model']}-{arm}-bag{seed}.npz"
            np.savez_compressed(path, id=valid.id.to_numpy(), logit=bags[-1], context_index=idx)
            publisher.artifact(path, f"bags/{path.name}")
            path.unlink()
    return np.mean(bags, axis=0), bags, timings, time.perf_counter() - started


def validate_screen(s):
    if s.get("model") not in MODELS or not set(s.get("arms", [])) <= set(ARMS) or not s.get("arms"):
        raise ValueError("Unknown model or arms")
    if s.get("fold") != 0 or s.get("context_rows") != 100000 or s.get("seeds") != [0, 1, 2]:
        raise ValueError("Screen is fold 0, 100k contexts, seeds 0,1,2")
    if not isinstance(s.get("n_estimators"), int) or not 1 <= s["n_estimators"] <= 32:
        raise ValueError("n_estimators must be an int in 1..32")
    if not isinstance(s.get("max_seconds"), int) or s["max_seconds"] <= 0:
        raise ValueError("max_seconds budget required")
    if len(s.get("weights_sha256", "")) != 64:
        raise ValueError("Pinned weights sha256 required")


def worker(context, manifest, manifest_sha):
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Screen requires exactly one visible CUDA GPU")
    for key in ("trainer_code_version", "training_image"):
        if manifest[key] != context[key]:
            raise ValueError("Trainer/context provenance mismatch: " + key)
    s = manifest["screen"]
    validate_screen(s)
    out = Path("/tmp/s6e11-attempts") / context["attempt_id"]
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    publisher = Publisher(context, out)
    publisher.progress("setup", force=True, measurements={"visible_gpus": 1})

    raw = read_bytes(manifest["dataset_manifest_uri"])
    if hashlib.sha256(raw).hexdigest() != context["dataset_manifest_hash"]:
        raise ValueError("Dataset manifest does not match Hub context")
    dataset = json.loads(raw)
    if dataset["model"]["revision"] != REVISION or dataset["files"]["split"]["sha256"] != context["split_manifest_hash"]:
        raise ValueError("Model/split revision mismatch")
    (out / "dataset.json").write_bytes(raw)
    _, training, valid, _ = load(dataset, out / "data", s["fold"], False)
    if set(training.id) & set(valid.id):
        raise ValueError("Training/validation overlap")

    wpath = WEIGHTS / s["weights_file"]
    if fingerprint(wpath) != s["weights_sha256"]:
        raise ValueError("Pinned weights checksum mismatch")
    cfg = dict(s, model_path=str(wpath))
    runner = make_runner(cfg, "cuda")
    gpu = torch.cuda.get_device_name(0)
    budget = {"max_seconds": s["max_seconds"], "arms": len(s["arms"])}
    measured, artifacts = {"gpu": gpu}, []
    from sklearn.metrics import roc_auc_score

    for arm in s["arms"]:
        torch.cuda.reset_peak_memory_stats()
        mean, bags, timings, seconds = run_arm(runner, training, valid, dataset["features"], arm, cfg,
                                               publisher, out, budget)
        budget = None
        pred = valid[["id", "is_fraud"]].copy()
        pred["fold"] = s["fold"]
        pred["prediction"] = 1 / (1 + np.exp(-mean))
        pred["logit"] = mean
        tag = f"{s['model']}-{arm}"
        path = out / f"{tag}.csv"
        pred.to_csv(path, index=False, float_format="%.10g")
        auc = float(roc_auc_score(valid.is_fraud, mean))
        info = {
            "model": s["model"], "arm": arm, "model_version": s["model_version"],
            "weights_file": s["weights_file"], "weights_sha256": s["weights_sha256"],
            "context_rows": s["context_rows"], "bags": len(s["seeds"]), "seeds": s["seeds"],
            "n_estimators": s["n_estimators"], "precision": s["precision"], "gpu": gpu,
            "wall_seconds": seconds, "bag_timings": timings, "rows": len(pred),
            "auc_fold0_reported_by_worker": auc, "bag_aucs": [float(roc_auc_score(valid.is_fraud, b)) for b in bags],
            "gpu_peak_allocated_bytes": float(torch.cuda.max_memory_allocated()),
            "predictions_sha256": fingerprint(path), "trainer_manifest_sha256": manifest_sha,
            "trainer_code_version": manifest["trainer_code_version"], "training_image": manifest["training_image"],
            "dataset_manifest_hash": context["dataset_manifest_hash"],
            "context_rule": "all training-fold frauds + default_rng(seed) non-frauds; validation labels never used",
        }
        write_json(path.with_suffix(".json"), info)
        publisher.artifact(path, f"predictions/{tag}.csv")
        publisher.artifact(path.with_suffix(".json"), f"predictions/{tag}.json")
        artifacts += [{"id": tag, "kind": "predictions", "path": f"predictions/{tag}.csv"},
                      {"id": tag + "-manifest", "kind": "manifest", "path": f"predictions/{tag}.json"}]
        measured[f"auc_{arm}"], measured[f"seconds_{arm}"] = auc, seconds
        publisher.progress("arm_complete", force=True, measurements={f"auc_{arm}": auc, f"seconds_{arm}": seconds})
    publisher.artifact(out / "dataset.json", "manifests/dataset.json")
    artifacts.append({"id": "dataset", "kind": "dataset_manifest", "path": "manifests/dataset.json"})
    numeric = {k: v for k, v in measured.items() if isinstance(v, (int, float))}
    publisher.report(numeric, f"tfm_screen;model={s['model']};fold={s['fold']};context={s['context_rows']};bags={len(s['seeds'])};purpose=validation", artifacts)
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
    validate_screen(manifest["screen"])
    import ray

    if ray.__version__ != "2.55.1":
        raise RuntimeError("Ray runtime must match Platform 2.55.1")
    ray.init(address="auto")
    task = ray.remote(num_gpus=1, num_cpus=4, max_retries=0)(worker)
    print(json.dumps(ray.get(task.remote(context, manifest, a.trainer_manifest_sha256)), allow_nan=False))


if __name__ == "__main__":
    main()
