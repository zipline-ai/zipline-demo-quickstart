# Compare model experiments with tracked metrics

This tutorial compares two models already available in the public demo to answer:
**does adding shopper-product history improve next-basket prediction?** You will
record both experiments in one trial, run them, and compare their measured
validation AUC and logloss.

| Available model | Full model config name |
| --- | --- |
| Product popularity and overall shopper behavior | `instacart.instacart.instacart_basket_baseline__19ca8c1c152c` |
| The same features plus shopper-product history and ratios | `instacart.instacart.instacart_basket_model__19ca8c1c152c` |

Both models and their trainer bundles are already prepared. You do not need S3
copy or upload permissions for this tutorial. If you would like to try another
model, a Zipline employee will be happy to help upload it on request.

Complete the [pipeline setup](../instacart.md) first, or confirm it has already
been completed for your demo. The training Join must be materialized for
**2026-08-18 through 2026-08-24**. You need the Zipline CLI and a demo login.

## 1. Configure hosted authentication

Start from a clean, pushed checkout of this repository:

```bash
cd configs
export ZIPLINE_AUTH_URL=https://try.zipline.ai
```

Set `ZIPLINE_TOKEN` to your hosted-demo token using your shell's secret-loading
mechanism. Keep it out of committed files and command output. `ZIPLINE_AUTH_URL`
is the frontend URL, not the Hub service path.

All remaining shell commands run from `configs/` in this same shell. The checked-in
team configuration supplies the demo Hub URL, AWS provider, and customer; the CLI
uses the `prod` environment by default. No `--hub-url` or `--cloud` arguments are
needed for this repository. Remove any environment overrides pointing at another
deployment before continuing.

## 2. Start or resume a trial

Look for prior attempts first:

```bash
zipline hub trial journal list --run-name instacart-next-basket --format json
zipline hub trial list --run-name instacart-next-basket --format json
```

Use `zipline hub trial show <trial-id>` to inspect an existing attempt. To continue
it, reuse its ID; calling `start` again creates a new attempt even with the same
name. For a new attempt:

```bash
zipline hub trial start instacart-next-basket \
  --task 'Does shopper-product history improve next-basket prediction?' \
  --model instacart.instacart.instacart_basket_model__19ca8c1c152c --format json
export ZIPLINE_TRIAL_ID='<returned-or-resumed-trial-id>'
```

A fresh trial does not automatically contain experiments from another trial. The
following steps record both available models in the selected trial. If resuming,
use `zipline hub trial experiments list "$ZIPLINE_TRIAL_ID" --format json` to check
which experiments already have completed runs and attached reports; skip those
steps rather than starting duplicate runs.

Use the **full model config name** from the table above for `--model` and
`--model-conf-name`, including the team, module, and `__version` suffix. An
experiment ID such as `baseline` is a label within the trial. The short name
`instacart_basket_baseline` is not a model config name. A compiled file path is
used by `backfill`, not by the trial's model-name options.

## 3. Check the training table

```bash
zipline hub eval-table public_demo_data.instacart_instacart_join_v1__1 \
  --team instacart --format json
```

Confirm that it contains the selected model features, label `in_next_basket`, and
partition column `ds`, and that the setup backfill completed for August 18–24.
This command checks the schema, not partition completeness or model quality.
Training-model configs do not support `zipline hub eval`; the completed trainer
report provides the model's evaluation results.

## 4. Record and run the baseline

Record the experiment before submitting training. Both attribution variables
must be on the backfill command, with the experiment ID matching its record:

```bash
zipline hub trial experiments record baseline "$ZIPLINE_TRIAL_ID" \
  --title 'Product popularity and shopper behavior' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_baseline__19ca8c1c152c && \
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=baseline \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_baseline__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24
```

The single backfill date chooses the training end date. The models' six-day
lookback gives August 18–24 inclusive, with August 24 held out for validation.
The date assignment holds out whole shoppers on a reconstructed calendar; it does
not establish real chronological generalization.

Wait for the workflow to succeed, then attach its report. Hub reads the trainer's
saved measurements; you do not supply AUC or logloss values yourself. The `&&`
prevents a failed metrics import from marking the experiment successful:

```bash
zipline hub trial experiments metrics baseline "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_baseline__19ca8c1c152c --format json && \
zipline hub trial experiments record baseline "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
```

## 5. Record and run the history model

The second model adds shopper-product history and ratios while keeping the
trainer version, tree depth, learning rate, seed, and training dates the same:

```bash
zipline hub trial experiments record history "$ZIPLINE_TRIAL_ID" \
  --title 'Add shopper-product history and ratios' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_model__19ca8c1c152c && \
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=history \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_model__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24
```

After this workflow succeeds, attach its report:

```bash
zipline hub trial experiments metrics history "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_model__19ca8c1c152c --format json && \
zipline hub trial experiments record history "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
```

## 6. Compare results and close out the trial

```bash
zipline hub trial experiments list "$ZIPLINE_TRIAL_ID" --format json
```

Open the trial in the [demo UI](https://try.zipline.ai). Its experiments appear
alongside one another in AUC/logloss graphs, with links through to the runs.
Compare validation AUC (higher is better) and validation logloss (lower is better).
Higher training AUC alone does not establish an improvement. The configured
acceptance threshold is not a measured result.

After both reports are attached, write the conclusion and journal:

```bash
zipline hub trial summary '<measured validation AUC/logloss comparison and conclusion>' "$ZIPLINE_TRIAL_ID"
zipline hub trial status SUCCEEDED "$ZIPLINE_TRIAL_ID"
zipline hub trial journal append '<what the reports showed and what to try next>' "$ZIPLINE_TRIAL_ID"
```

If a run fails, mark that experiment `FAILED` instead of `SUCCEEDED`. If the
comparison cannot be completed, summarize the blocker, mark the trial `FAILED`,
and append a journal entry. Leave running work running.

## Troubleshooting

Trainer errors appear in the workflow's **Ray (All)** logs.

- **`Model conf ... not found`:** use the full name from the model table. If you
  recorded the wrong name, repeat `experiments record` with the same trial and
  experiment IDs and the correct `--model-conf-name`, then retry importing metrics.
- **`Forbidden` while attaching metrics, or `NoSuchKey` during setup:** contact a
  Zipline employee for help with the prepared model's files. You do not need to
  upload or copy files yourself. Fixing report access does not require retraining
  a successful model.
- **A workflow stays `Submitted`:** check its status and logs before submitting
  again. It may be waiting for demo capacity. If it fails with a startup timeout,
  contact demo support, then repeat the same attributed backfill command after the
  issue is resolved. Do not start duplicate runs while the workflow is active.

## Try another model with Zipline's help

These two models are ready to use. To compare an additional feature set, change
`max-depth` or `eta`, or use another trainer, share your proposed change with a
Zipline employee. They will be happy to help prepare and upload another model
and provide its full config name and compiled path for a new experiment.

Use a distinct model name for each variant. Changing only a trial or experiment
ID does not isolate model outputs; reusing a model name and version can overwrite
its previous report. Coordinate changes to the shared demo models with Zipline
so comparisons retain the intended features, parameters, and reports.
