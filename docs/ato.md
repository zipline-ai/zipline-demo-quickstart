# Account-takeover detection: rules versus XGBoost

Can a learned model beat a hand-tuned rule set at catching account takeovers
(ATO)? This tutorial builds a session-level ATO training set from the demo's
real access logs. It then tracks four models in one trial: a rules baseline and
three XGBoost models with progressively richer features.

All config paths below are relative to `configs/` and belong to the `app` team.

## Where the labels come from

The demo has real user activity but no fraud outcomes, and this tutorial adds no
input tables. Instead, two staging queries simulate an ATO program on top of
`public_demo_app.ui_access_logs_iceberg`:

- `staging_queries/app/ato_data.py: activity` keeps every real request and adds
  synthetic sessions to *established* account-days (accounts active in the
  prior 14 days). The demo has only about 60 organic sessions a day, so each
  account-day gets 12 independent injection slots, and each slot becomes one
  scenario at the rate shown:

  | Scenario | Per slot | What it looks like |
  | --- | ---: | --- |
  | `ato_scripted` | 3.0% | Credential stuffing from 48 shared hosting IPs, a script or spoofed browser agent, 0–7 failed logins, machine-speed requests, and 45% writes such as token creation or email/MFA changes. |
  | `ato_stealth` | 3.0% | A residential IP, the victim's own user agent, business hours, human pace, and occasional writes. |
  | `new_device` | 4.5% | Benign: the owner on a new phone or laptop, sometimes travelling overnight. |
  | `vpn_new_device` | 2.5% | Benign: a new device behind a commercial VPN shared by many accounts. |

- `sessions` groups activity into account, IP, user-agent, and hour sessions.
  `is_ato` is 1 for 85% of attack sessions. The other 15% stay unlabelled,
  like victims who never report.

The benign look-alikes are deliberate. They make "new IP", "new device", and
"shared IP" individually unreliable, which is how such rules fail in practice.
Every choice is an `XXHASH64` of stable keys, so reruns are identical.

Accounts are the authenticated `user_id`. Anonymous traffic is keyed by IP as
`ip:<address>`. The `scenario` column is simulation ground truth for slicing
results. Features never read it.

## Features and the training set

`group_bys/app/ato_features.py` defines four temporally accurate GroupBys over
`activity`:

- `account`: requests, writes, and auth failures (401/403) over 1 hour, 1 day,
  and 7 days; distinct IPs and user agents over 1 and 7 days; first-seen time.
- `account_ip` and `account_user_agent`: when this account first used the IP or
  user agent within 14 days, and how often.
- `ip`: distinct accounts and auth failures per IP over 1 and 7 days.

`joins/app/ato_training.py: v1` joins them onto sessions at session close (1 ms
after the last request). Derivations add IP and device age, account age, write
share, request rate, the UTC hour, an automation-agent flag, and four rules:

| Rule | Fires when |
| --- | --- |
| `rule_new_ip_and_device` | An account older than a day uses an IP and a user agent both first seen in this session. |
| `rule_auth_failures` | The account has 3 or more auth failures in the last hour. |
| `rule_scripted_writes` | An automation user agent wrote to the account in the last hour. |
| `rule_shared_ip` | The IP served 3 or more accounts in the last 7 days. |

`rule_score` counts the rules that fire.

## The four models

`models/app/ato_models.py` uses the shared Ray/XGBoost trainer for every variant,
with the same rows and holdout. All train on September 9 – October 11, 2026 and
validate on the final week, October 12–18.

| Experiment | Model | Inputs |
| --- | --- | --- |
| `rules` | `ato_rules_baseline` | `rule_score` only. Depth-1 trees can only calibrate it, so this measures the rules. |
| `velocity` | `ato_xgb_velocity` | 13 per-account velocity and spread features. |
| `novelty` | `ato_xgb_novelty` | Velocity plus IP and device novelty, account age, and session context. |
| `full` | `ato_xgb_full` | Novelty plus IP reputation and the four rule flags. |

The trainer reports validation AUC, logloss, precision, recall, and a
precision-recall curve. Positives are under 10% of sessions, so read the
precision-recall curve alongside AUC.

Measured on the demo (trial `ato-detection`, validation week of 1,153 sessions,
4.3% labelled ATO):

| Experiment | AUC | Logloss | Precision | Recall |
| --- | ---: | ---: | ---: | ---: |
| `rules` | 0.690 | 0.175 | 0.48 | 0.28 |
| `velocity` | 0.914 | 0.131 | 0.50 | 0.40 |
| `novelty` | 0.987 | 0.062 | 0.79 | 0.54 |
| `full` | 0.989 | 0.057 | 0.83 | 0.60 |

Precision and recall use a 0.5 threshold. IP age is the top feature by gain in
both novelty models. The rules fire on benign new devices and VPN logins, and
they miss stealth takeovers that reuse the victim's user agent.

## 1. Materialize the training data

