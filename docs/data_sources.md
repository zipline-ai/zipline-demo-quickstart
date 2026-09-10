# Demo Data Sources

The demo uses its own traffic as data. Requests to `https://try.zipline.ai` produce Kubernetes ingress and application audit logs, which are shipped to CloudWatch, parsed by a scheduled Lambda, and stored in S3. No third-party API token is required.

```text
try.zipline.ai
  -> Kubernetes ingress and application audit logs
  -> CloudWatch Logs
  -> public-demo-ui-log-ingestor
  -> partitioned JSONL in S3 and AWS Glue
  -> Iceberg tables read by Zipline
```

The persistent datasource infrastructure lives in `infrastructure/aws/public-demo-datasources`. It is separate from the Kubernetes platform so weekly platform resets do not erase the demo history.

## Access Logs

Each row represents one parsed HTTP request.

| Layer | Location |
| --- | --- |
| Upstream logs | `/aws/eks/public-demo-eks/containers` in CloudWatch Logs |
| Raw Glue table | `public_demo_app.ui_access_logs` |
| Raw S3 prefix | `s3://zipline-public-demo-curated/app/ui_access_logs/` |
| Zipline-facing table | `public_demo_app.ui_access_logs_iceberg` |
| Partition | `snapshot_date` in Glue/JSONL; `ds` in Iceberg |
| Zipline source | `configs/sources/app/ui_logs.py` |

The ingestor understands standard ingress-nginx access lines and structured `api_request_complete` audit events. It discards log lines that are not HTTP requests.

### Columns

| Column | Type | Meaning |
| --- | --- | --- |
| `event_id` | string | Stable SHA-256 identifier derived from the CloudWatch event and message. |
| `ingestion_id` | string | UUID shared by rows written in one Lambda invocation. |
| `event_ts` | bigint | Request time in Unix milliseconds; used as event time by Zipline. |
| `event_time_iso` | string | UTC request time in ISO 8601 form. |
| `ingested_at` | string | UTC time at which the Lambda processed the request. |
| `freshness_lag_seconds` | bigint | Seconds between the request and ingestion. |
| `log_stream` | string | Source CloudWatch log stream. |
| `namespace` | string | Kubernetes namespace parsed from log metadata. |
| `pod` | string | Kubernetes pod that emitted the log. |
| `container` | string | Kubernetes container that emitted the log. |
| `client_ip` | string | Origin IP recorded by ingress or the structured audit event. |
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

The `email_access_logs` source selects authenticated requests and derives the
same eight-character `email_hash` directly in Spark without selecting the raw
email into its feature GroupBy. `email_request_activity` computes one-day and
six-day behavioral features by that privacy-safe key; the
`account_activity_review` Join packages them for online fetching.

## User Identity Snapshots

This entity dataset maps an internal user ID to a short, non-reversible display identifier without publishing email addresses.

| Layer | Location |
| --- | --- |
| Source events | `user_created`, `authn_login_success`, and `authn_token_created` application logs |
| Raw Glue table | `public_demo_app.user_identity_snapshots` |
| Raw S3 prefix | `s3://zipline-public-demo-curated/app/user_identity_snapshots/` |
| Zipline-facing table | `public_demo_app.app_user_identity_user_identity_snapshots_iceberg__0` |
| Partition | `snapshot_date` in Glue/JSONL; `ds` in Iceberg |
| Zipline source | `configs/sources/app/user_identity.py` |

The Lambda normalizes the email to lowercase and stores only the first eight hexadecimal characters of its SHA-256 digest. The plain email is not written to this dataset. Eight characters are convenient for the demo but are a pseudonymous label, not a security boundary.

### Columns

| Column | Type | Meaning |
| --- | --- | --- |
| `user_id` | string | Internal authenticated user identifier and entity key. |
| `email_hash` | string | First eight hexadecimal characters of SHA-256 over the normalized email. |
| `first_seen_ts` | bigint | Earliest observed identity event in Unix milliseconds. |
| `last_seen_ts` | bigint | Latest observed identity event in Unix milliseconds. |
| `last_seen_time_iso` | string | Latest observed identity event in ISO 8601 form. |
| `last_event` | string | Most recent supported authentication event name. |
| `source_event_id` | string | CloudWatch event that last updated the identity. |
| `ingestion_id` | string | UUID of the Lambda invocation that wrote the snapshot. |
| `ingested_at` | string | UTC time at which the snapshot was written. |
| `snapshot_date` / `ds` | string | Daily snapshot partition in `YYYY-MM-DD` format. |

The `user_identity_snapshots` entity source feeds two no-aggregation GroupBys:

- `user_identity`, keyed by internal `user_id`, enriches requests with `email_hash`.
- `email_identity`, keyed by `email_hash`, powers a privacy-safe self-lookup.

The `user_request_identity` join enriches a request with `email_hash` and `has_authenticated_identity`. The `email_activity_profile` join lets a person fetch their identity activity using only the eight-character email hash. It returns only the final eight characters of the opaque user ID as `user_id_suffix`, along with first/last-seen fields, the latest event, and the derived `is_returning_user` feature.

## Freshness And Cost

`ui_logs_freshness_profile` controls how often the Lambda reads CloudWatch and how far it looks back:

| Profile | Schedule | Lookback |
| --- | ---: | ---: |
| `low_cost` | 30 minutes | 30 minutes |
| `balanced` | 5 minutes | 5 minutes |
| `fresh` | 1 minute | 1 minute |

Both datasets are produced by the same invocation, so the setting affects access-log and identity freshness together. Overlapping lookbacks can produce repeated raw access events; `event_id` remains stable so consumers can identify duplicates.

The Iceberg tables are the tables referenced by the demo configs. Their latest `ds` partition must be refreshed from the raw Glue tables before a backfill that requires newly landed dates.
