"""The public bucket that holds a copy of all raw files.

The sources are slow, have gaps and can change. The bucket gives each person the same raw files.
A person reads the bucket with no key. Only a person with a Google login that has
write access can add files. A file in the bucket is never changed.
"""

import base64
import hashlib
from pathlib import Path
from urllib.parse import quote

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession

from chispa import config

API = "https://storage.googleapis.com"
PREFIX = "raw/"  # The folder in the bucket that is a copy of the local raw folder.
WRITE_SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"


def list_objects() -> dict[str, dict]:
    """Return each raw file in the bucket: path below the raw folder -> size and md5."""
    objects, page = {}, None
    while True:
        answer = requests.get(
            f"{API}/storage/v1/b/{config.BUCKET}/o",
            params={
                "prefix": PREFIX,
                "pageToken": page,
                "fields": "items(name,size,md5Hash),nextPageToken",
            },
            timeout=60,
        )
        answer.raise_for_status()
        body = answer.json()
        for item in body.get("items", []):
            objects[item["name"].removeprefix(PREFIX)] = item
        page = body.get("nextPageToken")
        if not page:
            return objects


def pull(raw_dir: Path) -> int:
    """Download each bucket file that is absent from the local raw folder. Return the count."""
    absent = {name: item for name, item in list_objects().items() if not (raw_dir / name).exists()}
    for name, item in absent.items():
        _download(name, item, raw_dir / name)
    return len(absent)


def _download(name: str, item: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    digest = hashlib.md5()
    with requests.get(
        f"{API}/{config.BUCKET}/{quote(PREFIX + name)}", stream=True, timeout=300
    ) as answer:
        answer.raise_for_status()
        with part.open("wb") as file:
            for chunk in answer.iter_content(chunk_size=1 << 20):
                file.write(chunk)
                digest.update(chunk)
    # A large file can have no md5 in the bucket. Then we compare only the size.
    expected = item.get("md5Hash", base64.b64encode(digest.digest()).decode())
    if part.stat().st_size != int(item["size"]) or base64.b64decode(expected) != digest.digest():
        raise RuntimeError(f"The download of {name} is not the same as the bucket file.")
    part.rename(path)


def push(raw_dir: Path, folder: str) -> int:
    """Upload each local file of one source folder that is absent from the bucket.

    This needs a Google login with write access to the bucket. README.md gives the setup.
    """
    credentials, _ = google.auth.default(scopes=[WRITE_SCOPE])
    session = AuthorizedSession(credentials)
    present = list_objects()
    # A name that ends in `.part` is a download in progress. It is not a raw file yet.
    files = sorted((raw_dir / folder).rglob("*"))
    local = [path for path in files if path.is_file() and path.suffix != ".part"]
    absent = [path for path in local if path.relative_to(raw_dir).as_posix() not in present]
    for path in absent:
        name = PREFIX + path.relative_to(raw_dir).as_posix()
        with path.open("rb") as file:
            # `ifGenerationMatch=0` makes the upload fail if the file exists.
            # Raw files never change.
            answer = session.post(
                f"{API}/upload/storage/v1/b/{config.BUCKET}/o",
                params={"uploadType": "media", "name": name, "ifGenerationMatch": 0},
                data=file,
                timeout=1800,
            )
        if answer.status_code != 200:
            raise RuntimeError(f"Upload of {name} failed: HTTP {answer.status_code}.")
    return len(absent)
