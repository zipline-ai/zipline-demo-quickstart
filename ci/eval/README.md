# Config eval CI

Pull requests and pushes to `main` run compile and eval when files under
`configs/` change. Adding the **`run-eval`** label to a pull request forces the
same sequence even without config changes; remove and re-add it to request
another run. Manual runs of **Config eval** also force the sequence. Other label
events do not run or cancel config checks. Merely keeping the label on a PR does
not force runs on later updates without config changes.

The entry point is `eval.yml`. It first calls the reusable `check-configs.yml`
workflow to compile and verify that committed generated configs are up to date.
Only after that check succeeds does it prepare the warehouse and evaluate every
GroupBy, Join, and StagingQuery. Preparation compiles a separate clean copy for
local source substitutions. Currently that
is **20 configs**. Models are deliberately excluded: `LocalEvalVerticle`'s
`InMemoryConfDao` does not load training Model configs.

## Shared source catalog

[`sources.yaml`](sources.yaml) is the source contract: Spark SQL column types,
optional partition columns, and named values for **one or two synthetic rows per
upstream source**. The current seven sources total eight rows. Use explicit
`null` values and quote date strings. Types come from `docs/data_sources.md`,
`scripts/provision_taxi.py`, and the source queries. These small fixtures check
SQL, schemas, and lineage; they do not assert feature values or window coverage.

Preparation builds one Hadoop Iceberg warehouse with the PySpark 3.5.0 runtime
in the published local eval image and Iceberg 1.4.3, matching the upstream
`docker/eval/examples/build_warehouse.py` example. It uploads the warehouse,
freshly compiled CI configs, normalized spec, matrix, and rewrite audit as the
`eval-inputs` artifact. Every eval job downloads that same artifact and mounts
the warehouse read-only. No eval job rebuilds or changes the input catalog.

**Always build and mount at `/warehouse` inside Docker.** Iceberg metadata
contains absolute paths, so changing that container path after artifact transfer
breaks reads. Host directories can differ freely.

The service creates a separate temporary output catalog per request and copies
the fixture inputs into it. This is intrinsic to local eval; the shared source
warehouse is still created only once. Do not set `catalogOverride` to the source
catalog: that would mix inputs and outputs and can cause eval to skip configs
whose output tables already exist.

Instacart reads raw Parquet paths rather than catalog tables. Each of these four
fixtures declares an exact `sql_source` identifier. `prepare.py` substitutes that
identifier with its `ci_raw` table **only in the disposable compiled CI copy**.
SQL expressions, source configs, dependencies, and committed compiled artifacts
are otherwise unchanged. `rewrites.json` records each substitution. No live S3,
Glue, Hub, or demo credentials are required. Derived tables are never seeded:
eval must traverse their generating configs.

## Individual results

We use a **job matrix**, not PR comments. Each config has its own check, job log,
summary, and `eval-<kind>-<name>` artifact. `fail-fast: false` runs all configs even
after a failure; concurrency is capped at six jobs. Each job runs its own eval
container so its server stack traces are localized to that config and lineage.
This also works for fork PRs with only `contents: read`, without comment tokens
or a privileged `pull_request_target` workflow.

Artifacts contain `request.json`, the raw and parsed response, readable
`eval.log`, `server.log`, `result.json`, and a summary. Console output uses eval's
`shortMessage`; `eval.log` contains its full `message`, without rebuilding the
response tree. HTTP errors, timeouts, malformed responses, explicit
eval failures, failed upstream responses, and logged computation fallbacks fail the job. The stable
**All config evals** check fails if the compile check, preparation, or any requested
matrix job fails or skips. It passes without running compile/eval for PRs with
no config changes and no explicit eval request, so it can be used for branch
protection. Artifact retention is seven days.

Eval's success flag primarily describes schema/lineage validation. Upstream
GroupBy, Join, and StagingQuery handlers can catch sample computation exceptions
and fall back to empty schema tables. The harness also checks the pinned image's
`Failed to run <kind> computation` log messages and fails the job if any occur,
saving `computation-errors.log` alongside the full server log. Recheck these log
markers when upgrading the image. A passing check still does not assert feature
values, nonempty outputs, model execution, or production warehouse access. The
request uses fixed dates `2026-08-01` through `2026-09-04` to bound sample work;
timestamps are not aligned to guarantee nonempty joins or aggregations.

Initial local validation found an existing computation failure in
`app.account_activity_review.account_activity_review__7`: the derivation refers
to `ts`, which is absent from its entity-left computation output. The service
reports success after falling back, but this CI check correctly fails that target.
The other 19 configs completed without these computation errors.

## Run locally

From the repository root, with Python 3.11+ and Docker:

```bash
python -m venv /tmp/demo-eval-venv
source /tmp/demo-eval-venv/bin/activate
pip install -r ci/eval/requirements.txt
python -m unittest discover -s ci/eval -p 'test_*.py' -v

# Choose a fresh directory for every run; preparation refuses stale outputs.
export EVAL_BUNDLE="$(mktemp -d)/eval-bundle"
export EVAL_IMAGE=ziplineai/local-eval@sha256:810166bdfa91d3cae5a54954479cb00f9798425687b16487f3e57dbdd77439c2
python ci/eval/prepare.py --output "$EVAL_BUNDLE"
mkdir -p "$EVAL_BUNDLE/warehouse"
docker pull --platform linux/amd64 "$EVAL_IMAGE"
docker run --rm --platform linux/amd64 --cpus 2 --memory 5g \
  -v "$PWD/ci/eval:/scripts:ro" \
  -v "$EVAL_BUNDLE/sources.json:/sources.json:ro" \
  -v "$EVAL_BUNDLE/warehouse:/warehouse" \
  -e JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=2 -Xmx3g' \
  "$EVAL_IMAGE" python3 /scripts/build_warehouse.py --spec /sources.json
python ci/eval/run_eval.py --image "$EVAL_IMAGE" --bundle "$EVAL_BUNDLE" \
  --name instacart.instacart.orders__1 --output /tmp/demo-eval-orders-result
```

Read `matrix.json` for the complete list of names. The pinned image is amd64;
Apple Silicon uses Docker emulation. Docker needs at least 5 GiB available for
each simultaneous eval container.

## Maintenance

- Add a fixture when adding an upstream table. Preparation rejects undeclared
  source references, unmapped file inputs, mismatched row columns/types, more
  than two rows, and fixtures that shadow generated output tables.
- Add new GroupBys, Joins, and StagingQueries normally; compilation discovers
  them without editing the workflow matrix. Python source helpers and team
  metadata are not standalone eval targets.
- Update the compiler pin in `requirements.txt` and the image digest in the
  workflow and this README together, then rerun the integration checks. Spark
  and Iceberg builder versions must remain compatible with the chosen image.
- Preparation runs `zipline compile` without `--force` or
  `--ignore-python-errors`. It never evaluates stale committed compiled configs.

The implementation follows `LocalEvalVerticle`, `InMemoryConfDao`, and
`CatalogDataLoader` under `platform/eval/src/main/scala/ai/chronon/eval/`,
plus `platform/docker/eval/local.Dockerfile`.
Some examples in `platform/eval/CI_SETUP.md` are older than the implementation:
local eval supplies its own name-based config lookup, so callers need only
`confName`; request options belong under `parameters`.
