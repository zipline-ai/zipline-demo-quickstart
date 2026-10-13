
# 🧠 Zipline AI: Sample Chronon Project

Use these configs to author and run [Chronon](https://chronon.ai) feature pipelines in the Zipline public demo, including GroupBys, Joins, and model experiments.

Chronon is a unified platform for **feature engineering**, enabling **online and offline consistency**, **real-time feature generation**, and **historical backfills** from a single codebase.

---

## 📦 Project Structure

```bash
.
├── group_bys/           # GroupBy definitions (feature aggregations)
├── joins/               # Join definitions (how sources and GroupBys are combined)
├── sources/             # Chronon Source definitions (event tables)
├── compiled/            # Generated configs and outputs
├── teams.py             # Chronon Team configurations
└── README.md
```

---

## 🚀 Quick Start

### 🛠️ Requirements

To get started, make sure you have the following set up:

- ✅ **Python** 3.11 or higher
- ✅ **Zipline CLI** — Install or upgrade via:
  ```bash
  pip install --upgrade zipline-ai
  ```
- ✅ Access to [the public demo](https://try.zipline.ai)
- ✅ Add this to your shell config (e.g., .bashrc, .zshrc):

```bash
# From the same directory as this README
export PYTHONPATH="$(pwd):$PYTHONPATH"
```

---
## Demo Configuration

[teams.py](teams.py) already contains the connection settings for the public demo.
Start with [your first feature](../docs/tutorials/quickstart.md), or follow
[model iteration and experiment comparison](../docs/tutorials/model-experiment-comparison.md).
Each tutorial explains the authentication and data access it needs.

---

## 🧪 Compiling

To generate the user configs from the Python chronon objects to be used in the CLI, run:

```bash
zipline compile
```

This will create a `compiled` directory.

## 🧪 Running a GroupBy or Join Backfill

Run a GroupBy backfill from the CLI:

```bash
zipline run \
--mode backfill \
--conf compiled/group_bys/<TEAM_NAME>/<GROUPBY_NAME>
```

Run a Join backfill from the CLI:

```bash
zipline run \
--mode backfill \
--conf compiled/joins/<TEAM_NAME>/<JOIN_NAME>
```

Results are written to the output table specified by the config.

---

## 🧪 Running a GroupBy upload (GBU) job.

```bash
zipline run \
--mode upload \
--conf compiled/group_bys/<TEAM_NAME>/<GROUP_BY_NAME> \
--ds <DATE>
```

Results are written to the output table specified by the config.

---

## 🧪 Upload the GBU values to online KV store.

```bash
zipline run \
--mode upload-to-kv \
--conf compiled/group_bys/<TEAM_NAME>/<GROUP_BY_NAME> \
--ds <DATE>
```

---

## 🧪 Upload the metadata of Chronon GroupBy or Join to online KV store for serving.

GroupBy metadata upload:
```bash
zipline run \
--mode metadata-upload \
--conf compiled/group_bys/<TEAM_NAME>/<GROUP_BY_NAME>
```

Join metadata upload:
```bash
zipline run \
--mode metadata-upload \
--conf compiled/joins/<TEAM_NAME>/<JOIN_NAME>
```

---

## 🧪 Fetch feature values from Chronon GroupBy or Join.

**Note:** This is only for debugging purposes. Not for production use.

Fetching from a GroupBy:
```bash
zipline run \
--mode fetch \
--conf compiled/group_bys/<TEAM_NAME>/<GROUP_BY_NAME> \
--name <GROUP_BY_NAME> \
-k '{"<ENTITY_KEY>": "<VALUE>"}'
```

Fetching from a Join:
```bash
zipline run \
--mode fetch \
--conf compiled/joins/<TEAM_NAME>/<JOIN_NAME> \
--name <JOIN_NAME> \
-k '{"<ENTITY_KEY>": "<VALUE>"}'
```

---

## 📚 Resources

- [Chronon Docs](https://chronon.ai)
- [GitHub](https://github.com/airbnb/chronon)
- [Community Slack](https://join.slack.com/t/chrononworkspace/shared_invite/zt-33zbnzwac-ghPZXpYNZJsArXZ5WdBy9g)

---

## 👋 About

This public demo helps you explore feature pipelines from source data through historical computation, online serving, and model evaluation.
