# Zipline Demo Quickstart

Example Zipline/Chronon configs for the public AWS demo environment.

Start with the UI logs tutorial case study:

- [UI logs online consistency case study](docs/ui-logs-online-consistency-case-study.md)

The first dataset is UI/server access-log data from the public demo Kubernetes
deployment, landed by the demo infrastructure into AWS Glue/S3:

- `public_demo_app.ui_access_logs`

The live public demo endpoints are:

- UI: `http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com`
- Hub: `http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com/services/hub`

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
