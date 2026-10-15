"""Run inside local-eval to build the shared Iceberg input warehouse once."""

import argparse
import json
from pathlib import Path


def literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build(spec_path, warehouse):
    from pyspark.sql import SparkSession

    if Path(warehouse).exists() and any(Path(warehouse).iterdir()):
        raise ValueError("Warehouse must be empty; build it only once per run")
    spec = json.loads(Path(spec_path).read_text())
    spark = (SparkSession.builder.master("local[2]").appName("demo-ci-warehouse")
             .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.4.3")
             .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
             .config("spark.sql.catalog.ci_catalog", "org.apache.iceberg.spark.SparkCatalog")
             .config("spark.sql.catalog.ci_catalog.type", "hadoop")
             .config("spark.sql.catalog.ci_catalog.warehouse", warehouse)
             .config("spark.sql.shuffle.partitions", "1")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.ui.enabled", "false").getOrCreate())
    try:
        for table, source in spec["tables"].items():
            namespace, _ = table.split(".")
            spark.sql(f"CREATE NAMESPACE IF NOT EXISTS ci_catalog.{namespace}")
            columns = ", ".join(f"`{name}` {kind}" for name, kind in source["schema"].items())
            partitions = source.get("partition_by", [])
            partition_sql = " PARTITIONED BY (" + ", ".join(f"`{p}`" for p in partitions) + ")" if partitions else ""
            spark.sql(f"CREATE TABLE ci_catalog.{table} ({columns}) USING iceberg{partition_sql}")
            rows = ", ".join("(" + ", ".join(literal(row[c]) for c in source["schema"]) + ")" for row in source["rows"])
            spark.sql(f"INSERT INTO ci_catalog.{table} VALUES {rows}")
            count = spark.table(f"ci_catalog.{table}").count()
            if count != len(source["rows"]):
                raise RuntimeError(f"Row count mismatch for {table}: {count}")
            print(f"{table}: {count} rows", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--warehouse", default="/warehouse")
    args = parser.parse_args()
    build(args.spec, args.warehouse)
