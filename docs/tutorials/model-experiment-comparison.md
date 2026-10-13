# Iterate on a model and compare experiments

This tutorial takes the existing next-basket model through one experiment:
**does increasing tree depth from 6 to 8 improve validation AUC and logloss?**
The features, trainer bytes, seed, and training dates stay fixed, so the comparison
isolates tree depth. Adding longer history is a separate experiment described below.

Complete the [Instacart pipeline setup](../instacart.md) first. The static Parquet
inputs and original trainer bundles are already in the demo buckets; the training
Join must also be materialized for **2026-08-18 through 2026-08-24**. You need the
Zipline CLI, AWS access to copy trainer archives, and permission to push your branch.

## 1. Create a branch and configure hosted authentication

Start from the repository root with the existing Instacart setup committed and
pushed. Choose your own branch prefix if desired:

```bash
git checkout -b codex/instacart-deeper
cd configs
export ZIPLINE_AUTH_URL=https://try.zipline.ai
export INSTACART_HUB_URL=https://try.zipline.ai/services/hub
```

Set `ZIPLINE_TOKEN` to your hosted-demo token using your shell's secret-loading
mechanism. Keep it out of committed files and command output. `ZIPLINE_AUTH_URL`
is the frontend URL, not the Hub service path. Missing or expired authentication
can send requests to the login page instead of returning API results.

All remaining shell commands run from `configs/` in this same shell. Define a
helper so **every trial command** carries `--cloud aws`, the demo customer, and
the production environment used by `compiled/`:

```bash
trial_cmd() {
  zipline hub trial "$@" --cloud aws --customer-id public-demo --env prod \
    --hub-url "$INSTACART_HUB_URL"
}
```

## 2. Start or resume the trial before making changes

Look for prior attempts first:

```bash
trial_cmd journal list --run-name instacart-iteration --format json
trial_cmd list --run-name instacart-iteration --format json
```

Use `trial_cmd show <trial-id>` to inspect an existing attempt. To continue it,
reuse its ID; calling `start` again creates a new attempt even with the same name.
For a new attempt:

```bash
trial_cmd start instacart-iteration \
  --task 'Does max-depth 8 improve next-basket prediction over max-depth 6?' \
  --model instacart.instacart.instacart_basket_model__19ca8c1c152c --format json
export ZIPLINE_TRIAL_ID='<returned-or-resumed-trial-id>'
```

A fresh trial does not automatically contain experiments from another trial.
The following steps train a control and a candidate in this trial, so both appear
in its comparison. If resuming a trial that already has a completed depth-6
history model and attached metrics for the same data and trainer, you can skip
the new control and add only the candidate. The popularity-only model is a
different baseline; comparing against it would change both features and depth.

## 3. Add uniquely named variants

Append this to `models/instacart/instacart.py`. `_variant` constructs a fresh model
and maps the supplied features into both the training and inference definitions.
The existing models remain available.

```python
# New control for this iteration: existing history features and depth 6.
instacart_basket_depth6_r1 = _variant("instacart_basket_depth6_r1", _WITH_HISTORY)

# New candidate: change only tree depth.
instacart_basket_depth8_r1 = _variant("instacart_basket_depth8_r1", _WITH_HISTORY)
instacart_basket_depth8_r1.trainingConf.jobConfigs["max-depth"] = "8"
```

Use unused model names; on later iterations, change `r1` to `r2` (or another
unique suffix) everywhere in the code and commands. Each variant needs both a
unique Python variable and a unique backend `model_name`. Trainer version
`19ca8c1c152c` identifies the unchanged trainer archive, not the hyperparameters.
The model name separates the report locations:

| Variant | Model config name | Artifact/report prefix |
| --- | --- | --- |
| Control | `instacart.instacart.instacart_basket_depth6_r1__19ca8c1c152c` | `s3://zipline-public-demo-artifacts/models/instacart_basket_depth6_r1/19ca8c1c152c/` |
| Candidate | `instacart.instacart.instacart_basket_depth8_r1__19ca8c1c152c` | `s3://zipline-public-demo-artifacts/models/instacart_basket_depth8_r1/19ca8c1c152c/` |

Changing only a trial or experiment ID does not isolate reports. Reusing a model
name/version can overwrite the report from an earlier run.

For a **longer-history feature experiment instead**, create a fresh variant with
an additional feature that the existing Join already emits:

```python
_WITH_LONGER_HISTORY = _WITH_HISTORY + [
    ("user_id_product_id_order_id_count_365d", "pair_count_365d"),
]
instacart_basket_long_history_r1 = _variant(
    "instacart_basket_long_history_r1", _WITH_LONGER_HISTORY
)
```

