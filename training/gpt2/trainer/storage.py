"""Small local/S3 I/O boundary; S3 uses the existing pod service account."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def read_bytes(uri):
    if uri.startswith("s3://"):
        import boto3

        u = urlparse(uri)
        return (
            boto3.client("s3")
            .get_object(Bucket=u.netloc, Key=u.path.lstrip("/"))["Body"]
            .read()
        )
    return Path(uri).read_bytes()


def download(uri, path, sha256):
    path = Path(path)
    if not path.exists() or fingerprint(path) != sha256:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".download")
        if uri.startswith("s3://"):
            import boto3

            u = urlparse(uri)
            boto3.client("s3").download_file(u.netloc, u.path.lstrip("/"), str(tmp))
        else:
            import shutil

            shutil.copyfile(uri, tmp)
        if fingerprint(tmp) != sha256:
            raise ValueError("Input SHA256 mismatch: " + uri)
        tmp.replace(path)
    return path


def upload(path, uri, immutable=False):
    path = Path(path)
    if uri.startswith("s3://"):
        import boto3

        u = urlparse(uri)
        client = boto3.client("s3")
        if immutable:
            with path.open("rb") as f:
                client.put_object(
                    Bucket=u.netloc, Key=u.path.lstrip("/"), Body=f, IfNoneMatch="*"
                )
        else:
            client.upload_file(str(path), u.netloc, u.path.lstrip("/"))
    else:
        target = Path(uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "xb" if immutable else "wb"
        with target.open(mode) as f:
            f.write(path.read_bytes())
