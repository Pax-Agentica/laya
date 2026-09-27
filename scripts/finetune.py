#!/usr/bin/env python3
"""Single-device fine-tune of a Laya checkpoint on a labelled text dataset.

A port of the upstream 2xT4 DDP notebook (RLCD policy gradient + soft cross-entropy
guidance, post-training temperature calibration) to one device: Apple MPS when
available, CPU otherwise. No DDP, no CUDA-specific bits.

Usage:
  export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json --dry-run
  export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json \
      --output-dir ./laya-fallacies
  export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json \
      --model-dir ./laya-fallacies --output-dir ./laya-fallacies-final --finalize-only
  export/.venv/bin/python export/export_onnx.py ./laya-fallacies ./onnx-fallacies
  LAYA_MODEL_DIR=./onnx-fallacies bun examples/debate.ts

The task file describes the dataset and the question schema, so the same script
fine-tunes on any single-label text dataset with a new --task-file.
"""
import argparse
import glob
import json
import math
import os
import random
import sys
import time

import numpy as np
import torch

from safetensors.torch import load_file, save_file
from transformers import AutoTokenizer

from laya.agent import _fix_tokenizer_config
from laya.common import QTYPES, build_model, build_sequence, proper_reward, render_options


def parse_args():
    p = argparse.ArgumentParser(description="single-device laya fine-tune")
    p.add_argument("--task-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fallacies.json"))
    p.add_argument("--dataset", help="hf dataset id (default: the task file's)")
    p.add_argument("--dataset-revision", help="pin the hf dataset revision (branch, tag or commit sha)")
    p.add_argument("--split", default="train", help="dataset split used for training")
    p.add_argument("--text-column", help="override the task file's text column")
    p.add_argument("--label-column", help="override the task file's label column")
    p.add_argument("--model-dir", help="checkpoint dir with model.safetensors/encoder/tokenizer (default: hf cache or download)")
    p.add_argument("--base-revision", help="pin the base checkpoint revision (branch, tag or commit sha); recorded in the report")
    p.add_argument("--output-dir", default="./laya-finetuned")
    p.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    p.add_argument("--amp", action="store_true", help="fp16 autocast + grad scaler on mps")
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--micro-batch", type=int, default=8)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--group-size", type=int, default=4, help="grpo baseline samples")
    p.add_argument("--lr-encoder", type=float, default=2.5e-5)
    p.add_argument("--lr-head", type=float, default=1.0e-4)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--sigma-start", type=float, default=0.4)
    p.add_argument("--sigma-end", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-items", type=int, default=0, help="cap dataset rows (0 = all)")
    p.add_argument("--calib-max", type=int, default=400, help="held-out sequences for temperature fitting")
    p.add_argument("--val-frac", type=float, default=0.1, help="fraction of training rows held out for eval")
    p.add_argument("--negative-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "negatives.jsonl"),
                   help="jsonl of {\"statement\": ...} labelled 'none'; use 'none' to disable")
    p.add_argument("--extra-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "curated.jsonl"),
                   help="jsonl of {\"statement\": ..., \"label\": <taxonomy key>} mixed into the training data; use 'none' to disable")
    p.add_argument("--dry-run", action="store_true", help="time a few real training steps and exit")
    p.add_argument("--dry-steps", type=int, default=5)
    p.add_argument("--finalize-only", action="store_true",
                   help="skip training; only fit calibration temperatures, save the final fp32 model and evaluate. "
                        "Use to finish a run that was interrupted after its last epoch's checkpoint")
    return p.parse_args()


def load_task(args):
    with open(args.task_file) as f:
        task = json.load(f)
    task["dataset"] = args.dataset or task["dataset"]
    task["text_column"] = args.text_column or task["text_column"]
    task["label_column"] = args.label_column or task["label_column"]
    # the task file may carry its own dataset pin; an explicit CLI flag wins
    task["revision"] = args.dataset_revision or task.get("revision")
    keys = list(task["taxonomy"].keys())
    assert "none" in keys, "the taxonomy needs a 'none' option for sound statements"
    for label, key in task["label_map"].items():
        assert key in keys, f"label_map target {key!r} for {label!r} is not a taxonomy option"
    return task, keys


BASE_REPO = "convaiinnovations/laya"
CACHE_SNAPSHOTS = os.path.expanduser(f"~/.cache/huggingface/hub/models--{BASE_REPO.replace('/', '--')}/snapshots")


def resolve_model_dir(args):
    if args.model_dir:
        return os.path.abspath(args.model_dir)
    pattern = os.path.join(CACHE_SNAPSHOTS, args.base_revision or "*")
    for cand in sorted(glob.glob(pattern), reverse=True):
        if os.path.exists(os.path.join(cand, "model.safetensors")):
            print(f"using cached checkpoint {cand}")
            return cand
    from huggingface_hub import snapshot_download

    pin = f"@{args.base_revision}" if args.base_revision else " (latest main; pass --base-revision to pin)"
    print(f"downloading {BASE_REPO}{pin}...")
    return snapshot_download(BASE_REPO, revision=args.base_revision)


def snapshot_revision(model_dir):
    """A hf snapshot dir is named after the commit sha; return it when model_dir is one."""
    name = os.path.basename(os.path.normpath(model_dir))
    if len(name) == 40 and all(c in "0123456789abcdef" for c in name):
        return name
    return None


def env_versions():
    """Versions of the packages that decide the numerics, recorded in the training report."""
    import importlib.metadata as metadata

    out = {}
    for pkg in ("laya", "torch", "transformers", "datasets", "safetensors", "numpy"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    return out


def build_items(task, keys, tok, cfg, args):
    """Tokenise every labelled row (and every negative) into one choice-question item."""
    from datasets import load_dataset

    ds = load_dataset(task["dataset"], split=args.split, revision=task["revision"])
    if args.max_items:
        ds = ds.select(range(min(args.max_items, len(ds))))
    question = {"t": "choice", "ins": task["instructions"], "crit": task["taxonomy"]}
    k = len(keys)
    items = []
    skipped = {}
    counts = {}

    def make_item(text, label_key):
        target = [0.0] * k
        target[keys.index(label_key)] = 1.0
        seq, markers = build_sequence(tok, text, question, cfg["max_len"], cfg["head_max_len"])
        if len(markers) != len(render_options(question)):
            return None
        return {"ids": seq, "markers": markers, "qtype": QTYPES["choice"], "target": target, "label": keys.index(label_key)}

    for row in ds:
        text = (row[task["text_column"]] or "").strip()
        if not text:
            continue
        key = task["label_map"].get(row[task["label_column"]])
        if key is None:
            skipped[row[task["label_column"]]] = skipped.get(row[task["label_column"]], 0) + 1
            continue
        counts[key] = counts.get(key, 0) + 1
        item = make_item(text, key)
        if item is not None:
            items.append(item)

    if args.negative_file != "none" and os.path.exists(args.negative_file):
        with open(args.negative_file) as f:
            for line in f:
                row = json.loads(line)
                counts["none"] = counts.get("none", 0) + 1
                item = make_item(row["statement"].strip(), "none")
                if item is not None:
                    items.append(item)

    if args.extra_file != "none" and os.path.exists(args.extra_file):
        with open(args.extra_file) as f:
            for line in f:
                row = json.loads(line)
                key = row["label"]
                if key not in keys:
                    raise SystemExit(f"extra-file label {key!r} is not a taxonomy option")
                counts[key] = counts.get(key, 0) + 1
                item = make_item(row["statement"].strip(), key)
                if item is not None:
                    items.append(item)

    print(f"tokenised {len(items)} items; per-class counts: {json.dumps(counts, indent=1)}")
    if skipped:
        print(f"skipped unmapped labels: {json.dumps(skipped, indent=1)}")
    if not items:
        raise SystemExit("no training items; check the task file's columns and label_map")
    return items


def collate(items, pad_id):
    n = len(items)
    max_len = max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = torch.full((n, max_len), pad_id, dtype=torch.long)
    att = torch.zeros((n, max_len), dtype=torch.long)
    mpos = torch.zeros((n, kmax), dtype=torch.long)
    mmask = torch.zeros((n, kmax), dtype=torch.bool)
    target = torch.zeros((n, kmax), dtype=torch.float32)
    for i, it in enumerate(items):
        ids[i, : len(it["ids"])] = torch.tensor(it["ids"])
        att[i, : len(it["ids"])] = 1
        k = len(it["markers"])
        mpos[i, :k] = torch.tensor(it["markers"])
        mmask[i, :k] = True
        target[i, :k] = torch.tensor(it["target"], dtype=torch.float32)
    return {
        "input_ids": ids,
        "attention_mask": att,
        "marker_pos": mpos,
        "marker_mask": mmask,
        "target": target,
        "qtype": torch.tensor([it["qtype"] for it in items]),
        "label": torch.tensor([it["label"] for it in items]),
    }


def fit_one_temp(sel):
    """LBFGS fit of one scalar temperature on held-out (logits, target) pairs."""
    if len(sel) < 10:
        return 1.0
    kmax = max(len(z) for z, _ in sel)
    big_z = torch.full((len(sel), kmax), -1e4)
    big_t = torch.zeros((len(sel), kmax))
    for i, (z, t) in enumerate(sel):
        big_z[i, : len(z)] = torch.tensor(z)
        big_t[i, : len(t)] = torch.tensor(t, dtype=torch.float32)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = -(big_t * torch.log_softmax(big_z / log_t.exp(), -1)).sum(-1).mean()
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())


def predict_logits(model, items, tok, device, amp, chunk=16):
    """Forward pass logits for eval/calibration, without gradient."""
    out = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(items), chunk):
            batch = collate(items[i : i + chunk], tok.pad_token_id)
            if amp and device == "mps":
                with torch.autocast("mps", dtype=torch.float16):
                    logits, _ = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                                      batch["marker_pos"].to(device), batch["marker_mask"].to(device), batch["qtype"].to(device))
            else:
                logits, _ = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                                  batch["marker_pos"].to(device), batch["marker_mask"].to(device), batch["qtype"].to(device))
            out.extend(logits.float().cpu().numpy())
    model.train()
    return out


