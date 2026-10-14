# Explore advanced feature stats in five minutes

**Five minutes of hands-on time; compute runs asynchronously.** Start with a clean
checkout, the Zipline CLI, demo access, and permission to push a branch. The taxi
fixture and baseline backfill should be ready before you start (setup below).

## 1. See what you get already · 1 minute

Open the [taxi Join's offline metrics](https://try.zipline.ai/joins/app.taxi_feature_stats.taxi_feature_stats__1/offline/metrics?start=2026-09-17T00%3A00%3A00.000Z&end=2026-09-17T23%3A59%3A59.999Z).
This Join enriches 500 ride IDs with features such as distance, passenger count,
and pickup hour. Its [definition](../../configs/joins/app/taxi_feature_stats.py)
does **not** set `enable_stats_compute`.

For **September 17, 2026**, inspect **Row counts**, **Feature null counts**, and
**Feature null rates**. Zipline uses Iceberg file metadata for these charts, so
basic visibility is available without an extra stats job. The message asking
you to enable Stats Compute is expected: richer summaries aren't computed yet.

## 2. Create a branch and enable stats · 2 minutes

From the repository root:

```bash
git switch -c feature/advanced-feature-stats
```

In `configs/joins/app/taxi_feature_stats.py`, copy the existing `Join(...)` block
below itself. Name the copy `taxi_feature_stats_v2`, change its `version` to `2`,
and add one flag:

```diff
-taxi_feature_stats = Join(
+taxi_feature_stats_v2 = Join(
     ...
+    enable_stats_compute=True,
-    version=1,
+    version=2,
 )
```

Keep the original block to preserve the baseline for comparison. The flag is
what enables the additional computation.

```bash
cd configs
zipline compile
git add joins/app/taxi_feature_stats.py compiled/joins/app/taxi_feature_stats.*
git commit -m "Enable advanced stats for the taxi Join"
git push -u origin HEAD

CONF=compiled/joins/app/taxi_feature_stats.taxi_feature_stats_v2__2
zipline hub eval --skip-compile "$CONF" &&
zipline hub backfill --skip-compile "$CONF" \
  --start-ds 2026-09-17 --end-ds 2026-09-17
```

Follow the returned workflow link: a new **Stats Compute** step runs after the
Join output is ready. It reads feature values to calculate richer summaries,
adding compute work beyond the Iceberg metadata charts. Leave it running and
return when the whole workflow succeeds.

## 3. Read the richer metrics · 2 minutes

Open [v2's offline metrics](https://try.zipline.ai/joins/app.taxi_feature_stats.taxi_feature_stats_v2__2/offline/metrics?start=2026-09-17T00%3A00%3A00.000Z&end=2026-09-17T23%3A59%3A59.999Z),
keeping **September 17, 2026** selected. The existing charts remain; feature
tables now include statistics appropriate to each feature's type.

- **`id_distance`:** compare average, min/max, and standard deviation. Open the
  feature to inspect its distribution and quantiles. Does the upper tail suggest
  that the average hides unusually long rides?
- **`id_passenger_count`:** inspect the histogram and unique values. Which
  passenger count is most common? Are there zeros worth investigating?

You have moved from checking **how many rows arrived and what's missing** to
understanding **the values and their distribution**. The flag alone doesn't
populate these metrics: Stats Compute must finish for the selected dates.

---

**Demo preparation (outside the exercise).** If the source is missing, follow the
[taxi fixture setup](featurestore-benchmark.md), using `2026-09-17` as the
snapshot date throughout. From a clean, pushed checkout
containing this tutorial, run the baseline once from `configs`:

```bash
zipline hub eval compiled/joins/app/taxi_feature_stats.taxi_feature_stats__1 &&
zipline hub backfill compiled/joins/app/taxi_feature_stats.taxi_feature_stats__1 \
  --start-ds 2026-09-17 --end-ds 2026-09-17
```

Wait for success before the session. The Join is offline-only, with no recurring
schedule. Use a fresh variable name and version if v2 is already in use, and
adjust the compiled path and metrics link accordingly.
