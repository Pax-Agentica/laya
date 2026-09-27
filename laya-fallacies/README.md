---
license: apache-2.0
base_model: convaiinnovations/laya
library_name: transformers
language:
  - en
pipeline_tag: text-classification
tags:
  - laya
  - system-one
  - calibrated-decisions
  - logical-fallacy
  - debate
  - modernbert
---

# laya-fallacies

A fine-tune of **[Laya](https://huggingface.co/convaiinnovations/laya)** that
labels a debate statement with the logical fallacy it commits, or `none`. It is
the model behind the fallacy debate detector in [`@receptron/laya`](https://github.com/receptron/laya)
(`examples/debate.ts`).

Laya is a non-autoregressive System 1 decision model: it does not generate text.
You hand it a state and a `choice` question whose options are the taxonomy
below, and it returns one probability per option in a single forward pass.

## Taxonomy

The 14 options are `none` plus the 13 fallacy classes of the training data:

| Label | Meaning |
| --- | --- |
| `none` | no logical fallacy |
| `ad_hominem` | attacking the opponent instead of their argument |
| `ad_populum` | appealing to popularity instead of the merits |
| `appeal_to_emotion` | manipulating emotion instead of engaging with the argument |
| `circular_reasoning` | assuming the conclusion in the premises |
| `equivocation` | using a word in two different senses |
| `fallacy_of_credibility` | leaning on the source's credibility instead of evidence |
| `fallacy_of_extension` | stretching the opponent's claim beyond what it says |
| `fallacy_of_logic` | the reasoning structure itself is invalid |
| `fallacy_of_relevance` | diverting to an issue that is irrelevant |
| `false_causality` | assuming causation from correlation |
| `false_dilemma` | presenting only two options when others exist |
| `faulty_generalization` | concluding from too little evidence |
| `intentional` | rejecting the argument because of the opponent's intent |

The taxonomy is defined at request time, so the option set can be changed
without retraining, as long as it stays within the model's option budget.

## Usage

The package this checkpoint was built for runs the model through ONNX. Export
the bundle first, then load it:

```sh
export/.venv/bin/python export/export_onnx.py ./laya-fallacies ./onnx-fallacies
LAYA_MODEL_DIR=./onnx-fallacies bun examples/debate.ts
```

```ts
import { Laya } from "@receptron/laya";

const laya = await Laya.load({ modelDir: "./onnx-fallacies" });

const result = await laya.systemOne(
  { statement: "You only believe that because you work for the company." },
  {
    fallacy: {
      type: "choice",
      instructions: "which logical fallacy, if any, does this statement commit?",
      criteria: FALLACY_TAXONOMY,
    },
  },
);

result.answers.fallacy.choice; // "ad_hominem"
result.answers.fallacy.probabilities; // one value per label

await laya.close();
```

The forward pass runs on CPU; the ONNX bundle is fp32 and about 1.7 GB.

## Training

`scripts/finetune.py` produced this checkpoint. It is a single-device port
(Apple MPS, no DDP) of the upstream 2xT4 RLCD notebook: policy gradient against
a strictly proper scoring rule (GRPO-style group-mean baseline), with soft
cross-entropy guidance and post-training temperature fitting.

| | |
| --- | --- |
| base checkpoint | `convaiinnovations/laya@1c5edc17a7acd8701df6fc341c0d179f1c62c982` |
| encoder | `answerdotai/ModernBERT-large` (inherited from the base checkpoint) |
| dataset | `tasksource/logical-fallacy@37e9b0537a86e72e9eaf6ee8c9a27d872a944103` (the LOGIC dataset) |
| extra rows | `scripts/negatives.jsonl` (30 sound statements labelled `none`) |
| epochs | 4, AdamW with `lr_encoder 2.5e-5`, `lr_head 1e-4`, cosine decay to `1e-6` |
| `laya` package | `0.3.5` — supplies `build_model`, `build_sequence`, `render_options`, `proper_reward` |

The 2710 labelled sequences split with a fixed seed into 2196 train / 243
validation / 271 calibration rows, so the split is reproducible.
`scripts/train_report_base_run.json` records the same 2196/243 from an earlier
run of this recipe, and this re-run reproduces its test accuracy to within 2
items out of 511.

A second stage was tried and discarded. One further epoch resumed from this
model with the 136 hand-written rows in `scripts/curated.jsonl` added, at a
gentler learning rate (`5e-6` encoder / `1e-5` head), scored **0.4990** on the
test split — 0.6 points below this model and inside noise. An earlier attempt at
the same stage with a larger learning rate (`1e-5`/`5e-5`) over 3 epochs scored
**0.4618**, a 4.3-point regression. Neither earned its place, so the curated
rows are not part of the published weights.

## Evaluation

Measured on this checkpoint, after temperature fitting:

| split | items | accuracy | mean argmax confidence |
| --- | --- | --- | --- |
| validation, held out from the LOGIC train split | 243 | 0.6543 | 0.780 |
| test, the LOGIC `test` split | 511 | 0.5049 | 0.649 |

The fitted per-type temperatures are `[1.8769, 1.2, 1.2]`. Only the `choice`
entry is meaningful: the taxonomy is a single `choice` question, so the `score`
and `noul` calibration slices are empty and those two entries keep the script's
`1.2` initialisation default.

Note the 15-point gap between the two rows. Validation is drawn from the same
pool as training; the test split is not. Expect the test figure on unfamiliar
text.

`train_report.json` in this repository is the raw output of the run.

## Known limitations

1. **The training data's licence is not clearly stated** on the Hub.
   `tasksource/logical-fallacy` lists it as `unknown`; treat the training mix as
   research-only.
2. **Accuracy is 0.5049 on the LOGIC test split.** This is a task-specific
   fine-tune, not a general fallacy detector; validate it on your own data.
3. **The test split was used to select between candidates**, so 0.5049 is a
   mildly optimistic estimate rather than a clean held-out number.
4. **Context-dependent fallacies are the main error mode.** Each debate turn is
   judged in isolation, so fallacies that need the previous turn (straw man,
   `fallacy_of_extension`) are the weakest.
5. **`ad_hominem` is only recognised when the attack is overt.** A
   circumstantial attack ("she says that because her family sells them") tends
   to land on the authority or popularity classes.
6. **English only.** The base English checkpoint collapses on non-Latin scripts.
7. **Fewer than about 20 options** is Laya's own recommendation;
   high-cardinality option sets degrade sharply because options share a fixed
   token budget.
8. **`rl_agent_config.json`'s `training` block is inherited**, not written by
   this fine-tune. `finetune.py` passes the base checkpoint's `training` record
   through unchanged, so its `epochs_completed` and `hours` describe Convai's
   pretraining rather than this run.

## Attribution and licence

This repository is licensed **Apache-2.0**. It is a derivative of two Apache-2.0
works, and redistributes both:

1. **[Laya](https://huggingface.co/convaiinnovations/laya)** — Convai
   Innovations, Apache-2.0. The base checkpoint, including the decision head and
   `rl_common.py`.
2. **[ModernBERT-large](https://huggingface.co/answerdotai/ModernBERT-large)** —
   Answer.AI and LightOn, Apache-2.0. The encoder weights inside the base
   checkpoint.

`laya-fallacies` is an unofficial derivative and is not endorsed by either
project. "Laya" is the name of the upstream model; no trademark rights are
granted by the Apache-2.0 licence.

The fine-tuning pipeline in [`@receptron/laya`](https://github.com/receptron/laya)
is itself a port of the upstream [fine-tuning notebook](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb)
(Apache-2.0). See the accompanying `LICENSE` file for the full licence text.