Keep tree depth unchanged for that comparison and use its new name throughout
the archive and trial commands. To test learning rate instead, change only
`trainingConf.jobConfigs["eta"]` on a fresh variant. Features absent from the Join
require versioning and validating their upstream configs and materializing the
new training table before training; a model-only change cannot create them.

## 4. Copy the trainer archives, compile, commit, and push

Ray resolves archives by **model name and trainer version**, so each new name
needs its own object even though the bytes are identical:

```bash
aws s3 cp \
  s3://zipline-public-demo-artifacts/builds/instacart_basket_model-19ca8c1c152c.zip \
  s3://zipline-public-demo-artifacts/builds/instacart_basket_depth6_r1-19ca8c1c152c.zip
aws s3 cp \
  s3://zipline-public-demo-artifacts/builds/instacart_basket_model-19ca8c1c152c.zip \
  s3://zipline-public-demo-artifacts/builds/instacart_basket_depth8_r1-19ca8c1c152c.zip
zipline compile

git add models/instacart/instacart.py \
  compiled/models/instacart/instacart.instacart_basket_depth6_r1__19ca8c1c152c \
  compiled/models/instacart/instacart.instacart_basket_depth8_r1__19ca8c1c152c
git diff --cached
git commit -m "Add Instacart tree-depth experiment"
git push -u origin HEAD
```

Review the compiler output for those exact names. Hub requires a clean, pushed
branch so workers can reproduce the configs. Evaluate both compiled models after
pushing, and resolve evaluation failures before submitting training:

```bash
zipline hub eval compiled/models/instacart/instacart.instacart_basket_depth6_r1__19ca8c1c152c \
  --hub-url "$INSTACART_HUB_URL"
zipline hub eval compiled/models/instacart/instacart.instacart_basket_depth8_r1__19ca8c1c152c \
  --hub-url "$INSTACART_HUB_URL"
```

## 5. Record each experiment, then submit its training backfill

The record must exist before submission. Include **both** attribution variables
on each command, with the experiment ID matching its record:

```bash
trial_cmd experiments record exp-control "$ZIPLINE_TRIAL_ID" \
  --title 'History model, depth 6' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_depth6_r1__19ca8c1c152c
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=exp-control \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_depth6_r1__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24 --hub-url "$INSTACART_HUB_URL"

trial_cmd experiments record exp-deeper "$ZIPLINE_TRIAL_ID" \
  --title 'History model, depth 8' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_depth8_r1__19ca8c1c152c
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=exp-deeper \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_depth8_r1__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24 --hub-url "$INSTACART_HUB_URL"
```

The single backfill date chooses the training end date. These models' six-day
lookback gives August 18–24 inclusive, with August 24 held out for validation.
The date assignment holds out whole shoppers on a reconstructed calendar.

## 6. Attach measured results and inspect the trial

Wait for each training workflow and its report to finish. Submission success
alone is not training success. Hub reads metrics from the trainer's own report;
you do not supply AUC or logloss values yourself:

```bash
trial_cmd experiments metrics exp-control "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_depth6_r1__19ca8c1c152c --format json
trial_cmd experiments metrics exp-deeper "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_depth8_r1__19ca8c1c152c --format json
```

Only after each job succeeds and its report is attached, mark it successful:

```bash
trial_cmd experiments record exp-control "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
trial_cmd experiments record exp-deeper "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
trial_cmd experiments list "$ZIPLINE_TRIAL_ID" --format json
```

Open the trial in the [demo UI](https://try.zipline.ai). Its experiments appear
alongside one another in AUC/logloss graphs, with links through to the runs.
Compare validation AUC (higher is better) and validation logloss (lower is better).
A deeper model can overfit; higher training AUC alone does not establish an
improvement. The configured acceptance threshold is not a measured result.

Trainer errors appear in the workflow's **Ray (All)** logs. `NoSuchKey` during
runtime setup commonly means the archive for the new model name is missing.
Missing feature-column errors require checking the materialized Join schema.
For a failed candidate, record the failure instead of the success command above:

```bash
trial_cmd experiments record exp-deeper "$ZIPLINE_TRIAL_ID" --status FAILED
```

## 7. Close out the attempt before the next iteration

After a complete, report-backed comparison, write the conclusion and journal:

```bash
trial_cmd summary '<measured validation AUC/logloss comparison and conclusion>' "$ZIPLINE_TRIAL_ID"
trial_cmd status SUCCEEDED "$ZIPLINE_TRIAL_ID"
trial_cmd journal append '<what changed, what the reports showed, and what to try next>' "$ZIPLINE_TRIAL_ID"
```

If the comparison failed, summarize the blocker, use `trial_cmd status FAILED
"$ZIPLINE_TRIAL_ID"`, and still append the journal entry. Leave running work
running. On the next iteration, search the journal again and choose fresh model
names before changing a feature or hyperparameter.
