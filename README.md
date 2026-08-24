# Zipline Demo Quickstart

Example Zipline/Chronon configs for the public GCP demo environment.

The first dataset is Caltrain data from 511.org, landed by the demo infrastructure into:

- `public-demo-506218.public_demo_caltrain_raw.vehicle_positions_raw`
- `public-demo-506218.public_demo_caltrain_raw.trip_updates_raw`
- `public-demo-506218.public_demo_caltrain_raw.service_alerts_raw`
- `public-demo-506218.public_demo_caltrain_raw.gtfs_static_rows`
- `public-demo-506218.public_demo_caltrain_curated.*`

## Compile

```bash
cd configs
export PYTHONPATH="$(pwd):$PYTHONPATH"
zipline compile
```

Or from the repository root:

```bash
./scripts/compile.sh
```
