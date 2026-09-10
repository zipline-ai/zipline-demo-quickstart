# Zipline Demo Quickstart

Example Zipline/Chronon configs for the public AWS demo environment.

New here? Start with [your first Zipline feature in five minutes](docs/tutorials/quickstart.md).

For a smaller follow-up exercise, try the [two-minute derived feature tutorial](docs/tutorials/derived-feature-and-fetch.md).

To combine chained features with an LLM-assisted investigation, try the
[account activity review tutorial](docs/tutorials/activity-review.md).

Coding agents can use the repository-local
[Zipline demo skill](.agents/skills/zipline-demo/SKILL.md) to discover the data,
follow lineage, deploy changes, and fetch features safely.

See [demo data sources](docs/data_sources.md) for the raw tables, schemas, freshness controls, and their consumers.

Start with the UI logs tutorial case study:

- [UI logs online consistency case study](docs/ui-logs-online-consistency-case-study.md)

The first dataset is UI/server access-log data from the public demo Kubernetes
deployment, landed by the demo infrastructure into AWS Glue/S3:

- `public_demo_app.ui_access_logs`

The live public demo endpoints are:

- UI: `https://try.zipline.ai`

By using the public demo, you agree to its [Terms of Service](TERMS.md). See the
[Privacy Policy](PRIVACY.md) for details about Google sign-in, access logs, Demo
datasets, retention, and your choices.

Datasource freshness is controlled in the infrastructure repo with
`ui_logs_freshness_profile` (`low_cost`, `balanced`, or `fresh`). This config
repo reads whatever cadence-produced log snapshots are present in S3/Glue.

