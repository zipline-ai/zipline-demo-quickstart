# UI Logs Freshness And Online Consistency Case Study

This is the primary case study for the public Zipline demo.

The story is simple: people are using the demo UI, and the platform is producing Kubernetes access logs. If the UI is returning 404s, 500s, slow requests, or surprising write traffic, stale features can make the product look healthy when it is not. If we cannot measure how fresh the online values are, we are flying blind.

## Product Story

Imagine an operator looking at the public demo while users are exploring it. They want to know:

- Which UI or Hub routes are being hit right now?
- Are users seeing 404s after clicking through the product?
- Are writes, PUTs, or DELETEs happening more often than expected?
- Did a route start returning 500s in the last few minutes?
- Is the "current" online health answer based on fresh logs or stale logs?
- Do offline backfills and online serving produce the same route health values?

This lands better than a synthetic file-count example because everybody understands a broken page, a failed request, or a stale dashboard.

## Data Source

The AWS platform layer already ships Kubernetes container logs to CloudWatch through Fluent Bit. The datasource layer harvests recent HTTP access log lines from that CloudWatch log group, parses them, writes JSONL to S3, and registers daily Glue partitions.

Default table:

```text
public_demo_app.ui_access_logs_iceberg
```

Important columns:

| Column | Meaning |
| --- | --- |
| `event_ts` | Original log event time in milliseconds |
| `ingested_at` | When the datasource Lambda harvested the event |
| `freshness_lag_seconds` | Age of the event at harvest time |
| `http_method` | GET, PUT, DELETE, POST, etc. |
| `path` | Raw request path |
| `route_family` | Stable route grouping such as `/services/hub` or `/workflows` |
| `status_code` | HTTP response status |
| `is_not_found` | 1 when status is 404 |
| `is_error` | 1 when status is 500 or above |
| `is_write` | 1 for POST, PUT, PATCH, or DELETE |
| `request_time_seconds` | Parsed request latency when present |
| `raw_message` | Original log message for debugging parser gaps |

## Freshness Lever

The source has one visible lever:

```hcl
ui_logs_freshness_profile = "low_cost"
```

Suggested profiles:

| Profile | Harvest Cadence | Lookback | Intended Feeling |
| --- | ---: | ---: | --- |
| `low_cost` | 30 minutes | 30 minutes | Cheap, but visibly stale for live health |
| `balanced` | 5 minutes | 5 minutes | Good default demo setting |
| `fresh` | 1 minute | 1 minute | Best live signal, highest cost |

Start the tutorial in `low_cost`. Then switch toward `balanced` or `fresh` and show that the same feature definitions become more useful because the online store receives newer observations.

## Features People Understand

### Endpoint Health

Keyed by `route_family`.

| Feature | Meaning |
| --- | --- |
| `request_count_sum_1d` | Was this route active in the current demo day? |
| `not_found_event_sum_1d` | Are users hitting broken paths? |
| `server_error_event_sum_1d` | Is this route failing? |
| `write_event_sum_1d` | Are users making mutating calls? |
| `request_time_seconds_average_1d` | Is the route getting slow? |
| `freshness_lag_seconds_last` | How stale is the latest served signal? |
| `freshness_lag_seconds_max_1d` | Worst freshness lag in the demo day |
| `access_event_struct_last10` | Recent explainable examples |

This is the main feature group. It lets the tutorial show a route that appears healthy, then reveal that the answer is based on logs from 30 minutes ago.

### Method Health

Keyed by `http_method`.

| Feature | Meaning |
| --- | --- |
| `request_count_sum_1d` | Which HTTP methods are active? |
| `write_event_sum_1d` | How much mutating traffic is happening? |
| `not_found_event_sum_1d` | Which methods are producing broken paths? |
| `server_error_event_sum_1d` | Which methods are failing? |
| `freshness_lag_seconds_last` | How fresh is the method-level view? |

This gives the demo an easy "GET vs PUT vs DELETE" surface.

## Tutorial Arc

### 1. Fetch A Route Health Signal

Fetch online features for a route users recognize:

```bash
zipline hub fetch \
  --name app.endpoint_health.endpoint_health__3 \
  -k '{"route_family":"/services/hub"}'
```

Healthy, fresh output should feel concrete:

```json
{
  "route_family": "/services/hub",
  "request_count_sum_1d": 82,
  "not_found_event_sum_1d": 0,
  "server_error_event_sum_1d": 0,
  "request_time_seconds_average_1d": 0.084,
  "freshness_lag_seconds_last": 47
}
```

That says the Hub route is active, successful, fast, and fresh.

### 2. Create Or Observe A Bad Request

Hit a route that does not exist, or wait for organic 404s from the public UI:

```bash
curl -i "${FRONTEND_URL}/definitely-not-a-real-route"
```

Then fetch the route family or method features again. In fresh mode, the 404 should show up quickly. In low-cost mode, it may not.

That is the first lesson: the platform can know a user just hit a broken path, but the online feature will not know until the datasource freshness catches up.

### 3. Pull The Freshness Lever

In `low_cost`, the online feature may say:

```json
{
  "route_family": "/definitely-not-a-real-route",
  "not_found_event_sum_1d": 0,
  "freshness_lag_seconds_last": 1810
}
```

That is the demo moment. The 404 happened, but the feature value is stale enough that the online answer misses it.

After switching to `balanced` or `fresh`, the same feature can become:

```json
{
  "route_family": "/definitely-not-a-real-route",
  "not_found_event_sum_1d": 1,
  "freshness_lag_seconds_last": 52
}
```

Same definition. Same platform. Better decision because the data is fresher.

### 4. Compare Offline And Online

The consistency check should compare the same route and time window:

```text
feature                         offline   online   delta
request_count_sum_1d            83        83       0
not_found_event_sum_1d          1         1        0
server_error_event_sum_1d       0         0        0
freshness_lag_seconds_last      52        52       0
freshness_status: fresh
```

And the stale case:

```text
feature                         offline   online   delta
request_count_sum_1d            83        79       -4
not_found_event_sum_1d          1         0        -1
server_error_event_sum_1d       0         0        0
freshness_lag_seconds_last      52        1810     +1758
freshness_status: stale_online_data
```

This is the "flying blind" moment. Without freshness as a feature, the stale online value looks like a valid answer.

## Configs

First configs:

- `app.endpoint_health.endpoint_health__3`
- `app.method_health.method_health__3`
- `app.client_activity.client_activity__3`

These are online GroupBys over `public_demo_app.ui_access_logs_iceberg`.

## Success Criteria

The case study is ready when:

1. The datasource Lambda writes parsed UI access logs to S3.
2. Glue exposes `public_demo_app.ui_access_logs_iceberg` with today's `ds` partition.
3. The configs compile.
4. A batch upload writes endpoint health features to the online store.
5. `zipline hub fetch` can fetch `/services/hub`, `/workflows`, `GET`, and `DELETE` keys.
6. The tutorial can show stale vs fresh behavior by changing `ui_logs_freshness_profile`.
