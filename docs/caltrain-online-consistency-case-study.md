# Caltrain Online Consistency Case Study

This case study is the tutorial path for the public Zipline demo. It uses Caltrain data from the 511 SF Bay Open Transit Data portal to show how a team can evolve online datasets, fetch live serving signals, and measure whether offline and online feature values stay consistent.

511 publishes Bay Area transit data as GTFS static feeds, GTFS-Realtime feeds for trip updates, vehicle positions, and service alerts, plus SIRI/NeTEx APIs for stop and vehicle monitoring. The public demo starts with a low-cost batch ingestion path and leaves room to turn the freshness dial up later.

Source: https://511.org/open-data/transit

## Story

A Caltrain operations or rider-experience team wants to build features that describe how fresh and stable transit data is:

- Which schedule files changed recently?
- Are the latest schedule snapshots available for offline training and online serving?
- Can a feature be fetched online for a route, stop, vehicle, or schedule file?
- Do the feature values fetched online match the values produced offline for the same keys and timestamp?
- What changes when the public demo freshness profile moves from a low-cost weekly cadence toward fresher polling?

The main lesson is that feature definitions should be portable across offline backfills, online batch uploads, and eventually streaming updates.

## Current Dataset

The infrastructure lands Caltrain data into AWS Glue/S3. The first working config path focuses on schedule file snapshots:

- Raw/curated source: `public_demo_caltrain.schedule_files`
- Staging query: `caltrain.schedule_files_import.v1__8`
- Online GroupBy: `caltrain.schedule_file_activity.schedule_file_activity__16`
- Join: `caltrain.schedule_snapshot.v1__16`
- Online KV backend: DynamoDB tables prefixed with `PUBLIC_DEMO_`

The current GroupBy is intentionally simple. It keys by `file_name` and computes:

- `content_sha256_count_1d`
- `content_sha256_count_7d`
- `row_count_average_1d`
- `row_count_average_7d`
- `snapshot_hour_last5`

This is enough to show end-to-end consistency before we add more realistic realtime feeds.

## Demo Walkthrough

### 1. Compile The Configs

```bash
cd /Users/cristian/zipline/zipline-demo-quickstart/configs
export PYTHONPATH="$(pwd):${PYTHONPATH}"
zipline compile
```

Expected result:

- `compiled/staging_queries/caltrain/schedule_files_import.v1__8`
- `compiled/group_bys/caltrain/schedule_file_activity.schedule_file_activity__16`
- `compiled/joins/caltrain/schedule_snapshot.v1__16`

### 2. Produce Offline Feature Data

Run the join for a known demo partition:

```bash
zipline hub backfill compiled/joins/caltrain/schedule_snapshot.v1__16 \
  --chronon-root /Users/cristian/zipline/zipline-demo-quickstart/configs \
  --hub-url http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com/services/hub \
  --no-use-auth \
  --start-ds 2026-08-26 \
  --end-ds 2026-08-26 \
  --concurrency 1 \
  --force \
  --skip-compile \
  -y
```

Proof point:

- The join table `public_demo_data.caltrain_schedule_snapshot_v1__16` contains the offline values for the same feature definitions used online.

### 3. Deploy The Online Dataset

Run an adhoc online deploy for the GroupBy:

```bash
zipline hub run-adhoc compiled/group_bys/caltrain/schedule_file_activity.schedule_file_activity__16 \
  --chronon-root /Users/cristian/zipline/zipline-demo-quickstart/configs \
  --hub-url http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com/services/hub \
  --no-use-auth \
  --end-ds 2026-08-26 \
  --skip-compile \
  --force \
  -y
```

Proof points from the current demo:

- GroupBy upload writes Ion files to `s3://zipline-public-demo-warehouse/data/ion_uploads/...__16__upload/ds=2026-08-26/`.
- DynamoDB ImportTable imports 20 items into a `PUBLIC_DEMO_CALTRAIN_...__16_...` physical table.
- `PUBLIC_DEMO_CHRONON_BATCH_TABLE_REGISTRY` maps the logical v16 batch dataset to that physical table.

