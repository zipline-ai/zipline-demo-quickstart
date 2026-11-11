import contextlib, io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import torch
from transformers import GPT2Config, GPT2LMHeadModel
import trainer.core as runner


class InterruptedResumeTests(unittest.TestCase):
    def test_interrupted_optimizer_and_dropout_rng_resume_matches_uninterrupted(self):
        torch.manual_seed(3)
        config = GPT2Config(
            vocab_size=32,
            n_positions=16,
            n_embd=8,
            n_layer=1,
            n_head=2,
            bos_token_id=0,
            eos_token_id=0,
        )
        initial = GPT2LMHeadModel(config).state_dict()

        class Encoder:
            features = ["x"]
            tok = SimpleNamespace(eos_token_id=0)

            def build(self, row, label, order, source=False, eos=True):
                return [1, 2 + int(label), 5 + row % 20, 0]

        labels = np.arange(405) % 2
        with TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            common = dict(device="cpu", microbatch=1, accumulation=2, epochs=1, lr=5e-5)
            complete = GPT2LMHeadModel(config)
            complete.load_state_dict(initial)
            args = SimpleNamespace(output=Path(tmp) / "full", **common)
            args.output.mkdir()
            runner.train_stage(complete, Encoder(), labels, "source", args)
            interrupted = GPT2LMHeadModel(config)
            interrupted.load_state_dict(initial)
            args2 = SimpleNamespace(output=Path(tmp) / "resume", **common)
            args2.output.mkdir()
            real_save = runner.save_checkpoint

            def stop_after_save(path, model, opt, next_step, device):
                real_save(path, model, opt, next_step, device)
                raise RuntimeError("simulated interruption")

            with patch.object(runner, "save_checkpoint", side_effect=stop_after_save):
                with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                    runner.train_stage(interrupted, Encoder(), labels, "source", args2)
            restarted = GPT2LMHeadModel(config)
            report = runner.train_stage(restarted, Encoder(), labels, "source", args2)
            self.assertEqual(report["initial_step_this_process"], 200)
            for key, expected in complete.state_dict().items():
                torch.testing.assert_close(
                    restarted.state_dict()[key], expected, atol=0, rtol=0
                )


if __name__ == "__main__":
    unittest.main()
