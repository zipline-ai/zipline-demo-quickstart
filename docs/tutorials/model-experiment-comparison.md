# Compare two models in a trial

Does shopper-product history improve next-basket prediction? Compare the two
models available in the public demo:

- **Baseline:** product popularity and overall shopper behavior.
- **History:** the baseline features plus shopper-product history and ratios.

You'll track both in one trial and compare validation AUC and logloss. Both models
are ready to use. A Zipline employee will be happy to help upload another model
on request.

Before starting, complete the [pipeline setup](../instacart.md), or confirm your
demo already has training data for **August 18–24, 2026**.

## 1. Start a trial

Use a clean, pushed checkout with the Zipline CLI installed and your demo token
in `ZIPLINE_TOKEN`. Run these commands from the repository root:

```bash
cd configs
export ZIPLINE_AUTH_URL=https://try.zipline.ai

BASELINE=instacart.instacart.instacart_basket_baseline__19ca8c1c152c
HISTORY=instacart.instacart.instacart_basket_model__19ca8c1c152c

zipline hub trial journal list --run-name instacart-next-basket
zipline hub trial start instacart-next-basket \
  --task 'Does shopper-product history improve next-basket prediction?' \
  --model "$HISTORY"
```

Copy the returned trial ID below. To resume an existing trial, use its ID instead
of starting another. Keep this shell open for the remaining steps.

```bash
export ZIPLINE_TRIAL_ID='<trial-id>'
```

## 2. Run the baseline

Record the experiment, then submit training:

```bash
zipline hub trial experiments record baseline "$ZIPLINE_TRIAL_ID" \
  --title 'Product popularity and shopper behavior' \
  --status RUNNING --model-conf-name "$BASELINE" && \
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=baseline \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_baseline__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24
```

Wait for the workflow to succeed in the [demo UI](https://try.zipline.ai), then
attach its metrics:

```bash
zipline hub trial experiments metrics baseline "$ZIPLINE_TRIAL_ID" \
  --model-conf-name "$BASELINE" && \
zipline hub trial experiments record baseline "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
```

## 3. Run the history model

This model uses the same trainer settings and dates, with additional history
features:

```bash
zipline hub trial experiments record history "$ZIPLINE_TRIAL_ID" \
  --title 'Add shopper-product history' \
  --status RUNNING --model-conf-name "$HISTORY" && \
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=history \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_model__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24
```

Wait for this workflow to succeed, then attach its metrics:

```bash
zipline hub trial experiments metrics history "$ZIPLINE_TRIAL_ID" \
  --model-conf-name "$HISTORY" && \
zipline hub trial experiments record history "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
```

Both models train on August 18–23 and validate on August 24, which holds out a
separate set of shoppers. Hub reads the saved trainer reports when you attach
metrics.

## 4. Compare the results

Open your trial in the [demo UI](https://try.zipline.ai) to see both experiments,
their AUC/logloss graphs, and links to the training runs:

- **Validation AUC:** higher is better.
- **Validation logloss:** lower is better.

Record what you learned after both experiments succeed:

```bash
zipline hub trial experiments list "$ZIPLINE_TRIAL_ID"
zipline hub trial summary '<which model performed better, with AUC and logloss>' "$ZIPLINE_TRIAL_ID"
zipline hub trial status SUCCEEDED "$ZIPLINE_TRIAL_ID"
zipline hub trial journal append '<what you learned and what to try next>' "$ZIPLINE_TRIAL_ID"
```

If a run fails, check its **Ray (All)** logs and record that experiment as
`FAILED` instead. Ask a Zipline employee for help with a stuck run or to try
another model.
