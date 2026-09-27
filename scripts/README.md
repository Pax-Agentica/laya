# Fine-tuning Laya

Single-device fine-tuning of a Laya checkpoint on labelled text, based on the
upstream [2xT4 fine-tuning notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb)
(RLCD policy gradient + soft cross-entropy guidance, post-training temperature
calibration), ported to one device — Apple MPS when available, CPU otherwise. No
DDP, no CUDA.

## Layout

- `finetune.py` — the training script; dataset-agnostic, driven by a task file.
- `fallacies.json` — the default task: the `tasksource/logical-fallacy` (LOGIC)
  dataset mapped onto the 14-option fallacy taxonomy used by
  `examples/debate.ts`.
- `negatives.jsonl` — 30 sound statements labelled `none`, added to the training
  mix (the LOGIC dataset only contains fallacious examples).
- `curated.jsonl` — 136 hand-written rows covering all 14 taxonomy labels: the
  targeted examples added to fix specific errors (see *Iterating on the
  debate*).
- `requirements.txt` — the pinned environment used for the published fine-tune.

## Requirements

The Python environment set up by the export README, plus `datasets`:

```sh
uv venv -p 3.12 export/.venv
uv pip install --python export/.venv/bin/python torch transformers safetensors onnx onnxscript onnxruntime huggingface_hub laya datasets
```

`scripts/requirements.txt` pins the exact versions used for the published
fine-tune (see *Reproducing the fallacy fine-tune*).

## Usage

```sh
# 1. time a few real training steps on this machine and project the full run
export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json --dry-run

# 2. fine-tune (writes a rolling checkpoint each epoch, final fp32 model at the end)
export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json --output-dir ./laya-fallacies

# 3. export to ONNX (needs the export/.venv toolchain)
export/.venv/bin/python export/export_onnx.py ./laya-fallacies ./onnx-fallacies

# 4. run the debate example against the fine-tuned model
LAYA_MODEL_DIR=./onnx-fallacies bun examples/debate.ts
```

The script prints a validation accuracy and runs a test-split evaluation at the
end; everything is also written to `<output-dir>/train_report.json`.

## Key options

| flag | default | meaning |
| --- | --- | --- |
| `--device` | `auto` | `mps` if available, else `cpu` |
| `--amp` | off | fp16 autocast + grad scaler on MPS (try both; MPS fp16 can be faster or flaky) |
| `--epochs` | 4 | |
| `--micro-batch` / `--grad-accum` | 8 / 4 | effective batch = product |
| `--max-items` | 0 (all) | cap dataset rows for quick experiments |
| `--calib-max` | 400 | held-out sequences for temperature fitting |
| `--negative-file` | `scripts/negatives.jsonl` | `none` disables |
| `--extra-file` | `scripts/curated.jsonl` | extra `{"statement", "label"}` rows mixed into training; `none` disables |
| `--model-dir` | HF cache or download | any checkpoint with `model.safetensors`, `encoder/`, `tokenizer/`, `rl_agent_config.json` |
| `--finalize-only` | off | skip training: only fit calibration temperatures, save the final fp32 model and evaluate (finishes an interrupted run) |

## Iterating on the debate

`curated.jsonl` is where you add targeted examples to fix specific model errors
(one JSON object per line, label must be a taxonomy key). Watch the debate's
false positives and misses, add rows for those patterns, then resume from the
last checkpoint instead of starting from the base model:

```sh
# continue from the current model, at a lower learning rate
export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json \
    --model-dir ./laya-fallacies --output-dir ./laya-fallacies-next \
    --epochs 3 --lr-encoder 1e-5 --lr-head 5e-5

# re-export and re-run the debate
export/.venv/bin/python export/export_onnx.py ./laya-fallacies-next ./onnx-fallacies
LAYA_MODEL_DIR=./onnx-fallacies bun examples/debate.ts
```

Don't paste the debate's own turns into the data verbatim — keep the debate as
your held-out evaluation and add paraphrases or novel statements of the same
patterns instead.

## Finishing an interrupted run

Each epoch ends with a rolling fp16 checkpoint, and only after the last epoch
does the script fit the calibration temperatures, save the final fp32 model and
run the evaluations. A run stopped inside that tail leaves a checkpoint that
trains and infers but is uncalibrated and unevaluated. `--finalize-only` runs
just the tail against an existing checkpoint:

```sh
export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json \
    --model-dir ./laya-fallacies --output-dir ./laya-fallacies-final --finalize-only \
    --base-revision 1c5edc17a7acd8701df6fc341c0d179f1c62c982
```

The report's `epochs` list is empty, because no epochs ran in that invocation.
Pass `--base-revision` explicitly: a local `--model-dir` cannot imply which
upstream revision the checkpoint descends from, and the field is recorded in
`train_report.json`.

## Using other datasets

Write a new task file with the same shape as `fallacies.json`:

```json
{
  "dataset": "<hf-dataset-id>",
  "revision": "<hf commit sha; optional but recommended>",
  "text_column": "<text field>",
  "label_column": "<label field>",
  "instructions": "which logical fallacy, if any, does this statement commit?",
  "taxonomy": { "none": "no logical fallacy", "some_class": "description" },
  "label_map": { "<dataset label>": "<taxonomy key>" }
}
```

Then run with `--task-file your-task.json`. Keep two things consistent with
inference:

- the taxonomy here and the `FALLACY_TAXONOMY` in `examples/debate.ts` must list
  the same options;
- labels the task file does not map are skipped (and counted in the log).

## Reproducing the fallacy fine-tune

`laya-fallacies` is produced with the values below. The script writes
`<output-dir>/train_report.json`, recording the resolved base revision, the
dataset revision and the package versions that decide the numerics, so a
reproducer can diff their own report against `laya-fallacies/train_report.json`.
An earlier run of the same recipe is kept at
`scripts/train_report_base_run.json` for comparison.

| | |
| --- | --- |
| base checkpoint | `convaiinnovations/laya@1c5edc17a7acd8701df6fc341c0d179f1c62c982` |
| `laya` package | `0.3.5` — supplies `build_model`, `build_sequence`, `render_options`, `proper_reward` |
| dataset | `tasksource/logical-fallacy@37e9b0537a86e72e9eaf6ee8c9a27d872a944103` (licence unclear, see Notes) |
| the rest | the defaults in `scripts/finetune.py`, plus `scripts/negatives.jsonl` and `--extra-file none` |

```sh
export/.venv/bin/python -m pip install -r scripts/requirements.txt
export/.venv/bin/python scripts/finetune.py --task-file scripts/fallacies.json \
    --extra-file none --output-dir ./laya-fallacies \
    --base-revision 1c5edc17a7acd8701df6fc341c0d179f1c62c982
```

`--extra-file none` matters: the published model excludes
`scripts/curated.jsonl`. Adding those 136 rows for one further epoch at a
gentler learning rate (`5e-6`/`1e-5`) scored 0.4990 on the test split against
0.5049 without them, so the curated rows were dropped. The recipe was also
reproduced from the base checkpoint and matched the earlier run's test accuracy
to within 2 items out of 511.

The dataset pin lives in `scripts/fallacies.json` as a `revision` field, so
every run of that task file gets it; `--dataset-revision` overrides it, as
`--base-revision` overrides the checkpoint.

Expect roughly the recorded metrics (val accuracy ≈ 0.654 on 243 items, test
accuracy ≈ 0.505 on 511 items) rather than bit-identical weights: MPS kernels
and the GRPO noise draw are not deterministic even with the seeds fixed. The
data split and ordering *are* exact.

The remaining gap is that the decision head, the prompt layout and
`proper_reward` live in the external `laya` package rather than in this repo.
Pinning `laya==0.3.5` freezes them, but vendoring `laya.common` / `laya.agent`
here would remove the dependency entirely.

## Notes

- The base checkpoint's `choice:11+` temperature is out of calibration range;
  the JS runtime clamps it to `[0.5, 5]` with a warning, and the script refits
  per-type temperatures after training anyway.
- `tasksource/logical-fallacy` is the LOGIC dataset (Jin et al., 2022); its
  license is not clearly stated on the Hub — treat it as research-only. If you
  plan to publish fine-tuned weights, prefer a dataset with a clear licence
  (e.g. a CC-BY one) or collect your own.
- Expect ~30–90 minutes of training for ~2,700 sequences on an M1 Pro (MPS).
  CPU-only is ~10x slower.
- Disk: each fp16 rolling checkpoint is ~0.9GB; the final fp32 model is ~1.7GB.