### 4. Fetch Online Features

Use the Hub fetch endpoint or CLI fetch command to fetch the GroupBy for one schedule file key. Pick a key from the offline output or source data.

Example shape:

```bash
zipline hub fetch \
  --hub-url http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com/services/hub \
  --no-use-auth \
  --name caltrain.schedule_file_activity.schedule_file_activity__16 \
  -k '{"file_name":"<schedule-file-name>"}'
```

The tutorial should show one concrete key once the source snapshot chosen for the public walkthrough is stable.

### 5. Compare Offline And Online Values

For the same `file_name`, compare:

- Offline values in `public_demo_data.caltrain_schedule_snapshot_v1__16`
- Online values returned by fetch for `caltrain.schedule_file_activity.schedule_file_activity__16`

The consistency check should report:

- Matching feature names
- Matching key
- Offline partition date
- Online batch table version from `PUBLIC_DEMO_CHRONON_BATCH_TABLE_REGISTRY`
- Value deltas, ideally zero for the schedule-file features

This becomes the core tutorial moment: the user sees the same definitions produce training data and online serving values.

## Dataset Evolution Path

### Step A: Schedule File Quality

Status: working.

This is the current `schedule_file_activity` GroupBy. It demonstrates config authoring, offline backfill, online upload, DynamoDB serving, and offline/online comparison with a small, cheap dataset.

### Step B: Vehicle Position Freshness

Next config to add:

- Source: `public_demo_caltrain.vehicle_positions`
- 511 feed: GTFS-Realtime Vehicle Positions
- Key: `vehicle_id` or `trip_id`
- Features:
  - latest observed latitude/longitude timestamp
  - position update count over 15 minutes and 1 hour
  - seconds since last observation
  - distinct trip count per vehicle over 1 day

This is the first place to show "realtime" signals. We can initially compute it from periodic snapshots written by the CloudRun poller, then later swap the ingestion edge to a streaming source without changing the user-facing feature definition story.

### Step C: Trip Update Delay Signals

Next config to add:

- Source: `public_demo_caltrain.trip_updates`
- 511 feed: GTFS-Realtime Trip Updates
- Key: `trip_id`, optionally `stop_id`
- Features:
  - latest delay seconds
  - average delay over 15 minutes and 1 hour
  - stop update count
  - percent of updates with missing delay

This shows online features that are useful to rider-facing predictions and alerting.

### Step D: Route And Stop Reliability

Next config to add:

- Source: `public_demo_caltrain.service_alerts`, plus static GTFS route/stop metadata
- 511 feeds/APIs: GTFS-Realtime Service Alerts, Stops, Lines, Stop Monitoring
- Keys: `route_id`, `stop_id`
- Features:
  - active alert count by route
  - scheduled departures by stop
  - observed versus scheduled update freshness
  - service disruption indicator

This creates a richer tutorial where users can fetch online features for a route or stop they recognize.

## Freshness Lever

The public demo intentionally starts cheap. The infrastructure owns the ingestion cadence through `caltrain_freshness_profile`:

- `low_cost`: sparse snapshots for demos and tutorials
- `balanced`: more frequent polling for stronger freshness examples
- `fresh`: higher cadence for realtime-style demos

The tutorial should ask the user to run the same offline/online comparison before and after a freshness profile change. The expected observation is that feature definitions remain stable while the data freshness and cost profile change.

## What We Should Build Next

1. Add a small comparison script that fetches one online key and queries the matching offline row.
2. Add vehicle position parsing configs over `public_demo_caltrain.vehicle_positions`.
3. Add trip update delay configs over `public_demo_caltrain.trip_updates`.
4. Add a stable tutorial seed key file so the public walkthrough always has known keys.
5. Add a scheduled v16 online deploy once the tutorial key and fetch command are stable.

## Success Criteria

The case study is ready for users when:

- A user can compile configs from a clean checkout.
- A user can run one backfill and one online deploy.
- A user can fetch at least one online feature vector.
- A user can run an offline/online consistency check and see matching values.
- The tutorial explains which 511 feeds are batch snapshots today and which ones are candidates for streaming.
