"""Offline integrity and schema tests for the taxi snapshot loader."""

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import provision_taxi as taxi


def fixture(count=500):
    handle = io.StringIO()
    writer = csv.writer(handle)
    writer.writerow(["", *taxi.COLUMNS[1:]])
    for index in range(count):
        writer.writerow([
            index if name == "id" else "ride" if name == "ride_id" else 1592984700000 if name == "pickup_datetime" else 2 if name in taxi.INTEGER_COLUMNS else 1.25
            for name in taxi.COLUMNS
        ])
    return handle.getvalue().encode()


class TaxiPreparationTest(unittest.TestCase):
    def parse(self, raw, snapshot_date="2026-09-16"):
        with patch.object(taxi, "SHA256", hashlib.sha256(raw).hexdigest()):
            return taxi.parse_rows(raw, snapshot_date)

    def test_iceberg_schema_and_readback_without_aws(self):
        try:
            import boto3
            from pyiceberg.exceptions import NoSuchTableError
            from pyiceberg.io.pyarrow import _check_pyarrow_schema_compatible
        except ImportError:
            self.skipTest("Optional AWS loader dependencies are not installed")
        rows = self.parse(fixture())
        catalog = MagicMock()
        catalog.load_table.side_effect = NoSuchTableError("absent")
        table = catalog.create_table.return_value

        def append(batch):
            schema = catalog.create_table.call_args.kwargs["schema"]
            _check_pyarrow_schema_compatible(schema, batch.schema)
            self.assertEqual(batch.num_rows, 500)
            partition = catalog.create_table.call_args.kwargs["partition_spec"].fields[0]
            self.assertEqual(partition.source_id, schema.find_field("ds").field_id)
            table.scan.return_value.to_arrow.return_value = batch

        table.append.side_effect = append
        with patch("pyiceberg.catalog.load_catalog", return_value=catalog) as load, patch.object(boto3, "Session") as session, patch.object(boto3, "client") as legacy_client:
            credentials = session.return_value.get_credentials.return_value.get_frozen_credentials.return_value
            credentials.access_key = "test-access"
            credentials.secret_key = "test-secret"
            credentials.token = "test-session-token"
            session.return_value.client.return_value.list_objects_v2.return_value = {"KeyCount": 0}
            legacy_client.return_value.list_objects_v2.return_value = {"KeyCount": 0}
            taxi.apply(rows, "us-west-2")
            properties = load.call_args.kwargs
            self.assertEqual(properties.get("client.access-key-id"), "test-access")
            self.assertEqual(properties.get("client.secret-access-key"), "test-secret")
            self.assertEqual(properties.get("client.session-token"), "test-session-token")
            session.return_value.client.assert_called_once_with("s3")
            legacy_client.assert_not_called()
        table.append.assert_called_once()

    def test_checksum_rejects_modified_data(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            taxi.parse_rows(fixture(), "2026-09-16")

    def test_schema_preserves_integer_timestamps_and_features(self):
        rows = self.parse(fixture())
        self.assertEqual(len(rows), 500)
        self.assertEqual(rows[0]["pickup_datetime"], 1592984700000)
        for name, kind in taxi.COLUMN_TYPES.items():
            self.assertIs(type(rows[0][name]), {"int64": int, "float64": float, "string": str}[kind])
        self.assertEqual(rows[0]["ds"], "2026-09-16")

    def test_wrong_row_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "500 rows"):
            self.parse(fixture(499))

    def test_duplicate_keys_are_rejected(self):
        raw = fixture().replace(b"\r\n1,", b"\r\n0,", 1)
        with self.assertRaisesRegex(ValueError, "unique integer IDs"):
            self.parse(raw)

    def test_unexpected_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "columns"):
            self.parse(fixture().replace(b"ride_id", b"renamed", 1))

    def test_nonfinite_features_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            self.parse(fixture().replace(b"1.25", b"NaN", 1))

    def test_invalid_dates_are_rejected(self):
        for day in ("20260916", "2026-02-30", "2026-9-16"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.parse(fixture(), day)

    def test_prepared_artifacts_agree_and_exclude_partition_from_features(self):
        raw = fixture()
        with tempfile.TemporaryDirectory() as directory, patch.object(taxi, "SHA256", hashlib.sha256(raw).hexdigest()):
            output = Path(directory)
            rows = taxi.prepare(raw, "2026-09-16", output)
            manifest = json.loads((output / "manifest.json").read_text())
            expected = json.loads((output / "expected.json").read_text())
            keys = json.loads((output / "keys.json").read_text())
            self.assertEqual(manifest["schema"], taxi.COLUMN_TYPES)
            self.assertEqual(manifest["rows"], 500)
            self.assertEqual(keys, [row["keys"] for row in expected])
            self.assertEqual(len(expected[0]["features"]), 19)
            self.assertEqual(expected[0]["features"], {name: rows[0][name] for name in taxi.COLUMNS if name != "id"})
            self.assertEqual((output / "rides500.original.csv").read_bytes(), raw)
            with (output / "rides500.csv").open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 500)


if __name__ == "__main__":
    unittest.main()
