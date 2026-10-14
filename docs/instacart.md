# Instacart next-basket tutorial configs

Follow [compare two models in a trial](tutorials/model-experiment-comparison.md)
to compare the two available models in the trials view. A Zipline employee will be
happy to help upload another model on request; customers do not need S3 copy or
upload permissions.

This is a separate, static-data tutorial under the `instacart` team. It uses the
Instacart Online Grocery Shopping Dataset 2017 (via Kaggle), published for
non-commercial use. See [data sources](data_sources.md) for attribution, Parquet
paths, and trainer archives. The supplied configs are ready to use with the
public demo. Scheduling is disabled; the features and Join are offline only.

## Pipeline and dates

- `staging_queries/instacart/instacart.py`: `orders`, `products`, `purchases`, and
  `candidates`. Static Parquet files are read directly; only dependencies on
  staged tables are declared.
- `group_bys/instacart/instacart.py`: `user_product`, `user`, and `product` history.
- `joins/instacart/instacart_join.py`: `v1` training rows, with candidate row IDs,
  history features, cross-entity ratios, and Join statistics enabled.
- `models/instacart/instacart.py`: `instacart_basket_baseline` and
  `instacart_basket_model`, using the same trainer bytes and separate model names.

All paths above are relative to `configs/`. New pipeline configs start at version
1; both models use the documented demo trainer version `19ca8c1c152c`.

The calendar is fixed at **2026-08-24**. Each shopper's last basket lands on
August 18–24 according to `user_id % 7`; previous baskets retain their actual
inter-order gaps. Purchases are prior baskets only. Labels indicate whether a
previously bought product appears in the train basket. Candidates read the full
static prior catalogue, so an incomplete purchases backfill cannot silently
remove old products from the label population. Train-only products are excluded.

Features use 7/14/45/90/365-day count windows and 365-day rates and recency.
Purchase timestamps are epoch milliseconds in UTC. Join features are read at
midnight on each label date, so same-day prior baskets are excluded by that
cutoff. Product and shopper rates use the 365-day history window.

Train once with end date **2026-08-24**. The six-day lookback passed to the trainer
covers **2026-08-18 through 2026-08-24 inclusive**. August 24 holds out whole
shoppers. This is a shopper holdout on a reconstructed calendar, not evidence of
real chronological generalization. The configured `validation_auc>=0.70` is a
run acceptance threshold, not a measured result. In `job_configs`, it is written
as `"thresholds": "validation_auc:ge:0.70"`, the supported argument syntax.

## Start or resume a tracked comparison

Run from `configs/` with a valid demo login and a clean, pushed branch. Trial
commands inherit the demo URL and AWS provider from the checked-in default team
configuration, so no Hub or cloud arguments are needed.

```bash
trial_cmd() {
  zipline hub trial "$@"
}
trial_cmd journal list --run-name instacart-next-basket --format json
trial_cmd list --run-name instacart-next-basket --format json
```

Inspect matching attempts with `trial_cmd show <trial-id>` and resume an existing
trial when appropriate. Otherwise start one before recording and running the
available models:

```bash
trial_cmd start instacart-next-basket \
  --task 'Does shopper-product history improve next-basket prediction?' \
  --model instacart.instacart.instacart_basket_model__19ca8c1c152c --format json
export ZIPLINE_TRIAL_ID='<returned-or-resumed-trial-id>'
```

## Validate and materialize

Both supplied models and their trainer bundles are already prepared in the public
demo. Their outputs are kept separately. If a model's files are unavailable, ask
a Zipline employee for help; you do not need to inspect or upload S3 objects.

Compile with `zipline compile` and commit any generated changes before running
Hub commands. The current demo's eval service cannot validate the raw Parquet-path
inputs in these staging queries or standalone training-model configs. Use the
staging and Join backfills below to validate execution, then inspect the
materialized training table's schema. A successful compile alone does not validate
the data or train a model.

