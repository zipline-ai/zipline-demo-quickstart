# Demo Data Sources

The public demo combines live application activity with the Instacart Online
Grocery Shopping Dataset 2017. Use application activity to explore online feature
updates, and the static grocery dataset to build historical features and compare
model experiments. No third-party dataset API token is required.

```text
Demo activity -> event sources -> online and offline features
Grocery orders -> staging queries -> history features -> model experiments
```

## Access Logs

Each row represents one parsed HTTP request.

| Layer | Location |
| --- | --- |
| Zipline-facing table | `public_demo_app.ui_access_logs_iceberg` |
| Partition | `ds`, a date in `YYYY-MM-DD` format |
| Zipline source | `configs/sources/app/ui_logs.py` |

Only HTTP request events enter this dataset.

### Columns used by the examples

| Column | Type | Meaning |
| --- | --- | --- |
| `event_id` | string | Stable SHA-256 identifier for the source request event. |
| `ingestion_id` | string | Identifier shared by rows ingested together. |
| `event_ts` | bigint | Request time in Unix milliseconds; used as event time by Zipline. |
| `event_time_iso` | string | UTC request time in ISO 8601 form. |
| `ingested_at` | string | UTC time at which the request was ingested. |
| `freshness_lag_seconds` | bigint | Seconds between the request and ingestion. |
| `client_ip` | string | Origin IP recorded for the request. |
| `user_id` | string | Authenticated Zipline user ID when an audit event provides it; otherwise empty. |
| `http_method` | string | HTTP method such as `GET`, `POST`, `PUT`, or `DELETE`. |
| `path` | string | Request path, including its query string when present. |
| `route_family` | string | Stable path grouping such as `/services/hub`, `/workflows`, or `/`. |
| `status_code` | int | HTTP response status. |
| `status_family` | string | Status class such as `2xx`, `4xx`, or `5xx`. |
| `is_error` | int | `1` for a response status of 500 or greater. |
| `is_not_found` | int | `1` for a 404 response. |
| `is_write` | int | `1` for `POST`, `PUT`, `PATCH`, or `DELETE`. |
| `request_time_seconds` | double | Request latency in seconds. |
| `user_agent` | string | HTTP user-agent value when available. |
| `raw_message` | string | Original message retained for parser debugging. |
| `snapshot_date` / `ds` | string | Daily partition in `YYYY-MM-DD` format. |

Two Zipline event sources select from this table:

- `access_logs` supplies route and HTTP-method health features.
- `client_access_logs` adds client IP, authenticated user, user agent, and recent activity fields.

They feed `endpoint_health`, `method_health`, and `client_activity`, plus the `client_request_context` and `user_request_identity` joins.

The [account-takeover tutorial](ato.md) reads this table through the
`ato` staging queries, which add simulated attack and look-alike sessions and
label them. Its features never read the simulation's ground-truth column.

The `email_access_logs` source selects authenticated requests, consumes the
same event shape for online updates, and derives the
same eight-character `email_hash` directly in Spark without selecting the raw
email into its feature GroupBy. `email_request_activity` computes one-day and
six-day behavioral features by that privacy-safe key; the
`account_activity_review` Join packages them for online fetching.

## User Identity Snapshots

This entity dataset maps an internal user ID to a short, non-reversible display identifier without publishing email addresses.

| Layer | Location |
| --- | --- |
| Source events | `user_created`, `authn_login_success`, and `authn_token_created` application logs |
| Zipline-facing table | `public_demo_app.app_user_identity_user_identity_snapshots_iceberg__0` |
| Partition | `ds`, a date in `YYYY-MM-DD` format |
| Zipline source | `configs/sources/app/user_identity.py` |

The demo normalizes the email to lowercase and stores only the first eight hexadecimal characters of its SHA-256 digest. The plain email is not written to this dataset. Eight characters are convenient for the demo but are a pseudonymous label, not a security boundary.

### Columns used by the examples

| Column | Type | Meaning |
| --- | --- | --- |
| `user_id` | string | Internal authenticated user identifier and entity key. |
| `email_hash` | string | First eight hexadecimal characters of SHA-256 over the normalized email. |
| `first_seen_ts` | bigint | Earliest observed identity event in Unix milliseconds. |
| `last_seen_ts` | bigint | Latest observed identity event in Unix milliseconds. |
| `last_seen_time_iso` | string | Latest observed identity event in ISO 8601 form. |
| `last_event` | string | Most recent supported authentication event name. |
| `source_event_id` | string | Source event that last updated the identity. |
| `ingestion_id` | string | Identifier of the batch that wrote the snapshot. |
| `ingested_at` | string | UTC time at which the snapshot was written. |
| `snapshot_date` / `ds` | string | Daily snapshot partition in `YYYY-MM-DD` format. |

The `user_identity_snapshots` entity source feeds two no-aggregation GroupBys:

