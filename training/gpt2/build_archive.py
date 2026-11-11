"""Build a deterministic, content-addressed Ray working-directory archive."""

import argparse
import json
import re
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
ARCHIVE_SOURCES = [ROOT / "setup.py", *sorted((ROOT / "trainer").glob("*.py"))]


def _archive_bytes(path: Path) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source in ARCHIVE_SOURCES:
            relative = source.relative_to(ROOT).as_posix()
            info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3  # Unix metadata on every host, including Windows.
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info, source.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="Published AMD64 image@sha256 digest"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", args.image):
        raise ValueError("A registry image digest is required")
    DIST.mkdir(exist_ok=True)
    temporary = DIST / "s6e11_gpt2_smoke.building.zip"
    _archive_bytes(temporary)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    target = DIST / f"s6e11_gpt2_smoke-{digest[:12]}.zip"
    temporary.replace(target)
    (DIST / f"{target.name}.sha256").write_text(f"{digest}  {target.name}\n")
    manifest = {
        "schema_version": 1,
        "trainer_code_version": digest[:12],
        "training_image": args.image,
        "dataset_manifest_uri": "s3://zipline-artifacts-crucible/gpt2-s6e11/manifests/dataset-802675cfd652bea99179b2f47402f906d581969773e3f57e6defca4689fc32ea.json",
        "recipe": json.loads((ROOT / "presets/pilot_parity.json").read_text()),
    }
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    (ROOT / "manifests/trainer.json").write_bytes(raw)
    artifacts = {
        "trainer_code_version": digest[:12],
        "archive_sha256": digest,
        "training_image": args.image,
        "trainer_manifest_sha256": manifest_hash,
        "trainer_manifest_uri": f"s3://zipline-artifacts-crucible/gpt2-s6e11/manifests/trainer-{manifest_hash}.json",
    }
    (ROOT / "manifests/artifacts.json").write_text(
        json.dumps(artifacts, sort_keys=True, indent=2) + "\n"
    )
    print(target)
    print(digest)


if __name__ == "__main__":
    main()
