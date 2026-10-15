import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prepare import load_spec, localize
from run_eval import check_response, computation_failures, evaluate


SPEC = Path(__file__).with_name("sources.yaml")


class FixtureTests(unittest.TestCase):
    def test_committed_spec_is_tiny_and_typed(self):
        spec = load_spec(SPEC)
        self.assertTrue(spec["tables"])
        for source in spec["tables"].values():
            self.assertIn(len(source["rows"]), (1, 2))

    def test_invalid_fixtures_fail_before_spark(self):
        import yaml

        spec = load_spec(SPEC)
        table = next(iter(spec["tables"]))
        for mutation in ("too_many_rows", "missing_column", "wrong_type"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                bad = copy.deepcopy(spec)
                source = bad["tables"][table]
                if mutation == "too_many_rows":
                    source["rows"] *= 3
                elif mutation == "missing_column":
                    del source["rows"][0]["ds"]
                else:
                    source["rows"][0]["event_ts"] = "not-a-long"
                path = Path(directory) / "spec.yaml"
                path.write_text(yaml.safe_dump(bad))
                with self.assertRaises(ValueError):
                    load_spec(path)

    def test_file_input_rewrite_preserves_sql_and_generated_dependency(self):
        spec = load_spec(SPEC)
        original = spec["tables"]["ci_raw.instacart_orders"]["sql_source"]
        configs = [
            {"metaData": {"name": "team.orders__1", "outputNamespace": "demo"},
             "query": f"SELECT order_id + 1 AS next_id FROM {original}"},
            {"metaData": {"name": "team.features__1", "outputNamespace": "demo"},
             "sources": [{"events": {"table": "demo.team_orders__1"}}]},
        ]
        untouched = copy.deepcopy(configs[1])
        replacements = localize(configs, spec)
        self.assertEqual(configs[0]["query"], "SELECT order_id + 1 AS next_id FROM ci_raw.instacart_orders")
        self.assertEqual(configs[1], untouched)
        self.assertEqual(replacements[0]["from"], original)

    def test_new_source_and_output_fixture_are_rejected(self):
        config = {"metaData": {"name": "team.config__1", "outputNamespace": "demo"},
                  "sources": [{"events": {"table": "demo.missing"}}]}
        spec = load_spec(SPEC)
        with self.assertRaisesRegex(ValueError, "Missing upstream fixture"):
            localize([config], spec)
        config["sources"] = []
        spec["tables"]["demo.team_config__1"] = {}
        with self.assertRaisesRegex(ValueError, "bypass eval"):
            localize([config], spec)

    def test_unmapped_file_source_rejected(self):
        config = {"metaData": {"name": "team.config__1", "outputNamespace": "demo"},
                  "query": "SELECT * FROM parquet.`s3://new-bucket/data/`"}
        with self.assertRaisesRegex(ValueError, "Unmapped file source"):
            localize([config], load_spec(SPEC))


class ResponseTests(unittest.TestCase):
    def test_swallowed_computation_errors_are_exposed(self):
        for kind in ("GroupBy", "Join", "StagingQuery"):
            log = f"ERROR Failed to run {kind} computation for demo.output\nAnalysisException: missing ts\nstack trace"
            self.assertIn("missing ts", computation_failures(log))
        self.assertEqual(computation_failures("WARN NoSuchObjectException: default database\nINFO ready"), "")

    def test_failure_even_with_http_success(self):
        for result in ({}, {"success": False}, {"success": 0}, {"success": 2}, {"success": 1.0}, {"success": "true"},
                       {"success": True, "upstreamResponse": [{"success": False}]}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                check_response(result)

    def test_success_with_upstream(self):
        check_response({"success": True, "upstreamResponse": [{"success": True}]})
        check_response({"success": 1, "upstreamResponse": [{"success": 1}]})

    def test_failed_response_is_saved_for_debugging(self):
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen") as request:
            result = {"confName": "app.failed", "success": False, "errors": ["missing column"]}
            request.return_value.__enter__.return_value.read.return_value = json.dumps(result).encode()
            with self.assertRaises(ValueError):
                evaluate("http://localhost:8080", "app.failed", Path(directory))
            self.assertEqual(json.loads((Path(directory) / "response.json").read_text()), result)


if __name__ == "__main__":
    unittest.main()