def evaluate(model, items, tok, device, amp):
    logits = predict_logits(model, items, tok, device, amp)
    correct = 0
    confs = []
    for it, z in zip(items, logits):
        k = len(it["markers"])
        p = torch.softmax(torch.tensor(z[:k]), -1)
        if int(p.argmax()) == it["label"]:
            correct += 1
        confs.append(float(p.max()))
    n = len(items)
    return {"accuracy": correct / n if n else 0.0, "mean_argmax_confidence": float(np.mean(confs)) if confs else 0.0, "n": n}


def save_checkpoint(model, tok, cfg, out_dir, dtype=torch.float32):
    os.makedirs(out_dir, exist_ok=True)
    save_file({name: tensor.to(dtype).contiguous().cpu() for name, tensor in model.state_dict().items()},
              os.path.join(out_dir, "model.safetensors"))
    model.encoder.config.save_pretrained(os.path.join(out_dir, "encoder"))
    tok.save_pretrained(os.path.join(out_dir, "tokenizer"))
    with open(os.path.join(out_dir, "rl_agent_config.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(out_dir, "rl_common.py"), "w") as f:
        f.write("# shim so export/export_onnx.py can import build_model from rl_common\n"
                "from laya.common import *  # noqa: F401,F403\n")


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)

    task, keys = load_task(args)
    model_dir = resolve_model_dir(args)
    base_revision = snapshot_revision(model_dir) or args.base_revision
    print(f"base checkpoint: {BASE_REPO}@{base_revision or 'unpinned'}")
    _fix_tokenizer_config(model_dir)
    tok = AutoTokenizer.from_pretrained(os.path.join(model_dir, "tokenizer"))

    with open(os.path.join(model_dir, "rl_agent_config.json")) as f:
        cfg = json.load(f)
    cfg["gradient_checkpointing"] = True
    cfg["max_tokens_per_batch"] = 4096
    cfg["max_len"] = 1024
    cfg["head_max_len"] = 256

    items = build_items(task, keys, tok, cfg, args)

    order = list(range(len(items)))
    random.Random(20260922).shuffle(order)
    n_calib = min(args.calib_max, len(items) // 10)
    calib_items = [items[i] for i in sorted(order[:n_calib])]
    rest = [items[i] for i in sorted(order[n_calib:])]
    n_val = int(len(rest) * args.val_frac)
    val_items, train_items = rest[:n_val], rest[n_val:]
    print(f"split: {len(train_items)} train / {len(val_items)} val / {len(calib_items)} calibration")

    device = "mps" if (args.device == "auto" and torch.backends.mps.is_available()) or args.device == "mps" else "cpu"
    print(f"device: {device}, amp: {args.amp and device == 'mps'}")

    model = build_model(cfg, encoder_dir=os.path.join(model_dir, "encoder"))
    model.load_state_dict(load_file(os.path.join(model_dir, "model.safetensors")), strict=True)
    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    model.to(device)
    model.train()

    enc_params = [p for name, p in model.named_parameters() if "encoder." in name]
    head_params = [p for name, p in model.named_parameters() if "encoder." not in name]
    optimizer = torch.optim.AdamW([{"params": enc_params, "lr": args.lr_encoder},
                                   {"params": head_params, "lr": args.lr_head}],
                                  weight_decay=args.weight_decay)
    total_updates = max(1, (len(train_items) // (args.micro_batch * args.grad_accum)) * args.epochs)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_updates, eta_min=1e-6)
    scaler = torch.amp.GradScaler("mps", enabled=True) if (args.amp and device == "mps") else None

    def run_step(chunk, sigma):
        batch = collate(chunk, tok.pad_token_id)
        x = (batch["input_ids"].to(device), batch["attention_mask"].to(device),
             batch["marker_pos"].to(device), batch["marker_mask"].to(device), batch["qtype"].to(device))
        if scaler is not None:
            with torch.autocast("mps", dtype=torch.float16):
                logits, _ = model(*x)
        else:
            logits, _ = model(*x)
        logits = logits.float()
        mask = batch["marker_mask"].to(device)
        k = mask.sum(-1, keepdim=True).float()
        target = batch["target"].to(device)
        eps = torch.randn((args.group_size,) + logits.shape, device=device) * sigma * mask
        eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
        z = logits.detach().unsqueeze(0) + eps
        q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
        with torch.no_grad():
            r = proper_reward(q, target.unsqueeze(0), batch["qtype"].to(device), mask, w_sph=0.75, w_rps=1.0)
            adv = r - r.mean(0, keepdim=True)
            adv = adv / (adv.std() + 1e-6)
        logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma**2)
        loss_rl = -(adv * logp).mean()
        loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
        loss = (loss_rl + 1.0 * loss_ce) / args.grad_accum
        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
        else:
            loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if scaler is not None:
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()
        return loss.item() * args.grad_accum, float(r.mean().item())

    # --dry-run: time real steps and project the full run, then exit
    if args.dry_run:
        probe = train_items[: args.micro_batch * args.grad_accum]
        times = []
        for step in range(args.dry_steps):
            sigma = args.sigma_start + (args.sigma_end - args.sigma_start) * (step / max(1, args.dry_steps - 1))
            optimizer.zero_grad(set_to_none=True)
            t0 = time.time()
            loss, reward = run_step(probe, sigma)
            if step > 0:
                times.append(time.time() - t0)
            print(f"dry step {step + 1}/{args.dry_steps}: loss {loss:.4f} reward {reward:.3f} ({time.time() - t0:.1f}s)")
        avg = float(np.mean(times))
        steps = math.ceil(len(train_items) / (args.micro_batch * args.grad_accum)) * args.epochs
        print(f"\nmeasured {avg:.2f}s per step on {device} ({'amp' if scaler else 'fp32'})")
        print(f"projected full run: {steps} steps x {avg:.2f}s ~= {steps * avg / 60:.1f} minutes "
              f"({len(train_items)} train items, {args.epochs} epochs)")
        return

    report = {"args": vars(args), "base_model": BASE_REPO, "base_revision": base_revision,
              "base_model_dir": model_dir, "dataset": task["dataset"], "dataset_revision": task["revision"],
              "env": env_versions(), "epochs": [], "fitted_temperatures": None, "val": None, "test": None,
              "train_items": len(train_items), "device": device, "amp": bool(scaler)}
    t0 = time.time()
    # --finalize-only finishes a run interrupted after its last checkpoint: no training, just the
    # calibration fit, the final fp32 save and the evaluations below.
    epochs_to_run = 0 if args.finalize_only else args.epochs
    for epoch in range(epochs_to_run):
        random.seed(42 + epoch)
        random.shuffle(train_items)
        epoch_loss, n_batches = 0.0, 0
        optimizer.zero_grad(set_to_none=True)
        accum_step = 0
        progress = epoch / max(1, args.epochs - 1)
        sigma = args.sigma_start + (args.sigma_end - args.sigma_start) * progress
        for b_idx in range(0, len(train_items), args.micro_batch):
            chunk = train_items[b_idx : b_idx + args.micro_batch]
            if not chunk:
                continue
            loss, reward = run_step(chunk, sigma)
            accum_step += 1
            if accum_step % args.grad_accum == 0 or (b_idx + args.micro_batch) >= len(train_items):
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            epoch_loss += loss
            n_batches += 1
            if n_batches % 50 == 0:
                done = epoch * len(train_items) + b_idx
                total = args.epochs * len(train_items)
                eta = (time.time() - t0) / done * (total - done) / 60 if done else 0
                print(f"  epoch {epoch + 1}/{args.epochs} | step {n_batches} | loss {loss:.4f} | "
                      f"reward {reward:.3f} | lr {scheduler.get_last_lr()[0]:.2e} | eta {eta:.0f}m")
        print(f"=== epoch {epoch + 1}/{args.epochs} done in {time.time() - t0:.1f}s | "
              f"avg loss {epoch_loss / max(1, n_batches):.4f} ===")
        report["epochs"].append({"epoch": epoch + 1, "avg_loss": epoch_loss / max(1, n_batches)})
        save_checkpoint(model, tok, cfg, os.path.join(args.output_dir, "checkpoint_latest"), dtype=torch.float16)

    # post-training temperature calibration on the held-out slice
    print("fitting post-training calibration temperatures...")
    calib_preds = []
    for it, z in zip(calib_items, predict_logits(model, calib_items, tok, device, bool(scaler))):
        calib_preds.append((it["qtype"], z[: len(it["markers"])], it["target"]))
    fitted = [1.2, 1.2, 1.2]
    try:
        for qt in range(3):
            sel = [(z, t) for qtype, z, t in calib_preds if qtype == qt]
            if sel:
                fitted[qt] = fit_one_temp(sel)
        print(f"fitted calibration temperatures (choice, score, noul): {[round(t, 3) for t in fitted]}")
    except Exception as exc:  # noqa: BLE001
        print(f"temperature fitting fallback: {exc}")
    report["fitted_temperatures"] = [round(t, 4) for t in fitted]

    # final save in fp32 for the ONNX export, with the fitted temperatures
    cfg = dict(cfg)
    cfg["fine_tuned"] = True
    cfg["model_name"] = os.path.basename(os.path.abspath(args.output_dir))
    cfg["temperature"] = fitted
    cfg.pop("temperature_by_options", None)
    save_checkpoint(model, tok, cfg, args.output_dir, dtype=torch.float32)
    print(f"model saved to {args.output_dir}")

    report["val"] = evaluate(model, val_items, tok, device, bool(scaler))
    print(f"val ({report['val']['n']} items): accuracy {report['val']['accuracy']:.3f}, "
          f"mean argmax confidence {report['val']['mean_argmax_confidence']:.3f}")
    try:
        from datasets import load_dataset

        test_ds = load_dataset(task["dataset"], split="test", revision=task["revision"])
        test_items = []
        for row in test_ds:
            key = task["label_map"].get(row[task["label_column"]])
            if key is None:
                continue
            target = [0.0] * len(keys)
            target[keys.index(key)] = 1.0
            seq, markers = build_sequence(tok, row[task["text_column"]].strip(),
                                          {"t": "choice", "ins": task["instructions"], "crit": task["taxonomy"]},
                                          cfg["max_len"], cfg["head_max_len"])
            if len(markers) == len(keys):
                test_items.append({"ids": seq, "markers": markers, "qtype": QTYPES["choice"],
                                   "target": target, "label": keys.index(key)})
        report["test"] = evaluate(model, test_items, tok, device, bool(scaler))
        print(f"test ({report['test']['n']} items): accuracy {report['test']['accuracy']:.3f}")
    except Exception as exc:  # noqa: BLE001
        print(f"test evaluation skipped: {exc}")

    with open(os.path.join(args.output_dir, "train_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("done")


if __name__ == "__main__":
    main()
