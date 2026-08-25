# Zipline Demo Quickstart

Example Zipline/Chronon configs for the public AWS demo environment.

The first dataset is Caltrain data from 511.org, landed by the demo infrastructure into AWS Glue/S3:

- `public_demo_caltrain.vehicle_positions`
- `public_demo_caltrain.trip_updates`
- `public_demo_caltrain.service_alerts`
- `public_demo_caltrain.gtfs_static`
- `public_demo_caltrain.schedule_files`
- `public_demo_caltrain.schedule_*`

The live public demo endpoints are:

- UI: `http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com`
- Hub: `http://k8s-ziplines-ziplineo-82549f7164-cb3dfbbafd5a0571.elb.us-west-2.amazonaws.com/services/hub`

Datasource freshness is controlled in the infrastructure repo with
`caltrain_freshness_profile` (`low_cost`, `balanced`, or `fresh`). This config
repo reads whatever cadence-produced snapshots are present in S3/Glue.

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
