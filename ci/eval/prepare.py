"""Compile a clean CI copy, localize file inputs, and discover the eval matrix."""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

import yaml

KINDS = ("group_bys", "joins", "staging_queries")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
TYPES = {"string", "int", "bigint", "double", "boolean"}


def load_spec(path):
    spec = yaml.safe_load(Path(path).read_text())
    if spec.get("version") != 1 or not spec.get("tables"):
        raise ValueError("Expected version: 1 and a nonempty tables mapping")
    aliases = set()
    for table, source in spec["tables"].items():
        if len(table.split(".")) != 2 or not all(IDENTIFIER.fullmatch(p) for p in table.split(".")):
            raise ValueError(f"Expected namespace.table identifier: {table}")
        schema = source["schema"]
        if not schema or any(not IDENTIFIER.fullmatch(c) or t not in TYPES for c, t in schema.items()):
            raise ValueError(f"Invalid column name or unsupported type: {table}")
        if not 1 <= len(source["rows"]) <= 2:
            raise ValueError(f"{table}: provide one or two rows")
        for row in source["rows"]:
            if set(row) != set(schema):
                raise ValueError(f"{table}: row columns must exactly match schema; use explicit nulls")
            for column, value in row.items():
                kind = schema[column]
                valid = value is None or (
                    (kind == "string" and isinstance(value, str))
                    or (kind in {"int", "bigint"} and type(value) is int)
                    or (kind == "double" and type(value) in {int, float})
                    or (kind == "boolean" and type(value) is bool)
                )
                if not valid:
                    raise ValueError(f"{table}.{column}: value does not match {kind}")
        if not set(source.get("partition_by", [])).issubset(schema):
            raise ValueError(f"{table}: unknown partition column")
        alias = source.get("sql_source")
        if alias:
            if alias in aliases:
                raise ValueError(f"Duplicate sql_source: {alias}")
            aliases.add(alias)
    return spec


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def localize(configs, spec):
    aliases = {v["sql_source"]: k for k, v in spec["tables"].items() if "sql_source" in v}
    replacements = []
    # Mirrors MetaDataOps.outputTable: explicit executionInfo override, otherwise
    # outputNamespace + sanitized config name. outputTable is not a JSON field.
    outputs = set()
    for config in configs:
        metadata = config["metaData"]
        override = metadata.get("executionInfo", {}).get("outputTableInfo", {}).get("table")
        outputs.add(override or metadata["outputNamespace"] + "." + re.sub(r"[^A-Za-z0-9_]", "_", metadata["name"]))
    overlap = outputs & spec["tables"].keys()
    if overlap:
        raise ValueError(f"Seed only upstream sources; output fixtures bypass eval: {sorted(overlap)}")
    for config in configs:
        for node in walk(config):
            if isinstance(node.get("query"), str):
                for original, table in aliases.items():
                    if original in node["query"]:
                        node["query"] = node["query"].replace(original, table)
                        replacements.append({"config": config["metaData"]["name"], "from": original, "to": table})
                if re.search(r"\b(?:parquet|orc|csv|json|delta)\s*\.\s*`", node["query"], re.I):
                    raise ValueError(f"Unmapped file source in {config['metaData']['name']}; add sql_source to sources.yaml")
            for field in ("table", "snapshotTable", "mutationTable"):
                table = node.get(field)
                if table and table not in outputs and table not in spec["tables"]:
                    raise ValueError(f"Missing upstream fixture: {table}")
    return replacements


def prepare(repo, output):
    spec = load_spec(repo / "ci/eval/sources.yaml")
    root = output / "configs"
    # Refuse reuse so deleted configs and stale compiled outputs cannot enter CI.
    root.mkdir(parents=True, exist_ok=False)
    for folder in (*KINDS, "sources", "models"):
        if (repo / "configs" / folder).exists():
            shutil.copytree(repo / "configs" / folder, root / folder,
                            ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(repo / "configs/teams.py", root / "teams.py")
    subprocess.run(["zipline", "compile"], cwd=root, check=True)
    paths = sorted(p for kind in KINDS for p in (root / "compiled" / kind).rglob("*") if p.is_file())
    if not paths or len(paths) > 256:
        raise ValueError(f"Expected 1–256 configs for the GitHub matrix, got {len(paths)}")
    configs = [json.loads(p.read_text()) for p in paths]
    replacements = localize(configs, spec)
    matrix = []
    names = set()
    for path, config in zip(paths, configs):
        name = config["metaData"]["name"]
        if name in names or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError(f"Duplicate or invalid config name: {name}")
        names.add(name)
        kind = path.relative_to(root / "compiled").parts[0]
        matrix.append({"name": name, "kind": kind})
        path.write_text(json.dumps(config, indent=2) + "\n")
    (output / "sources.json").write_text(json.dumps(spec, indent=2) + "\n")
    (output / "rewrites.json").write_text(json.dumps(replacements, indent=2) + "\n")
    (output / "matrix.json").write_text(json.dumps({"include": matrix}) + "\n")
    print(f"Prepared {len(matrix)} eval targets and {len(spec['tables'])} sources; models excluded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.repo.resolve(), args.output.resolve())
