"""Audit immutable CSVs and select persisted IDs; never regenerate folds."""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .storage import download, fingerprint, write_json

REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
ROOT_URI = "s3://zipline-artifacts-crucible/gpt2-s6e11"


def audit(paths, features):
    train, test, source, folds = [
        pd.read_csv(paths[n]) for n in ("train", "test", "source", "folds")
    ]
    split = json.loads(Path(paths["split"]).read_text())
    if (
        fingerprint(paths["train"]) != split["contract"]["train_sha256"]
        or fingerprint(paths["folds"]) != split["folds_sha256"]
    ):
        raise ValueError("Persisted split hashes differ")
    if (len(train), len(test), len(source), len(features)) != (
        699960,
        299984,
        20000,
        24,
    ):
        raise ValueError("Unexpected dataset dimensions")
    if set(train) != set(features) | {"id", "is_fraud"} or set(source) != set(
        features
    ) | {"transaction_id", "is_fraud"}:
        raise ValueError("Predictor schema differs")
    for frame, key in [
        (train, "id"),
        (test, "id"),
        (source, "transaction_id"),
        (folds, "id"),
    ]:
        if frame[key].isna().any() or frame[key].duplicated().any():
            raise ValueError("Invalid or duplicate IDs")
    if set(train.id) & set(test.id) or not np.array_equal(folds.id, train.id):
        raise ValueError("Competition/split ID mismatch")
    if "is_fraud" in folds and not np.array_equal(folds.is_fraud, train.is_fraud):
        raise ValueError("Split label mismatch")
    if folds.fold.value_counts().to_dict() != dict.fromkeys(range(5), 139992):
        raise ValueError("Invalid fold coverage")
    # Same exact relational exclusion as the verified pilot, without coercing values.
    keys = pd.concat(
        [train[features], test[features]], ignore_index=True
    ).drop_duplicates()
    marked = source.merge(
        keys.assign(_competition_match=True),
        on=features,
        how="left",
        validate="many_to_one",
    )
    eligible = marked.loc[marked._competition_match.isna(), source.columns].reset_index(
        drop=True
    )
    if len(eligible) != 20000 or not np.array_equal(
        eligible.transaction_id, pd.read_csv(paths["source_ids"]).transaction_id
    ):
        raise ValueError("Eligible source IDs changed after overlap exclusion")
    train_ids, valid_ids = [
        pd.read_csv(paths[n]).id for n in ("training_ids", "validation_ids")
    ]
    if (
        len(train_ids) != 20000
        or len(valid_ids) != 10000
        or train_ids.duplicated().any()
        or valid_ids.duplicated().any()
    ):
        raise ValueError("Pilot sample IDs changed")
    f = folds.set_index("id").fold
    if (
        set(train_ids) & set(valid_ids)
        or not (f.loc[train_ids] != 0).all()
        or not (f.loc[valid_ids] == 0).all()
    ):
        raise ValueError("Training/held-out leakage")
    pilot = pd.read_csv(paths["pilot_predictions"])
    valid = train.set_index("id").loc[valid_ids]
    if not np.array_equal(pilot.id, valid_ids) or not np.array_equal(
        pilot.is_fraud, valid.is_fraud
    ):
        raise ValueError("Saved prediction scope differs")
    return train, eligible, folds, train_ids, valid_ids


def load(manifest, cache, fold=0, sampled=True):
    paths = {
        k: download(v["uri"], Path(cache) / (k + Path(v["uri"]).suffix), v["sha256"])
        for k, v in manifest["files"].items()
    }
    train, source, folds, tid, vid = audit(paths, manifest["features"])
    if sampled and fold != 0:
        raise ValueError("Saved pilot is fold 0 only")
    if not sampled:
        tid, vid = (
            train.loc[folds.fold != fold, "id"],
            train.loc[folds.fold == fold, "id"],
        )
    indexed = train.set_index("id", drop=False)
    return (
        source,
        indexed.loc[tid].reset_index(drop=True),
        indexed.loc[vid].reset_index(drop=True),
        paths,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--competition", type=Path, required=True)
    p.add_argument(
        "--reference",
        type=Path,
        required=True,
        help="modelpg competition directory (read only)",
    )
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    pilot = a.reference / "outputs/gpt2-pilot-v1"
    reference = json.loads((pilot / "config.json").read_text())
    files = {n: a.competition / (n + ".csv") for n in ("train", "test")}
    files.update(
        source=a.reference / "data/source/credit_card_fraud_2026.csv",
        folds=a.reference / "validation/stratified-5fold-seed42/folds.csv",
        split=a.reference / "validation/stratified-5fold-seed42/manifest.json",
        pilot_predictions=pilot / "evaluation/validation.csv",
    )
    files.update(
        {
            n: pilot / (n + ".csv")
            for n in ("training_ids", "validation_ids", "source_ids")
        }
    )
    if (
        any(
            fingerprint(files[n]) != reference["input_sha256"][n + ".csv"]
            for n in ("train", "test")
        )
        or fingerprint(files["source"]) != reference["source_sha256"]
    ):
        raise ValueError("Pilot input bytes changed")
    audit(files, reference["features"])
    manifest = {
        "schema_version": 1,
        "format": "pilot-pandas-raw-v1",
        "features": reference["features"],
        "model": reference["checkpoint"],
        "pilot_code_sha256": reference["code_sha256"]["fraud_gpt2.py"],
        "rows": {"train": 699960, "test": 299984, "eligible_source": 20000},
        "files": {},
    }
    import shutil

    a.output.mkdir(parents=True, exist_ok=False)
    for key, path in files.items():
        sha = fingerprint(path)
        name = sha + "/" + path.name
        dest = a.output / name
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, dest)
        manifest["files"][key] = {"uri": ROOT_URI + "/data/" + name, "sha256": sha}
    write_json(a.output / "dataset.json", manifest)
    print(
        json.dumps(
            {
                "dataset_sha256": fingerprint(a.output / "dataset.json"),
                "split_sha256": fingerprint(files["split"]),
                "audited": True,
            }
        )
    )


if __name__ == "__main__":
    main()