Use a clean, pushed branch with a valid demo login. Wait for each backfill to
succeed before starting the next. Access logs begin on 2026-09-02, which gives
the features a week of history before the first training day.

```bash
cd configs
zipline compile
zipline hub backfill compiled/staging_queries/app/ato_data.activity__2 \
  --start-ds 2026-09-02 --end-ds 2026-10-18
zipline hub backfill compiled/staging_queries/app/ato_data.sessions__2 \
  --start-ds 2026-09-09 --end-ds 2026-10-18
zipline hub backfill compiled/joins/app/ato_training.v1__1 \
  --start-ds 2026-09-09 --end-ds 2026-10-18
zipline hub eval-table public_demo_data.app_ato_training_v1__1 --team app
```

Confirm `is_ato`, `ds`, and the `rule_*` columns are present.

## 2. Start a trial

```bash
zipline hub trial journal list --run-name ato-detection
zipline hub trial start ato-detection \
  --task 'Does an XGBoost model beat hand-tuned rules at catching account takeovers?' \
  --model app.ato_models.ato_xgb_full__fb2ec671ae2b
export ZIPLINE_TRIAL_ID='<trial-id>'
```

## 3. Run each experiment

Record, train, and attach metrics for each pair below, one at a time. Wait for
each workflow to succeed in the [demo UI](https://try.zipline.ai) before
attaching its metrics.

```bash
run_experiment() {
  experiment=$1 model=$2 title=$3
  conf=app.ato_models.${model}__fb2ec671ae2b
  zipline hub trial experiments record "$experiment" "$ZIPLINE_TRIAL_ID" \
    --title "$title" --status RUNNING --model-conf-name "$conf" && \
  ZIPLINE_TRIAL_ID="$ZIPLINE_TRIAL_ID" ZIPLINE_EXPERIMENT_ID="$experiment" \
    zipline hub backfill "compiled/models/app/ato_models.${model}__fb2ec671ae2b" \
    --start-ds 2026-10-18 --end-ds 2026-10-18
}

finish_experiment() {
  experiment=$1 model=$2
  zipline hub trial experiments metrics "$experiment" "$ZIPLINE_TRIAL_ID" \
    --model-conf-name "app.ato_models.${model}__fb2ec671ae2b" && \
  zipline hub trial experiments record "$experiment" "$ZIPLINE_TRIAL_ID" --status SUCCEEDED
}

run_experiment rules ato_rules_baseline 'Hand-tuned rules'
# After the workflow succeeds:
finish_experiment rules ato_rules_baseline

run_experiment velocity ato_xgb_velocity 'XGBoost: account velocity'
finish_experiment velocity ato_xgb_velocity

run_experiment novelty ato_xgb_novelty 'XGBoost: + IP and device novelty'
finish_experiment novelty ato_xgb_novelty

run_experiment full ato_xgb_full 'XGBoost: + IP reputation and rule flags'
finish_experiment full ato_xgb_full
```

If a run fails, check its **Ray (All)** logs and record that experiment as
`FAILED` instead.

## 4. Compare and record

Open the trial in the [demo UI](https://try.zipline.ai) to compare the four
experiments, then record the outcome:

```bash
zipline hub trial experiments list "$ZIPLINE_TRIAL_ID"
zipline hub trial summary '<best model, with validation AUC and logloss>' "$ZIPLINE_TRIAL_ID"
zipline hub trial status SUCCEEDED "$ZIPLINE_TRIAL_ID"
zipline hub trial journal append '<what each feature group added>' "$ZIPLINE_TRIAL_ID"
```

## Trainer archives

Ray downloads `<model_artifact_base_uri>/builds/<model_name>-<version>.zip`
for each model and writes its report beside it. These models keep artifacts
under `s3://zipline-public-demo-warehouse/ato_models`, rather than the demo
artifacts bucket, because Hub can read the warehouse bucket when it attaches
trainer reports to a trial. The models are version `fb2ec671ae2b`, and each name has a
copy of the shared trainer archive (build `19ca8c1c152c`):

```text
s3://zipline-public-demo-warehouse/ato_models/builds/ato_rules_baseline-fb2ec671ae2b.zip
s3://zipline-public-demo-warehouse/ato_models/builds/ato_xgb_velocity-fb2ec671ae2b.zip
s3://zipline-public-demo-warehouse/ato_models/builds/ato_xgb_novelty-fb2ec671ae2b.zip
s3://zipline-public-demo-warehouse/ato_models/builds/ato_xgb_full-fb2ec671ae2b.zip
```

If a training run fails with `NoSuchKey` while preparing its runtime
environment, an archive is missing; ask a Zipline employee to add it.

## Limits

This is a simulated fraud program on real traffic. The attack patterns, their
rates, and the 85% confirmation rate are assumptions written into
`ato_data.py`, so the comparison shows how to evaluate rules against models. It
says nothing about real-world ATO rates. The holdout is the final week, not a
random sample, so it does test generalization forward in time.
