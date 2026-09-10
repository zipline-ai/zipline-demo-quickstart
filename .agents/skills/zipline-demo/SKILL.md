---
name: zipline-demo
description: Explore, modify, deploy, and fetch features from the public Zipline demo configuration repository.
---

# Zipline Demo

Use this skill when asked to explore the public demo, create a feature, deploy a
config, fetch a user's activity, or review whether activity looks unusual.

## Environment

- Work from `configs` for `zipline hub` commands.
- Read service URLs from `configs/teams.py`; do not add URL flags unnecessarily.
- `zipline hub eval` compiles automatically.
- Fetch keys must be JSON arrays, for example
  `[{"email_hash":"deadbeef"}]`.
- Derive `email_hash` locally with `python3 scripts/email_hash.py` and never send
  the plain email to Zipline.

## Data And Lineage

Read `docs/data_sources.md` before changing a source. The account-review path is:

```text
ui_access_logs_iceberg
  -> email_request_activity GroupBy
  -> account_activity_review Join
  -> online fetch
```

External staging-query inputs must be declared with `TableDependency`, including
their actual partition column. Outputs of Zipline configs are resolved through
lineage and must not be treated as external tables.

Public-demo Joins should set `enable_stats_compute=True` in the Python `Join`
constructor. This enables Join stats computation and serializes to
`executionInfo.enableStatsCompute` in the compiled config; it is separate from
`check_consistency`. Enabling it on an existing online Join requires a version
increment.

## Workflow

1. Inspect the source, upstream configs, and compiled lineage.
2. Make the smallest config change and increment versions for changed online
   configs and their affected dependents.
3. Run `zipline hub eval <compiled-conf>`.
4. Run `zipline hub run-adhoc <compiled-conf>` and wait for success.
5. Fetch with `zipline hub fetch <compiled-conf> --key-json '<json-array>' --format json`.
6. Check freshness fields before interpreting feature values.

For an account review, derive the email hash locally and fetch the
`account_activity_review` Join with the Zipline CLI. Treat the result as
investigative guidance only. Never claim fraud, infer identity or location from
IP metadata, or recommend automatic enforcement from this demo.