Materialize orders first; its query writes the entire reconstructed static
calendar. The purchase range below covers the longest feature window, including
an extra boundary day. Products are a standalone dimension for tutorial browsing.
Wait for each upstream backfill to succeed before proceeding.

```bash
zipline hub backfill compiled/staging_queries/instacart/instacart.orders__1 \
  --start-ds 2025-08-17 --end-ds 2026-08-24
zipline hub backfill compiled/staging_queries/instacart/instacart.products__1 \
  --start-ds 2026-08-24 --end-ds 2026-08-24
zipline hub backfill compiled/staging_queries/instacart/instacart.purchases__1 \
  --start-ds 2025-08-17 --end-ds 2026-08-24
zipline hub backfill compiled/staging_queries/instacart/instacart.candidates__1 \
  --start-ds 2026-08-18 --end-ds 2026-08-24
zipline hub backfill compiled/joins/instacart/instacart_join.v1__1 \
  --start-ds 2026-08-18 --end-ds 2026-08-24
```

After those backfills succeed, check the training table:

```bash
zipline hub eval-table public_demo_data.instacart_instacart_join_v1__1 \
  --team instacart --format json
```

Confirm the selected model features, label `in_next_basket`, and partition column
`ds` are present. Schema inspection does not verify partition completeness; also
check that the Join backfill succeeded for the entire requested date range.

## Record and train each experiment

Record each variant before submitting it. Both attribution variables must be on
each model backfill command; the experiment ID must match its preceding record.
The single-day backfill chooses the training end date, not a one-day input window.

```bash
trial_cmd experiments record baseline "$ZIPLINE_TRIAL_ID" \
  --title 'Product popularity and shopper behavior' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_baseline__19ca8c1c152c
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=baseline \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_baseline__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24

trial_cmd experiments record history "$ZIPLINE_TRIAL_ID" \
  --title 'Add shopper-product history and ratios' --status RUNNING \
  --model-conf-name instacart.instacart.instacart_basket_model__19ca8c1c152c
ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID=history \
  zipline hub backfill compiled/models/instacart/instacart.instacart_basket_model__19ca8c1c152c \
  --start-ds 2026-08-24 --end-ds 2026-08-24
```

Wait for both jobs and their reports, then retrieve metrics from the exact model
configs. Mark a failed run `FAILED`; do not mark it successful merely because the
submission returned successfully. The success commands below apply only after
successful completion and report retrieval:

```bash
trial_cmd experiments metrics baseline "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_baseline__19ca8c1c152c --format json && \
trial_cmd experiments record baseline "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
trial_cmd experiments metrics history "$ZIPLINE_TRIAL_ID" \
  --model-conf-name instacart.instacart.instacart_basket_model__19ca8c1c152c --format json && \
trial_cmd experiments record history "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
trial_cmd experiments list "$ZIPLINE_TRIAL_ID" --format json
trial_cmd summary '<conclusion supported by retrieved reports>' "$ZIPLINE_TRIAL_ID"
trial_cmd status SUCCEEDED "$ZIPLINE_TRIAL_ID"
trial_cmd journal append '<measured comparison and remaining limitations>' "$ZIPLINE_TRIAL_ID"
```

## Generated files

Compilation generates these files under `configs/compiled/` (no canary pass is
configured):

```text
teams_metadata/instacart/instacart_team_metadata
staging_queries/instacart/instacart.orders__1
staging_queries/instacart/instacart.products__1
staging_queries/instacart/instacart.purchases__1
staging_queries/instacart/instacart.candidates__1
group_bys/instacart/instacart.user_product__1
group_bys/instacart/instacart.user__1
group_bys/instacart/instacart.product__1
joins/instacart/instacart_join.v1__1
models/instacart/instacart.instacart_basket_baseline__19ca8c1c152c
models/instacart/instacart.instacart_basket_model__19ca8c1c152c
```
