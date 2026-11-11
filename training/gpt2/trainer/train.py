"""Ray CPU driver; full-weight GPT-2 work explicitly occupies one GPU worker."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from .storage import download, fingerprint, read_bytes, write_json
from .attempt import Publisher, context_from_env
from .metrics import metrics, probabilities
from .data import REVISION, load


def validate_recipe(recipe):
    for key in (
        "source_epochs",
        "competition_epochs",
        "microbatch",
        "source_accumulation",
        "competition_accumulation",
        "score_batch",
        "orders",
        "checkpoint_steps",
    ):
        if type(recipe[key]) is not int or recipe[key] <= 0:
            raise ValueError("Positive integer required: " + key)
    if (
        recipe["fold"] not in range(5)
        or recipe["orders"] > 30
        or recipe["prior_mode"] not in ("fold_training_prior", "reference_no_prior")
    ):
        raise ValueError("Invalid scoring/fold policy")
    if recipe["bf16"] not in (True, False) or not 0 < recipe["lr"] < 1:
        raise ValueError("Invalid precision/learning rate")


def resume_compatible(saved, current, stage):
    if stage not in ("source", "competition"):
        return False
    if stage == "competition":
        return saved == current
    # Source adaptation is independent of the competition fold. An immutable
    # source checkpoint may initialize a fresh classifier for each fold.
    source_keys = ("source_epochs", "microbatch", "source_accumulation", "lr", "bf16")

    def source_identity(config):
        return {
            **{k: v for k, v in config.items() if k != "recipe"},
            "recipe": {k: config["recipe"][k] for k in source_keys},
        }

    return source_identity(saved) == source_identity(current)


def score(model, encoder, valid, training, recipe, out, publisher):
    from .core import conditional_log_likelihood

    rng = np.random.default_rng(recipe["order_seed"])
    orders = [rng.permutation(len(encoder.features)) for _ in range(recipe["orders"])]
    model.eval()
    all_ll = []
    for lo in range(0, len(valid), 512):
        hi = min(lo + 512, len(valid))
        ll = np.zeros((hi - lo, len(orders), 2), dtype=np.float64)
        for o, order in enumerate(orders):
            for start in range(lo, hi, recipe["score_batch"]):
                stop = min(start + recipe["score_batch"], hi)
                rows = range(start, stop)
                seqs = [encoder.build(r, y, order) for y in (0, 1) for r in rows]
                prefixes = [len(encoder.prefix[y]) for y in (0, 1) for _ in rows]
                values = conditional_log_likelihood(
                    model, seqs, prefixes, encoder.tok.eos_token_id, "cuda"
                )
                ll[start - lo : stop - lo, o] = values.reshape(2, -1).T
                publisher.progress("scoring", rows=start, total_steps=len(valid))
        chunk = out / f"likelihoods-{lo:06d}.npz"
        np.savez_compressed(
            chunk, id=valid.id.iloc[lo:hi].to_numpy(), ll=ll, orders=np.array(orders)
        )
        publisher.artifact(chunk, "evaluation/" + chunk.name)
        all_ll.append(ll)
    p = probabilities(
        np.concatenate(all_ll), recipe["prior_mode"], float(training.is_fraud.mean())
    )
    predictions = valid[["id", "is_fraud"]].copy()
    predictions["fold"], predictions["prediction"] = recipe["fold"], p
    path = out / "validation.csv"
    predictions.to_csv(path, index=False)
    return path, metrics(valid.is_fraud, p)


def worker(context, manifest, manifest_sha):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from .core import RowEncoder, train_stage

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Training requires exactly one visible CUDA GPU")
    for key in ("trainer_code_version", "training_image"):
        if manifest[key] != context[key]:
            raise ValueError("Trainer/context provenance mismatch: " + key)
    recipe = manifest["recipe"]
    validate_recipe(recipe)
    # A new task has a fresh directory. Automatic Ray task retries are disabled;
    # resumption is an explicit new Hub attempt with parent provenance.
    out = Path("/tmp/s6e11-attempts") / context["attempt_id"]
    out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    publisher = Publisher(context, out)
    publisher.progress(
        "setup", force=True, measurements={"visible_gpus": torch.cuda.device_count()}
    )
    dataset_raw = read_bytes(manifest["dataset_manifest_uri"])
    if hashlib.sha256(dataset_raw).hexdigest() != context["dataset_manifest_hash"]:
        raise ValueError("Dataset manifest does not match Hub context")
    dataset = json.loads(dataset_raw)
    if (
        dataset["model"]["revision"] != REVISION
        or dataset["files"]["split"]["sha256"] != context["split_manifest_hash"]
    ):
        raise ValueError("Model/split revision mismatch")
    (out / "dataset.json").write_bytes(dataset_raw)
    source, training, valid, paths = load(
        dataset, out / "data", recipe["fold"], recipe["sampled"]
    )
    weights = Path("/opt/gpt2")
    for name, sha in dataset["model"]["sha256"].items():
        if fingerprint(weights / name) != sha:
            raise ValueError("Pretrained file checksum mismatch: " + name)
    tok = AutoTokenizer.from_pretrained(weights, local_files_only=True)
    encoders = {
        n: RowEncoder(tok, frame, dataset["features"])
        for n, frame in [
            ("source", source),
            ("competition", training),
            ("validation", valid),
        ]
    }
    for encoder in encoders.values():
        encoder.check()
    model = AutoModelForCausalLM.from_pretrained(
        weights, local_files_only=True, dtype=torch.float32, attn_implementation="sdpa"
    ).to("cuda")
    if not all(p.requires_grad for p in model.parameters()):
        raise ValueError("All model weights must be trainable")
    resume_config = {
        "recipe": recipe,
        "dataset_manifest_hash": context["dataset_manifest_hash"],
        "split_manifest_hash": context["split_manifest_hash"],
        "model_revision": REVISION,
        "trainer_code_version": manifest["trainer_code_version"],
        "training_image": manifest["training_image"],
    }
    write_json(out / "resume_config.json", resume_config)
    resume = manifest.get("resume")
    if resume:
        if context.get("parent_attempt_id") != resume["parent_attempt_id"]:
            raise ValueError("Resume lineage must be declared to Hub")
        if not resume_compatible(
            json.loads(read_bytes(resume["checkpoint_uri"] + ".json")),
            resume_config,
            resume["stage"],
        ):
            raise ValueError("Resume recipe/provenance mismatch")
        if (
            resume["stage"] not in ("source", "competition")
            or "/runs/" not in resume["checkpoint_uri"]
        ):
            raise ValueError("Invalid resume stage/URI")
        download(
            resume["checkpoint_uri"],
            out / resume["stage"] / "checkpoint.pt",
            resume["sha256"],
        )
    reports = {}
    for name, frame in [("source", source), ("competition", training)]:
        if resume and resume["stage"] == "competition" and name == "source":
            continue  # Competition checkpoint contains adapted model + optimizer/RNG.
        args = SimpleNamespace(
            output=out,
            device="cuda",
            epochs=recipe[name + "_epochs"],
            microbatch=recipe["microbatch"],
            accumulation=recipe[name + "_accumulation"],
            lr=recipe["lr"],
            bf16=recipe["bf16"],
            checkpoint_steps=recipe["checkpoint_steps"],
            checkpoint_callback=publisher.checkpoint_saved,
            progress_callback=lambda phase, step, total, loss: publisher.progress(
                phase, step=step, total_steps=total, measurements={"lm_loss": loss}
            ),
        )
        reports[name] = train_stage(
            model, encoders[name], frame.is_fraud.to_numpy(dtype=int), name, args
        )
        expected_checkpoint = (
            f"checkpoints/{name}-{reports[name]['optimizer_steps']:08d}.pt"
        )
        if publisher.checkpoint != expected_checkpoint:
            publisher.checkpoint_saved(
                out / name / "checkpoint.pt", name, reports[name]["optimizer_steps"]
            )
    predictions, measured = score(
        model, encoders["validation"], valid, training, recipe, out, publisher
    )
    scope = "sampled_fold0_10k" if recipe["sampled"] else "full_fold"
    write_json(
        predictions.with_suffix(".json"),
        {
            **resume_config,
            "complete": True,
            "scope": scope,
            "fold": recipe["fold"],
            "predictions_sha256": fingerprint(predictions),
            "recipe": {k: v for k, v in recipe.items() if k != "fold"},
        },
    )
    measured.update(
        training_rows=len(training),
        source_rows=len(source),
        trainable_parameters=sum(p.numel() for p in model.parameters()),
    )
    write_json(
        out / "profile.json",
        {
            "device": torch.cuda.get_device_name(),
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "stages": reports,
            "training_prior": float(training.is_fraud.mean()),
            "scoring_precision": "float32 transformer/head; float64 sums",
            "trainer_manifest_sha256": manifest_sha,
            "adaptation": "S6E10-inspired pilot optimizer, not exact legacy GReaT parity",
        },
    )
    artifacts = []
    for ident, kind, path, relative in [
        ("validation", "predictions", predictions, "predictions/validation.csv"),
        (
            "coverage",
            "manifest",
            predictions.with_suffix(".json"),
            "predictions/validation.json",
        ),
        ("dataset", "dataset_manifest", out / "dataset.json", "manifests/dataset.json"),
        ("split", "split_manifest", paths["split"], "manifests/split.json"),
        ("profile", "profile", out / "profile.json", "profile.json"),
        ("recipe", "manifest", out / "resume_config.json", "manifests/recipe.json"),
    ]:
        publisher.artifact(path, relative)
        artifacts.append({"id": ident, "kind": kind, "path": relative})
    artifacts.append(
        {"id": "checkpoint", "kind": "checkpoint", "path": publisher.checkpoint}
    )
    publisher.progress("complete", force=True, measurements=measured)
    publisher.report(
        measured,
        f"{scope};fold={recipe['fold']};prior={recipe['prior_mode']};orders={recipe['orders']};purpose=validation",
        artifacts,
    )
    return measured


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trainer-manifest-uri", required=True)
    p.add_argument("--trainer-manifest-sha256", required=True)
    p.add_argument("--model-dir", required=True)
    # Existing generic Model training arguments supplied by Platform.
    p.add_argument("--input-table")
    p.add_argument("--start-ds")
    p.add_argument("--end-ds")
    a = p.parse_args()
    if a.input_table != "data.s6e11_gpt2_train_87eaa10b":
        raise ValueError("Unexpected training source: use the audited external table")
    context = context_from_env(a.model_dir)
    raw = read_bytes(a.trainer_manifest_uri)
    if hashlib.sha256(raw).hexdigest() != a.trainer_manifest_sha256:
        raise ValueError("Trainer manifest checksum mismatch")
    manifest = json.loads(raw)
    validate_recipe(manifest["recipe"])
    import ray

    if ray.__version__ != "2.55.1":
        raise RuntimeError("Ray runtime must match Platform 2.55.1")
    ray.init(address="auto")
    task = ray.remote(num_gpus=1, num_cpus=2, max_retries=0)(worker)
    print(
        json.dumps(
            ray.get(task.remote(context, manifest, a.trainer_manifest_sha256)),
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
