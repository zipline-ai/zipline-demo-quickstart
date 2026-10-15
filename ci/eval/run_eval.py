"""Evaluate one config in its own container, preserving its response and server log."""

import argparse
import json
import os
import subprocess
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


def check_response(result):
    """Do not let HTTP 200, malformed responses, or a failed ancestor pass CI."""
    # Thrift's JSON codec emits booleans as 0/1; also accept ordinary JSON bools.
    flag = result.get("success") if isinstance(result, dict) else None
    if type(flag) not in (bool, int) or flag != 1:
        raise ValueError("Eval returned failure or no explicit success; see response.json")
    for upstream in result.get("upstreamResponse") or []:
        check_response(upstream)


def format_response(result, depth=0):
    if not isinstance(result, dict):
        return repr(result)
    prefix = "  " * depth
    flag = result.get("success")
    status = "PASS" if type(flag) in (bool, int) and flag == 1 else "FAIL"
    lines = [f"{prefix}{status} {result.get('confName', '<unknown>')}"]
    message = result.get("shortMessage") if status == "PASS" else result.get("message")
    if message:
        lines.append(str(message))
    lines.extend(str(error) for error in result.get("errors") or [])
    lines.extend(format_response(upstream, depth + 1) for upstream in result.get("upstreamResponse") or [])
    return "\n".join(lines)


def computation_failures(log):
    """The pinned eval handlers can swallow compute errors and return success."""
    markers = tuple(f"Failed to run {kind} computation" for kind in ("GroupBy", "Join", "StagingQuery"))
    lines = log.splitlines()
    return "\n".join("\n".join(lines[index:index + 2]) for index, line in enumerate(lines)
                     if any(marker in line for marker in markers))


def evaluate(url, name, output):
    payload = {"confName": name, "parameters": {"startDate": "2026-08-01", "endDate": "2026-09-04"}}
    (output / "request.json").write_text(json.dumps(payload, indent=2) + "\n")
    request = urllib.request.Request(url + "/eval", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as error:
        (output / "response.txt").write_bytes(error.read())
        raise
    (output / "response.txt").write_text(body)
    result = json.loads(body)
    (output / "response.json").write_text(json.dumps(result, indent=2) + "\n")
    readable = format_response(result)
    (output / "eval.log").write_text(readable + "\n")
    print(readable, flush=True)
    check_response(result)
    if result.get("confName") != name:
        raise ValueError(f"Unexpected response config: {result.get('confName')}")


def run(image, bundle, name, output):
    output.mkdir(parents=True, exist_ok=True)
    container = "demo-eval-" + uuid.uuid4().hex[:12]
    started = False
    success = False
    detail = ""
    try:
        # /warehouse is also the builder's path: Iceberg metadata embeds absolute
        # paths. The host artifact may move, but this container path must not.
        docker("run", "--detach", "--platform", "linux/amd64", "--name", container,
               "--cpus", "2", "--memory", "5g", "-p", "127.0.0.1::8080",
               "-v", f"{bundle / 'configs'}:/configs:ro",
               "-v", f"{bundle / 'warehouse'}:/warehouse:ro",
               "-e", "CHRONON_ROOT=/configs", "-e", "CHRONON_EVAL_WAREHOUSE_PATH=/warehouse",
               "-e", "CHRONON_EVAL_WAREHOUSE_CATALOG=ci_catalog", "-e", "SERVER_PORT=8080",
               "-e", "JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -Xmx3g", image)
        started = True
        port = docker("port", container, "8080/tcp").rsplit(":", 1)[1]
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 180
        while True:
            try:
                with urllib.request.urlopen(url + "/ping", timeout=3) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            if docker("inspect", "-f", "{{.State.Running}}", container) != "true":
                raise RuntimeError("Eval container exited before becoming ready")
            if time.monotonic() >= deadline:
                raise TimeoutError("Eval service did not become ready within 180 seconds")
            time.sleep(2)
        evaluate(url, name, output)
        success = True
    except Exception as error:
        detail = traceback.format_exc()
        if isinstance(error, subprocess.CalledProcessError):
            detail += "\nDocker output:\n" + (error.output or "")
        print(detail, flush=True)
    finally:
        if started:
            with (output / "server.log").open("w") as log:
                subprocess.run(["docker", "logs", container], stdout=log, stderr=subprocess.STDOUT, check=False)
            failures = computation_failures((output / "server.log").read_text())
            if failures:
                success = False
                detail += "\nEval computation failed (the service may still report success):\n" + failures
                (output / "computation-errors.log").write_text(failures + "\n")
                with (output / "eval.log").open("a") as log:
                    log.write("\nFAIL: sample computation fell back to schema validation\n" + failures + "\n")
                print(failures, flush=True)
            subprocess.run(["docker", "rm", "-f", container], check=False)
        (output / "result.json").write_text(json.dumps({"config": name, "success": success, "error": detail}, indent=2) + "\n")
        summary = f"### {name}\n\n{'PASS' if success else 'FAIL'}\n\n"
        summary += "Full response, upstream errors, and isolated server log are in this job's eval artifact.\n"
        if detail:
            summary += f"\n```text\n{detail}\n```\n"
        (output / "summary.md").write_text(summary)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
                stream.write(summary)
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.image, args.bundle.resolve(), args.name, args.output.resolve()))
