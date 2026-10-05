---
license: apache-2.0
base_model: convaiinnovations/laya
library_name: onnx
tags:
  - onnx
  - onnxruntime
  - decision-model
  - system-one
  - jev
  - modernbert
---

# Laya — ONNX export

ONNX export of [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya)
(ModernBERT-large encoder + Laya's decision head) for use with [`@receptron/laya`](https://www.npmjs.com/package/@receptron/laya)
from Bun, or with ONNX Runtime directly.

| File | Contents |
| --- | --- |
| `laya.onnx` / `laya.onnx.data` | graph + fp32 weights (English checkpoint, 421M parameters) |
| `laya_config.json` | `max_len`, `head_max_len` and the per-cardinality temperatures from `rl_agent_config.json`; the runtime clamps every temperature to `[0.5, 5]`, and `choice:11+` is refit |
| `tokenizer/` | the checkpoint's tokenizer |

Inputs: `input_ids` [B,L] int64, `attention_mask` [B,L] int64, `marker_pos` [B,K]
int64, `marker_mask` [B,K] bool, `qtype` [B] int64. Outputs: `logits` [B,K]
float32 (uncalibrated; masked slots = -1e4), `act_probs` [B,2] float32.

Built with [`export/export_onnx.py`](https://github.com/receptron/laya/blob/main/export/export_onnx.py);
max logit difference vs. the PyTorch reference ≈ 1e-5.

```ts
import { Laya } from "@receptron/laya";
const laya = await Laya.load(); // downloads this bundle on first use
```

## Calibration

The published bundle shipped `choice:11+ = 0.10058280825614929`, far outside
the `[0.5, 5]` range every other bucket sits in. `systemOne` divides the logits
by that temperature before the softmax, so 11+-option `choice` answers came back
roughly 0.98–1.00 confident whether they were right or wrong. The argmax — and
therefore the chosen answer and the accuracy — was unaffected; only the
confidence was meaningless.

This bundle ships a refit `choice:11+ = 1.03`. It was refit by NLL on 39
hand-labelled 13–15 option "which link matches this goal" questions and checked
on 12 held-out questions from a fourth site: ECE went from 0.336 to 0.122, and
with that temperature the answers at p >= 0.7 were correct 28/29 times across 51
questions (receptron/laya#10).

That refit comes from a small external set, so treat it as a better default than
the shipped value rather than a guarantee. If confidence matters to you, re-fit
on your own labelled data with `scripts/finetune.py --calib-max`. The runtime's
`[0.5, 5]` clamp remains as a safety net for any future checkpoint that ships an
out-of-range temperature.

The `[0.5, 5]` range matches `clamp_temperature` in upstream Python laya
(>= 0.3.5, `laya/common.py`).

Weights are Convai Innovations' and remain under Apache 2.0. This export and the
export code are Apache 2.0 too: <https://github.com/receptron/laya>
