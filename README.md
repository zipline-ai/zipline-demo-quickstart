# Zipline Demo Quickstart

Example Zipline/Chronon configs for the public AWS demo environment.

New here? Start with [your first Zipline feature in five minutes](docs/tutorials/quickstart.md).

For a smaller follow-up exercise, try the [two-minute derived feature tutorial](docs/tutorials/derived-feature-and-fetch.md).

See [demo data sources](docs/data_sources.md) for the raw tables, schemas, freshness controls, and their consumers.

Start with the UI logs tutorial case study:

- [UI logs online consistency case study](docs/ui-logs-online-consistency-case-study.md)

The first dataset is UI/server access-log data from the public demo Kubernetes
deployment, landed by the demo infrastructure into AWS Glue/S3:

- `public_demo_app.ui_access_logs`

The live public demo endpoints are:

- UI: `https://try.zipline.ai`
- Hub: `https://try.zipline.ai/services/hub`

Datasource freshness is controlled in the infrastructure repo with
`ui_logs_freshness_profile` (`low_cost`, `balanced`, or `fresh`). This config
repo reads whatever cadence-produced log snapshots are present in S3/Glue.

## Compile

```bash
cd configs
export PYTHONPATH="$(pwd):$PYTHONPATH"
zipline compile
```

Or from the repository root:

```bash
./scripts/compile.sh
```
