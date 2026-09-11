# Zipline Demo Quickstart

Example Zipline/Chronon configs for a demo environment.

New here? Start with [your first Zipline feature in five minutes](docs/tutorials/quickstart.md).

For a smaller follow-up exercises, see other included [tutorials](docs/tutorials/).

Coding agents can use the repository-local
[Zipline demo skill](.agents/skills/zipline-demo/SKILL.md) to discover the data,
follow lineage, deploy changes, and fetch features safely.

See [demo data sources](docs/data_sources.md) for the raw tables, schemas, freshness controls, and their consumers.

The live public demo endpoints are:

- UI: [https://try.zipline.ai](https://try.zipline.ai)

By using the public demo, you agree to its [Terms of Service](TERMS.md). See the
[Privacy Policy](PRIVACY.md) for details about Google sign-in, access logs, Demo
datasets, retention, and your choices.

Datasource freshness is controlled in an infrastructure repo with
`ui_logs_freshness_profile` (`low_cost`, `balanced`, or `fresh`) changed weekly to purposely create online offline inconsistencies. 

