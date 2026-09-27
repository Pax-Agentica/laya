---
license: apache-2.0
library_name: onnx
tags:
  - onnx
  - onnxruntime
  - decision-model
  - system-one
  - logical-fallacy
  - modernbert
---

# laya-fallacies — ONNX export

ONNX export of the `laya-fallacies` fine-tune — ModernBERT-large plus Laya's
decision head, fine-tuned on a 14-way logical-fallacy taxonomy — for use with [`@receptron/laya`](https://www.npmjs.com/package/@receptron/laya)
from Bun, or with ONNX Runtime directly.

This export is a derivative of two Apache-2.0 works: the upstream [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya)
checkpoint that the fine-tune descends from, and the [ModernBERT-large](https://huggingface.co/answerdotai/ModernBERT-large)
encoder inside it.

| File | Contents |
| --- | --- |
| `laya.onnx` / `laya.onnx.data` | graph + fp32 weights (~1.7 GB) |
| `laya_config.json` | `max_len`, `head_max_len` and the per-type temperatures from `rl_agent_config.json` |
| `tokenizer/` | the checkpoint's tokenizer |

Inputs: `input_ids` [B,L] int64, `attention_mask` [B,L] int64, `marker_pos` [B,K]
int64, `marker_mask` [B,K] bool, `qtype` [B] int64. Outputs: `logits` [B,K]
float32 (uncalibrated; masked slots = -1e4), `act_probs` [B,2] float32.

## Usage

```ts
import { Laya } from "@receptron/laya";

// from a local export
const laya = await Laya.load({ modelDir: "./onnx-fallacies" });

// or from this repository, once published
const remote = await Laya.load({ repo: "BryanSnappCTO/laya-fallacies-onnx" });
```

Rebuild the bundle from the weights with `export/export_onnx.py`; the maximum
logit difference against the PyTorch reference is about 2.2e-06.

## Calibration

`laya_config.json` carries the temperatures fitted on 271 held-out calibration
rows after training: `[1.8769, 1.2, 1.2]`. Only the `choice` entry is meaningful
— the fallacy taxonomy is a single `choice` question, so the `score` and `noul`
slices are empty and those two entries keep the script's `1.2` initialisation
default.

The fit is on this checkpoint's own held-out data, so the probabilities are
calibrated for the fallacy task. Re-fit on your own data before relying on them
for a different distribution. See the `laya-fallacies` model card for the
measured accuracy and the full list of caveats.

## Licence

Apache-2.0. The base Laya checkpoint is Convai Innovations', the encoder is
Answer.AI and LightOn's, and both are Apache-2.0. See `LICENSE` for the full
text.
