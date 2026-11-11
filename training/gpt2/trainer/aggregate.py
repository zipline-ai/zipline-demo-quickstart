"""Pool five compatible, complete held-out folds. Never average fold AUCs."""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .metrics import metrics
from .storage import fingerprint, write_json


def aggregate(paths, truth_path, folds_path=None):
    truth = pd.read_csv(truth_path)
    if folds_path is not None:
        folds = pd.read_csv(folds_path)
        if folds.id.duplicated().any() or set(folds.id) != set(truth.id):
            raise ValueError("Split IDs differ from training IDs")
        truth = truth.merge(folds, on="id", validate="one_to_one")
    if truth.id.duplicated().any() or set(truth.fold) != set(range(5)):
        raise ValueError("Invalid truth/split coverage")
    if len(paths) != 5:
        raise ValueError("Exactly five prediction files required")
    seen, frames, compatible = set(), [], None
    for path in map(Path, paths):
        meta = json.loads(path.with_suffix(".json").read_text())
        if (
            meta.get("complete") is not True
            or meta.get("scope") != "full_fold"
            or fingerprint(path) != meta["predictions_sha256"]
        ):
            raise ValueError("Incomplete/corrupt fold")
        recipe = {
            k: meta[k]
            for k in (
                "dataset_manifest_hash",
                "split_manifest_hash",
                "recipe",
                "model_revision",
                "trainer_code_version",
                "training_image",
            )
        }
        if compatible is not None and compatible != recipe:
            raise ValueError("Incompatible fold provenance")
        compatible = recipe
        fold = meta["fold"]
        if fold in seen or fold not in range(5):
            raise ValueError("Repeated/invalid fold")
        seen.add(fold)
        frame = pd.read_csv(path)
        expected = truth[truth.fold == fold].set_index("id")
        if (
            frame.id.duplicated().any()
            or set(frame.id) != set(expected.index)
            or not (frame.fold == fold).all()
        ):
            raise ValueError("Incomplete held-out coverage")
        aligned = expected.loc[frame.id]
        if not np.array_equal(aligned.is_fraud, frame.is_fraud):
            raise ValueError("Labels do not match split truth")
        metrics(frame.is_fraud, frame.prediction)
        frames.append(frame)
    pooled = pd.concat(frames, ignore_index=True)
    if pooled.id.duplicated().any() or set(pooled.id) != set(truth.id):
        raise ValueError("Not exactly one prediction per training ID")
    return {
        **metrics(pooled.is_fraud, pooled.prediction, "oof"),
        "complete": True,
        "scope": "pooled_five_fold_oof",
        "provenance": compatible,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--truth",
        type=Path,
        required=True,
        help="Persisted folds.csv including id/is_fraud/fold",
    )
    p.add_argument(
        "--folds", type=Path, required=True, help="Original persisted folds.csv"
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("predictions", nargs=5, type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("Output already exists")
    write_json(a.output, aggregate(a.predictions, a.truth, a.folds))


if __name__ == "__main__":
    main()
