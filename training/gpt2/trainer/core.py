"""Pilot math/optimization port; original modelpg fraud_gpt2.py SHA256 in manifest.

Full-weight AdamW, token-weighted microbatch loss, deterministic row/order seeds,
and stage-local linear LR decay. Not a claim of exact legacy GReaT parity.
"""

import gc, json, math, resource, time, sys
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from .storage import fingerprint, write_json


def value_string(v):
    if pd.isna(v):
        return "None"
    return str(v)


class RowEncoder:
    """Fixed pretrained tokenizer only; labels are never stored in feature tables."""

    def __init__(self, tok, frame, features):
        self.tok = tok
        self.features = list(features)
        self.frame = frame[self.features].reset_index(drop=True)
        self.tables = []
        for c in self.features:
            values = self.frame[c].map(value_string)
            codes, unique = pd.factorize(values, sort=False)
            variants = []
            for prefix in ["", " ", ", "]:
                variants.append(
                    tok(
                        [prefix + c + " is " + v for v in unique],
                        add_special_tokens=False,
                    )["input_ids"]
                )
            self.tables.append((codes, *variants))
        self.prefix = [
            tok.encode(f"is_fraud is {label},", add_special_tokens=False)
            for label in ["False", "True"]
        ]
        self.target = {
            space: [
                tok.encode(space + "is_fraud is " + label, add_special_tokens=False)
                for label in ["False", "True"]
            ]
            for space in ["", ", "]
        }

    def build(self, row, label, order, source=False, eos=False):
        if source:
            ids = []
            for pos, j in enumerate(order):
                if j == len(self.features):
                    ids += self.target["" if pos == 0 else ", "][int(label)]
                else:
                    codes, plain, first, later = self.tables[j]
                    ids += (plain if pos == 0 else later)[codes[row]]
        else:
            ids = list(self.prefix[int(label)])
            for pos, j in enumerate(order):
                codes, plain, first, later = self.tables[j]
                ids += (first if pos == 0 else later)[codes[row]]
        if eos:
            ids.append(self.tok.eos_token_id)
        if len(ids) > 1024:
            raise ValueError("Row exceeds GPT-2 context; no silent truncation")
        return ids

    def check(self, seed=0):
        rng = np.random.default_rng(seed)
        for r in rng.choice(len(self.frame), min(32, len(self.frame)), replace=False):
            for source in [False, True]:
                label = int(rng.integers(2))
                order = rng.permutation(len(self.features) + int(source))
                fragments = []
                for j in order:
                    fragments.append(
                        "is_fraud is " + str(bool(label))
                        if j == len(self.features)
                        else self.features[j]
                        + " is "
                        + value_string(self.frame.iloc[r, j])
                    )
                text = (
                    ", ".join(fragments)
                    if source
                    else "is_fraud is " + str(bool(label)) + ", " + ", ".join(fragments)
                )
                if self.build(r, label, order, source) != self.tok.encode(
                    text, add_special_tokens=False
                ):
                    raise ValueError(
                        "Fragment tokenization differs from whole-row tokenization"
                    )


def pad(seqs, eos, device):
    ids = torch.full((len(seqs), max(map(len, seqs))), eos, dtype=torch.long)
    mask = torch.zeros_like(ids)
    for i, s in enumerate(seqs):
        ids[i, : len(s)] = torch.tensor(s)
        mask[i, : len(s)] = 1
    return ids.to(device), mask.to(device)


def conditional_log_likelihood(model, seqs, prefix_lengths, eos, device):
    """Sum only field-token log probabilities; mask label prefix and right padding."""
    ids, mask = pad(seqs, eos, device)
    with torch.inference_mode():
        h = model.transformer(input_ids=ids, use_cache=False).last_hidden_state
        logits = F.linear(h[:, :-1].float(), model.lm_head.weight.float())
        losses = F.cross_entropy(
            logits.reshape(-1, logits.shape[-1]),
            ids[:, 1:].reshape(-1),
            reduction="none",
        ).reshape(len(seqs), -1)
        positions = torch.arange(1, ids.shape[1], device=device)[None, :]
        keep = (
            positions >= torch.tensor(prefix_lengths, device=device)[:, None]
        ) & mask[:, 1:].bool()
        values = (-losses * keep).cpu().numpy().astype(np.float64).sum(axis=1)
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite likelihood")
        return values


def memory(device):
    r = {
        "process_peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1024 if sys.platform == "linux" else 1)
        / 2**30
    }
    if device == "mps":
        r.update(
            mps_allocated_gib=torch.mps.current_allocated_memory() / 2**30,
            mps_driver_gib=torch.mps.driver_allocated_memory() / 2**30,
        )
    if device == "cuda":
        r.update(cuda_peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30)
    return r


def sync(device):
    if device == "mps":
        torch.mps.synchronize()
    if device == "cuda":
        torch.cuda.synchronize()


