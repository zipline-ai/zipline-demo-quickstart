# Provision the featurestore.org taxi benchmark

This setup uses the existing AWS demo in us-west-2. It adds one static Iceberg source table and one online snapshot GroupBy. It does not run a load test or create a streaming pipeline.

## Prepare locally

From the repository root:

```sh
python3 -m venv .venv-taxi
. .venv-taxi/bin/activate
pip install -r scripts/requirements-taxi.txt
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/provision_taxi.py --snapshot-date 2026-09-16 --output /tmp/zipline-taxi
```

Choose the snapshot date explicitly and use the same date for deployment. Preparation checks the upstream CSV checksum and creates 500 integer entity keys, expected feature values, a normalized CSV, and a source manifest. It makes no AWS calls without `--apply`.

## Load AWS data

Use AWS credentials for the public demo account. The loader uses the standard AWS credential chain; do not put keys into the script. The operator needs Glue table creation/read permissions in `public_demo_app`, S3 list/read/write permissions on the dedicated prefix below, and any encryption permissions required by the bucket. The Glue database must already exist.

Check the selected AWS identity, then create the table:

```sh
aws sts get-caller-identity
python scripts/provision_taxi.py --snapshot-date 2026-09-16 \
  --input /tmp/zipline-taxi/rides500.original.csv \
  --output /tmp/zipline-taxi --apply
```

This writes:

- Glue table: `public_demo_app.featurestore_benchmark_taxi`
- S3 location: `s3://zipline-public-demo-curated/app/featurestore_benchmark_taxi`
- Identity partition: string `ds` using the supplied date

The loader reads the table back and compares all values. It refuses to modify an existing table or nonempty location. If a run fails after creating a table, inspect that partial state before retrying; do not delete it blindly. The `applied.json` receipt records the Iceberg snapshot ID.

The demo's orchestration tfvars already include this curated bucket in `aws.additional_data_buckets`. No Terraform change is expected, assuming that configuration has been applied and the datasource database exists. Actual IAM and AWS writes have not been verified by local tests.

## Deploy online

Work from `configs` so the CLI reads `teams.py` for demo endpoints. Authenticate to the demo Hub using your normal Zipline CLI login flow if prompted.

```sh
cd configs
zipline compile
zipline hub eval compiled/group_bys/app/benchmark_taxi.benchmark_taxi__0
zipline hub run-adhoc --end-ds 2026-09-16 \
  compiled/group_bys/app/benchmark_taxi.benchmark_taxi__0
```

Wait for the adhoc workflow to finish successfully in the demo UI before fetching. The GroupBy has no aggregations and serves all 19 CSV feature columns by integer `id`. Its online and offline recurring schedules are disabled; this is a one-off fixture. If the demo is reset or online data expires, deploy it again using the original snapshot date. No Join is needed.

## Verify serving

From the repository root:

```sh
python scripts/verify_taxi.py --expected /tmp/zipline-taxi/expected.json \
  --group-by app.benchmark_taxi.benchmark_taxi__0
```

This sends five sequential 100-record requests, verifies every entity and feature value, and fails on missing rows, partial failures, or mismatches. Floating-point values use a 1e-9 tolerance. If the endpoint requires a bearer token, supply `ZIPLINE_TOKEN` in the environment.

After verification, point the separate Locust package in `platform/benchmarks/featurestore-org/zipline-benchmarking` at this GroupBy and `/tmp/zipline-taxi/keys.json`. Record the deployment revision, resources, source receipt, and client placement before measuring latency. A successful correctness check is not a performance result.
