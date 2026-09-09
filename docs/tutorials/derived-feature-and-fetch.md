# Create And Fetch A Derived Feature In Two Minutes

This tutorial adds one decision-ready feature to the request-context join, deploys it, and fetches it online.

## 1. Add The Derivation

Open `configs/joins/app/client_request_context.py` and add this item to `derivations`:

```python
Derivation(
    name="needs_attention",
    expression=(
        "CASE WHEN route_family_server_error_event_sum_1d > 0 "
        "OR client_ip_freshness_lag_seconds_last > 900 "
        "THEN 1 ELSE 0 END"
    ),
),
```

Change the join's `version` from `2` to `3`. The feature now answers a useful question: should we trust this route's current health, or investigate errors or stale data?

## 2. Compile And Deploy

From the `configs` directory:

```bash
export HUB_URL="https://try.zipline.ai/services/hub"
export FETCHER_URL="https://try.zipline.ai/services/fetcher"

zipline compile
zipline hub eval \
  compiled/joins/app/client_request_context.client_request_context__3 \
  --hub-url "$HUB_URL"
zipline hub run-adhoc \
  compiled/joins/app/client_request_context.client_request_context__3 \
  --hub-url "$HUB_URL" \
  --skip-compile \
  --yes
```

Wait for the workflow link printed by `run-adhoc` to report success.

## 3. Fetch It

Use a `client_ip` visible in `public_demo_app.ui_access_logs_iceberg` and a route such as `/`:

```bash
zipline hub fetch \
  compiled/joins/app/client_request_context.client_request_context__3 \
  --hub-url "$HUB_URL" \
  --fetcher-url "$FETCHER_URL" \
  --key-json '{"client_ip":"YOUR_PUBLIC_IP","route_family":"/"}' \
  --format json
```

Look for `needs_attention` in the response. A value of `1` means the route has seen a server error in the one-day window or its latest client signal is more than 15 minutes stale. The expression is evaluated consistently for offline computation and online fetching; no second serving implementation is required.

