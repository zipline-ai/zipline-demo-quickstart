import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import numpy as np
import pandas as pd
import torch
from transformers import GPT2Config, GPT2LMHeadModel, AutoTokenizer
from trainer.core import RowEncoder, conditional_log_likelihood, train_stage

WEIGHTS = Path(__import__("os").environ.get("GPT2_WEIGHTS", "/opt/gpt2"))


class GPTPilotTests(unittest.TestCase):
    def test_exact_tokenization_and_label_not_in_feature_tables(self):
        tok = AutoTokenizer.from_pretrained(WEIGHTS, local_files_only=True)
        frame = pd.DataFrame(
            {
                "amount_usd": [1.0, 32.17],
                "used_vpn": [True, False],
                "merchant_category": ["Travel", "Online Retail"],
                "is_fraud": [0, 1],
            }
        )
        enc = RowEncoder(tok, frame, ["amount_usd", "used_vpn", "merchant_category"])
        enc.check()
        self.assertNotIn("is_fraud", enc.frame)
        changed = RowEncoder(tok, frame.assign(is_fraud=[1, 0]), enc.features)
        self.assertEqual(enc.build(0, 1, [2, 0, 1]), changed.build(0, 1, [2, 0, 1]))
        with self.assertRaises(ValueError):
            enc.build(0, 0, [0] * 2000)

    def test_raw_value_spellings(self):
        from trainer.core import value_string

        self.assertEqual(
            [value_string(v) for v in [36, 36.0, 0.0, True, False, None, float("nan")]],
            ["36", "36.0", "0.0", "True", "False", "None", "None"],
        )
        tok = AutoTokenizer.from_pretrained(WEIGHTS, local_files_only=True)
        frame = pd.DataFrame(
            {"age": [36], "amount": [0.0], "flag": [True], "missing": [None]}
        )
        enc = RowEncoder(tok, frame, list(frame))
        enc.check()
        self.assertEqual(
            enc.build(0, 1, [0, 1, 2, 3]),
            tok.encode(
                "is_fraud is True, age is 36, amount is 0.0, flag is True, missing is None",
                add_special_tokens=False,
            ),
        )

    def test_likelihood_masks_prefix_and_padding_and_matches_manual(self):
        torch.manual_seed(4)
        model = GPT2LMHeadModel(
            GPT2Config(
                vocab_size=32,
                n_positions=32,
                n_embd=16,
                n_layer=1,
                n_head=2,
                attn_pdrop=0.0,
                embd_pdrop=0.0,
                resid_pdrop=0.0,
            )
        ).eval()
        seqs = [[1, 2, 3, 4, 5], [1, 7, 8, 9]]
        prefix = [2, 3]
        got = conditional_log_likelihood(model, seqs, prefix, 0, "cpu")
        for i, (seq, npre) in enumerate(zip(seqs, prefix)):
            with torch.no_grad():
                ids = torch.tensor([seq])
                lp = model(ids).logits.log_softmax(-1)
                expected = sum(
                    float(lp[0, t - 1, seq[t]]) for t in range(npre, len(seq))
                )
            self.assertAlmostEqual(got[i], expected, places=5)
            single = conditional_log_likelihood(model, [seq], [npre], 0, "cpu")[0]
            self.assertAlmostEqual(got[i], single, places=5)

    def test_real_cpu_training_and_completed_checkpoint_resume(self):
        torch.manual_seed(2)
        config = GPT2Config(
            vocab_size=32,
            n_positions=32,
            n_embd=16,
            n_layer=1,
            n_head=2,
            attn_pdrop=0.0,
            embd_pdrop=0.0,
            resid_pdrop=0.0,
        )
        model = GPT2LMHeadModel(config)

        class Encoder:
            features = ["x"]
            tok = SimpleNamespace(eos_token_id=0)

            def build(self, row, label, order, source=False, eos=True):
                return [1, 2 + int(label), 5 + row, 0]

        with TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                output=Path(tmp),
                device="cpu",
                microbatch=2,
                accumulation=2,
                epochs=1,
                lr=5e-5,
            )
            before = model.transformer.wte.weight.detach().clone()
            report = train_stage(
                model, Encoder(), np.array([0, 1, 0, 1, 0]), "source", args
            )
            self.assertEqual(report["optimizer_steps"], 2)
            self.assertFalse(torch.equal(before, model.transformer.wte.weight))
            expected = {k: v.clone() for k, v in model.state_dict().items()}
            fresh = GPT2LMHeadModel(config)
            train_stage(fresh, Encoder(), np.array([0, 1, 0, 1, 0]), "source", args)
            for k, v in fresh.state_dict().items():
                torch.testing.assert_close(v, expected[k], rtol=0, atol=0)
            path = Path(tmp) / "source/report.json"
            r = json.loads(path.read_text())
            r["checkpoint_sha256"] = "wrong"
            path.write_text(json.dumps(r))
            with self.assertRaises(ValueError):
                train_stage(fresh, Encoder(), np.array([0, 1, 0, 1, 0]), "source", args)


if __name__ == "__main__":
    unittest.main()
