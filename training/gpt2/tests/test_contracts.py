import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from trainer.aggregate import aggregate
from trainer.attempt import Publisher
from trainer.metrics import metrics, probabilities
from trainer.storage import fingerprint, write_json


class Contracts(unittest.TestCase):
    def test_mixture_and_prior(self):
        ll = np.log(np.array([[[0.8, 0.2], [0.1, 0.9]], [[0.4, 0.6], [0.2, 0.8]]]))
        p = probabilities(ll, "reference_no_prior", 0.1)
        np.testing.assert_allclose(p, [1.1 / 2, 1.4 / 2])
        np.testing.assert_allclose(
            probabilities(ll, "fold_training_prior", 0.2),
            expit(np.log(p / (1 - p)) + np.log(0.2 / 0.8)),
        )
        with self.assertRaises(ValueError):
            probabilities(ll, "implicit", 0.1)
        with self.assertRaises(ValueError):
            probabilities(ll * np.nan, "reference_no_prior", 0.1)

    def test_reject_invalid_metrics(self):
        for y, p in [
            ([1, 1], [0.2, 0.3]),
            ([0, 1], [0.1, np.nan]),
            ([0, 1], [-0.1, 0.4]),
            ([0, 1], [0.5]),
            ([], []),
        ]:
            with self.assertRaises(ValueError):
                metrics(y, p)

    def fixture(self, root):
        truth = pd.DataFrame(
            {"id": range(10), "fold": np.repeat(range(5), 2), "is_fraud": [0, 1] * 5}
        )
        tp = root / "truth.csv"
        truth.to_csv(tp, index=False)
        paths = []
        for fold in range(5):
            frame = truth[truth.fold == fold].copy()
            # Perfect within folds, offset across folds => pooled AUC != mean AUC.
            frame["prediction"] = [0.02 + fold * 0.19, 0.03 + fold * 0.19]
            path = root / f"fold{fold}.csv"
            frame.to_csv(path, index=False)
            paths.append(path)
            write_json(
                path.with_suffix(".json"),
                {
                    "complete": True,
                    "scope": "full_fold",
                    "fold": fold,
                    "predictions_sha256": fingerprint(path),
                    "dataset_manifest_hash": "a" * 64,
                    "split_manifest_hash": "b" * 64,
                    "recipe": {"prior": "none"},
                    "model_revision": "pin",
                    "trainer_code_version": "code",
                    "training_image": "image",
                },
            )
        return tp, paths

    def test_pooled_oof_and_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            truth, paths = self.fixture(root)
            result = aggregate(paths, truth)
            self.assertEqual(result["oof_rows"], 10)
            self.assertLess(result["oof_auc"], 1.0)
            with self.assertRaises(ValueError):
                aggregate(paths[:-1], truth)
            with self.assertRaises(ValueError):
                aggregate(paths[:4] + [paths[0]], truth)
            frame = pd.read_csv(paths[0])
            frame.loc[1, "id"] = frame.loc[0, "id"]
            frame.to_csv(paths[0], index=False)
            m = json.loads(paths[0].with_suffix(".json").read_text())
            m["predictions_sha256"] = fingerprint(paths[0])
            write_json(paths[0].with_suffix(".json"), m)
            with self.assertRaises(ValueError):
                aggregate(paths, truth)

    def test_incompatible_partial_and_wrong_labels(self):
        for change in [
            {"scope": "sampled_fold0_10k"},
            {"complete": False},
            {"recipe": {"prior": "different"}},
            {"training_image": "different"},
        ]:
            with tempfile.TemporaryDirectory() as d:
                truth, paths = self.fixture(Path(d))
                p = paths[0].with_suffix(".json")
                m = json.loads(p.read_text())
                m.update(change)
                write_json(p, m)
                with self.assertRaises(ValueError):
                    aggregate(paths, truth)
        with tempfile.TemporaryDirectory() as d:
            truth, paths = self.fixture(Path(d))
            frame = pd.read_csv(truth)
            frame["is_fraud"] = 1 - frame.is_fraud
            frame.to_csv(truth, index=False)
            with self.assertRaises(ValueError):
                aggregate(paths, truth)

    def test_publication_durability_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            local = root / "local"
            local.mkdir()
            context = {
                k: "test"
                for k in (
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
            }
            context["artifact_root"] = str(root / "remote")
            publisher = Publisher(context, local)
            publisher.progress("training", force=True, measurements={"lm_loss": 1.0})
            pointer = json.loads((root / "remote/progress/latest.json").read_text())
            batch = json.loads((root / "remote/progress/000000000001.json").read_text())
            self.assertEqual(pointer["sequence"], batch["sequence"])
            publisher.report(metrics([0, 1], [0.2, 0.8]), "synthetic", [])
            with self.assertRaises(FileExistsError):
                publisher.report(metrics([0, 1], [0.2, 0.8]), "synthetic", [])


class ResumeIdentity(unittest.TestCase):
    def test_source_reuse_is_fold_independent_but_classifier_is_not(self):
        from trainer.train import resume_compatible

        recipe = json.loads(
            (
                Path(__file__).resolve().parents[1] / "presets/reference_small.json"
            ).read_text()
        )
        saved = {
            "recipe": recipe,
            "training_image": "digest",
            "dataset_manifest_hash": "dataset",
        }
        current = {**saved, "recipe": {**recipe, "fold": 1}}
        self.assertTrue(resume_compatible(saved, current, "source"))
        self.assertFalse(resume_compatible(saved, current, "competition"))
        current["recipe"]["source_epochs"] = 8
        self.assertFalse(resume_compatible(saved, current, "source"))
        self.assertFalse(resume_compatible(saved, saved, "unknown"))


class AttemptIsolation(unittest.TestCase):
    def test_context_identity_and_no_shared_output_fallback(self):
        import os
        from unittest.mock import patch
        from trainer.attempt import context_from_env

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "context.json"
            context = {
                k: "test"
                for k in (
                    "trial_id",
                    "experiment_id",
                    "workflow_id",
                    "step_id",
                    "conf_hash",
                    "dataset_manifest_hash",
                    "split_manifest_hash",
                    "model_conf_name",
                )
            }
            context.update(
                schema_version=1,
                attempt_id="test-1",
                artifact_root="s3://zipline-artifacts-crucible/gpt2-s6e11/runs/test/test/1/",
            )
            write_json(path, context)
            env = {
                "ZIPLINE_RUN_CONTEXT_URI": str(path),
                **{
                    "ZIPLINE_" + k.upper(): context[k]
                    for k in (
                        "trial_id",
                        "experiment_id",
                        "workflow_id",
                        "step_id",
                        "attempt_id",
                        "artifact_root",
                    )
                },
            }
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(context_from_env(context["artifact_root"]), context)
                with self.assertRaises(ValueError):
                    context_from_env(
                        "s3://zipline-artifacts-crucible/gpt2-s6e11/models/shared"
                    )
                os.environ["ZIPLINE_ATTEMPT_ID"] = "different-1"
                with self.assertRaises(ValueError):
                    context_from_env(context["artifact_root"])
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(KeyError):
                    context_from_env(context["artifact_root"])
