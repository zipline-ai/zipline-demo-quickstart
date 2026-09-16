#!/usr/bin/env python3
"""Prepare the featurestore.org taxi snapshot; --apply creates its Iceberg table."""

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date
from pathlib import Path
from urllib.request import urlopen

URL = "https://repo.hops.works/dev/davit/nyc_taxi/rides500.csv"
SHA256 = "6dc1e769b5ab60929ce5633c4a59c40ffc358ee8c253d2d605eeee3c23ef1620"
TABLE = "public_demo_app.featurestore_benchmark_taxi"
LOCATION = "s3://zipline-public-demo-curated/app/featurestore_benchmark_taxi"
COLUMNS = (
    "id", "ride_id", "pickup_datetime", "pickup_longitude", "dropoff_longitude",
    "pickup_latitude", "dropoff_latitude", "passenger_count", "taxi_id", "driver_id",
    "distance", "pickup_distance_to_jfk", "dropoff_distance_to_jfk",
    "pickup_distance_to_ewr", "dropoff_distance_to_ewr", "pickup_distance_to_lgr",
    "dropoff_distance_to_lgr", "year", "weekday", "hour",
)
INTEGER_COLUMNS = {"id", "pickup_datetime", "passenger_count", "taxi_id", "driver_id", "year", "weekday", "hour"}
COLUMN_TYPES = {name: "int64" if name in INTEGER_COLUMNS else "string" if name == "ride_id" else "float64" for name in COLUMNS}
COLUMN_TYPES["ds"] = "string"


def parse_rows(raw, snapshot_date):
    """Validate upstream bytes before parsing explicitly typed, non-null rows."""
    if date.fromisoformat(snapshot_date).isoformat() != snapshot_date:
        raise ValueError("snapshot_date must use YYYY-MM-DD")
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("Upstream dataset checksum changed; review before using it")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if reader.fieldnames != ["", *COLUMNS[1:]]:
        raise ValueError("Unexpected upstream taxi columns")
    rows = []
    for source in reader:
        if None in source or any(value in (None, "") for value in source.values()):
            raise ValueError("Missing or extra CSV values")
        row = {}
        for name in COLUMNS:
            value = source["" if name == "id" else name]
            if name in INTEGER_COLUMNS:
                value = int(value)
                if not -(2**63) <= value < 2**63:
                    raise ValueError(f"{name} is outside int64 range")
            elif name != "ride_id":
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(f"{name} must be finite")
            row[name] = value
        row["ds"] = snapshot_date
        rows.append(row)
    if len(rows) != 500 or len({row["id"] for row in rows}) != 500:
        raise ValueError("Expected 500 rows with unique integer IDs")
    return rows


def prepare(raw, snapshot_date, output):
    rows = parse_rows(raw, snapshot_date)
    output.mkdir(parents=True, exist_ok=True)
    (output / "rides500.original.csv").write_bytes(raw)
    with (output / "rides500.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMN_TYPES)
        writer.writeheader()
        writer.writerows(rows)
    documents = {
        "keys.json": [{"id": row["id"]} for row in rows],
        "expected.json": [{"keys": {"id": row["id"]}, "features": {name: row[name] for name in COLUMNS if name != "id"}} for row in rows],
        "manifest.json": {
            "source": URL, "sha256": SHA256, "rows": len(rows),
            "snapshot_date": snapshot_date, "table": TABLE, "location": LOCATION,
            "schema": COLUMN_TYPES,
            "transformation": "Rename unnamed CSV index to int64 id; add string ds snapshot partition",
        },
    }
    for name, document in documents.items():
        (output / name).write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    return rows


def apply(rows, region):
    """Create a new table only. Existing tables require explicit operator review."""
    import boto3
    import pyarrow as pa
    from pyiceberg.catalog import load_catalog
    from pyiceberg.exceptions import NoSuchTableError
    from pyiceberg.partitioning import PartitionField, PartitionSpec
    from pyiceberg.schema import Schema
    from pyiceberg.transforms import IdentityTransform
    from pyiceberg.types import DoubleType, LongType, NestedField, StringType

    catalog = load_catalog("glue", **{
        "type": "glue", "glue.region": region, "s3.region": region,
        "warehouse": LOCATION,
    })
    try:
        catalog.load_table(TABLE)
    except NoSuchTableError:
        pass
    else:
        raise ValueError(f"Refusing to modify existing table {TABLE}; review its data before retrying")
    # Also reject orphaned data from an interrupted earlier attempt.
    bucket, prefix = LOCATION.removeprefix("s3://").split("/", 1)
    existing = boto3.client("s3", region_name=region).list_objects_v2(
        Bucket=bucket, Prefix=prefix + "/", MaxKeys=1,
    )
    if existing.get("KeyCount", 0):
        raise ValueError(f"Refusing to reuse nonempty prefix {LOCATION}")
    iceberg_types = {"int64": LongType(), "float64": DoubleType(), "string": StringType()}
    arrow_types = {"int64": pa.int64(), "float64": pa.float64(), "string": pa.string()}
    schema = Schema(*[
        NestedField(field_id=index, name=name, field_type=iceberg_types[kind], required=False)
        for index, (name, kind) in enumerate(COLUMN_TYPES.items(), start=1)
    ])
    arrow_schema = pa.schema([pa.field(name, arrow_types[kind]) for name, kind in COLUMN_TYPES.items()])
    batch = pa.Table.from_pylist(rows, schema=arrow_schema)
    table = catalog.create_table(
        TABLE, schema=schema, location=LOCATION,
        partition_spec=PartitionSpec(PartitionField(
            source_id=schema.find_field("ds").field_id, field_id=1000,
            transform=IdentityTransform(), name="ds",
        )),
        properties={"format-version": "2", "write.parquet.compression-codec": "snappy"},
    )
    table.append(batch)
    stored = table.scan().to_arrow().to_pylist()
    if sorted(stored, key=lambda row: row["id"]) != sorted(rows, key=lambda row: row["id"]):
        raise RuntimeError("Iceberg readback differs from the prepared snapshot; review before deploying")
    return table.current_snapshot().snapshot_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--input", type=Path, help="Previously downloaded original CSV; checksum is still required")
    parser.add_argument("--output", type=Path, default=Path("data/featurestore-benchmark-taxi"))
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--apply", action="store_true", help="Create the Glue Iceberg table and write S3 data")
    args = parser.parse_args()
    if args.input:
        raw = args.input.read_bytes()
    else:
        with urlopen(URL, timeout=30) as response:
            raw = response.read()
    rows = prepare(raw, args.snapshot_date, args.output)
    print(f"Prepared {len(rows)} records in {args.output}")
    if args.apply:
        snapshot_id = apply(rows, args.region)
        receipt = {"table": TABLE, "location": LOCATION, "region": args.region, "snapshot_id": snapshot_id, "rows": len(rows), "ds": args.snapshot_date}
        (args.output / "applied.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"Created and verified {TABLE}, Iceberg snapshot {snapshot_id}")
    else:
        print("No AWS calls made. Add --apply to provision the snapshot.")


if __name__ == "__main__":
    main()