def save_checkpoint(path, model, opt, next_step, device):
    payload = {
        "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "optimizer": opt.state_dict(),
        "next_step": next_step,
        "torch_rng": torch.get_rng_state(),
    }
    if device == "mps":
        payload["mps_rng"] = torch.mps.get_rng_state().cpu()
    if device == "cuda":
        payload["cuda_rng"] = torch.cuda.get_rng_state_all()
    temp = path.with_suffix(".tmp")
    torch.save(payload, temp)
    temp.replace(path)


def train_stage(model, encoder, labels, name, args):
    d = args.output / name
    d.mkdir(exist_ok=True)
    cp = d / "checkpoint.pt"
    rp = d / "report.json"
    if rp.exists():
        report = json.loads(rp.read_text())
        if fingerprint(cp) != report["checkpoint_sha256"]:
            raise ValueError("Checkpoint checksum mismatch")
        saved = torch.load(cp, map_location=args.device, weights_only=True)
        model.load_state_dict(saved["model"])
        print(name, "completed stage verified/skipped", flush=True)
        return report
    n = len(labels)
    batch = args.microbatch * args.accumulation
    steps = math.ceil(n / batch) * args.epochs
    opt = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=0.0, foreach=False
    )
    start_step = 0
    seed = 42 if name == "source" else 1042
    torch.manual_seed(seed)
    if cp.exists():
        saved = torch.load(cp, map_location=args.device, weights_only=True)
        model.load_state_dict(saved["model"])
        opt.load_state_dict(saved["optimizer"])
        start_step = saved["next_step"]
        if not 0 <= start_step <= steps:
            raise ValueError("Checkpoint step outside configured schedule")
        torch.set_rng_state(saved["torch_rng"].cpu())
        if args.device == "mps":
            torch.mps.set_rng_state(saved["mps_rng"].cpu())
        if args.device == "cuda":
            torch.cuda.set_rng_state_all([s.cpu() for s in saved["cuda_rng"]])
        del saved
        print(name, "resuming at step", start_step, flush=True)
    model.train()
    started = time.perf_counter()
    maximum = memory(args.device)
    first_loss = None
    last_loss = None
    steps_per_epoch = math.ceil(n / batch)
    log = d / "training.jsonl"
    current_epoch = None
    for step in range(start_step, steps):
        epoch, within = divmod(step, steps_per_epoch)
        if epoch != current_epoch:
            permutation = np.random.default_rng(seed + epoch).permutation(n)
            current_epoch = epoch
        rows = permutation[within * batch : min((within + 1) * batch, n)]
        rng = np.random.default_rng(seed + step * 7919)
        seqs = [
            encoder.build(
                int(r),
                labels[r],
                rng.permutation(len(encoder.features) + (name == "source")),
                source=name == "source",
                eos=True,
            )
            for r in rows
        ]
        total_tokens = sum(len(s) - 1 for s in seqs)
        opt.zero_grad(set_to_none=True)
        weighted_loss = 0.0
        for lo in range(0, len(seqs), args.microbatch):
            micro = seqs[lo : lo + args.microbatch]
            ids, mask = pad(micro, encoder.tok.eos_token_id, args.device)
            with torch.autocast(
                device_type=args.device,
                dtype=torch.bfloat16,
                enabled=getattr(args, "bf16", False),
            ):
                loss = model(
                    input_ids=ids,
                    attention_mask=mask,
                    labels=ids.masked_fill(mask == 0, -100),
                    use_cache=False,
                ).loss
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite loss")
            weight = sum(len(s) - 1 for s in micro) / total_tokens
            (loss * weight).backward()
            weighted_loss += loss.detach().item() * weight
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        for group in opt.param_groups:
            group["lr"] = args.lr * (1 - step / steps)
        opt.step()
        sync(args.device)
        last_loss = weighted_loss
        if first_loss is None:
            first_loss = last_loss
        for k, v in memory(args.device).items():
            maximum[k] = max(maximum.get(k, 0), v)
        if (step + 1) % 25 == 0 or step + 1 == steps:
            row = {
                "step": step + 1,
                "total_steps": steps,
                "loss": last_loss,
                "elapsed_this_process_seconds": time.perf_counter() - started,
                "memory": maximum,
            }
            with log.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(name, json.dumps(row), flush=True)
        if (step + 1) % getattr(
            args, "checkpoint_steps", 200
        ) == 0 or step + 1 == steps:
            save_checkpoint(cp, model, opt, step + 1, args.device)
            if getattr(args, "checkpoint_callback", None):
                args.checkpoint_callback(cp, name, step + 1)
        if getattr(args, "progress_callback", None):
            args.progress_callback(name, step + 1, steps, weighted_loss)
    del opt
    gc.collect()
    if args.device == "mps":
        torch.mps.empty_cache()
    report = {
        "status": "complete",
        "rows": n,
        "positives": int(np.sum(labels)),
        "epochs": args.epochs,
        "optimizer_steps": steps,
        "effective_batch_size": batch,
        "initial_step_this_process": start_step,
        "seconds_this_process": time.perf_counter() - started,
        "first_logged_loss_this_process": first_loss,
        "last_loss": last_loss,
        "sampled_memory_max": maximum,
        "checkpoint_sha256": fingerprint(cp),
    }
    write_json(rp, report)
    return report