- `user_identity`, keyed by internal `user_id`, enriches requests with `email_hash`.
- `email_identity`, keyed by `email_hash`, powers a privacy-safe self-lookup.

The `user_request_identity` join enriches a request with `email_hash` and `has_authenticated_identity`. The `email_activity_profile` join lets a person fetch their identity activity using only the eight-character email hash. It returns only the final eight characters of the opaque user ID as `user_id_suffix`, along with first/last-seen fields, the latest event, and the derived `is_returning_user` feature.

## Instacart Grocery Orders

This static source is the Instacart Online Grocery Shopping Dataset 2017,
accessed through Kaggle. It contains more than 3.4 million orders from over
200,000 shoppers and supports the demo's next-basket feature engineering and
model-training examples. Instacart publishes the dataset for non-commercial use;
demo code and tutorials should preserve this attribution.

The original CSV files were converted once to Parquet. The `iceberg` prefix is
retained for compatibility with the existing staging-query paths, but these are
plain Parquet files read directly by Spark rather than catalog-managed Iceberg
tables.

| Layer | Location |
| --- | --- |
| S3 prefix | `s3://zipline-public-demo-curated/kaggle_instacart/iceberg/` |
| File layout | `<table>/data/part-00000.parquet` |
| Partitioning | None; the source is a static snapshot |
| Total rows | 37,290,032 |
| Stored size | Approximately 142 MiB |

### Tables

| Table | Rows | Columns | Used by current staging queries |
| --- | ---: | --- | --- |
| `orders` | 3,421,083 | `order_id`, `user_id`, `eval_set`, `order_number`, `order_dow`, `order_hour_of_day`, `days_since_prior_order` | Yes |
| `order_products_prior` | 32,434,489 | `order_id`, `product_id`, `add_to_cart_order`, `reordered` | Yes |
| `order_products_train` | 1,384,617 | `order_id`, `product_id`, `add_to_cart_order`, `reordered` | Yes |
| `products` | 49,688 | `product_id`, `product_name`, `aisle_id`, `department_id` | Yes |
| `aisles` | 134 | `aisle_id`, `aisle` | No |
| `departments` | 21 | `department_id`, `department` | No |

The dataset does not include calendar dates. The staging queries reconstruct
event dates from each shopper's real order sequence and
`days_since_prior_order`, anchored to a fixed demo date. The `prior` baskets
form the historical feature stream, while the `train` basket supplies the
next-basket label. Keeping those inputs separate prevents label leakage.

Spark reads the four active inputs from these paths:

```text
s3://zipline-public-demo-curated/kaggle_instacart/iceberg/orders/data/
s3://zipline-public-demo-curated/kaggle_instacart/iceberg/order_products_prior/data/
s3://zipline-public-demo-curated/kaggle_instacart/iceberg/order_products_train/data/
s3://zipline-public-demo-curated/kaggle_instacart/iceberg/products/data/
```

### Trainer Artifacts

The Ray trainer code is packaged separately from the compiled Zipline model
configuration. For each model, Ray downloads this name-scoped object:

```text
<model_artifact_base_uri>/builds/<model_name>-<version>.zip
```

The demo uses `s3://zipline-public-demo-artifacts` as
`model_artifact_base_uri` and trainer version `19ca8c1c152c`. Both model names
therefore require an archive, even though the bytes are identical:

```text
s3://zipline-public-demo-artifacts/builds/instacart_basket_baseline-19ca8c1c152c.zip
s3://zipline-public-demo-artifacts/builds/instacart_basket_model-19ca8c1c152c.zip
```

These are one-time artifacts, not outputs of config compilation. If either is
missing, Ray fails while preparing its runtime environment with `NoSuchKey`
before training starts.

## Feature Freshness

Online activity features update as new events arrive. Offline activity and
identity data refresh periodically, so their values may lag behind recent demo
activity. Check `event_ts`, `ingested_at`, and `freshness_lag_seconds` before
interpreting results or backfilling a recent date.

Compare online and offline values to see how delayed data affects feature
correctness. Repeated source events can share the same `event_id`; use that stable
identifier when checking for duplicates. The Instacart dataset is a fixed
snapshot and does not receive live updates.

## Featurestore.org Taxi Benchmark

The optional static benchmark fixture uses `public_demo_app.featurestore_benchmark_taxi`
at `s3://zipline-public-demo-curated/app/featurestore_benchmark_taxi`. It contains the
500 upstream taxi records, an integer `id`, and a string `ds` snapshot partition.
`configs/group_bys/app/benchmark_taxi.py` serves the 19 feature columns without
aggregation. Its recurring schedules are disabled.

See [provisioning and verification](tutorials/featurestore-benchmark.md) for the
explicit loader and one-off online deployment steps. The configuration's presence
does not mean the table has been provisioned.
