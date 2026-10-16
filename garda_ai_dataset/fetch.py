"""Download the original IBM files from Kaggle, one file at a time (spec 7).

Credentials are read from kaggle.json and only ever placed in the Authorization header.
They are never logged, written, or included in error messages.
"""

import base64
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from garda_ai_dataset.errors import FetchError, RawInputError
from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.paths import DatasetPaths

KAGGLE_DATASET = "ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/{dataset}/{file}"
ZIP_MAGIC = b"PK\x03\x04"
Opener = Callable[[urllib.request.Request], Any]  # urlopen-compatible context manager


def _urlopen(request: urllib.request.Request) -> Any:
    return urllib.request.urlopen(request, timeout=600)


def _authorization(kaggle_json: Path) -> str:
    try:
        data = json.loads(kaggle_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FetchError(
            f"Kaggle credentials not found at {kaggle_json} (set GARDA_KAGGLE_JSON or pass "
            "--kaggle-json)"
        ) from None
    except json.JSONDecodeError:
        raise FetchError(f"{kaggle_json} is not valid JSON") from None
    user = data.get("username") if isinstance(data, dict) else None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(user, str) or not isinstance(key, str) or not user or not key:
        raise FetchError(f"{kaggle_json} must contain non-empty 'username' and 'key'")
    return "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode("ascii")


def read_sums(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[name.strip()] = digest
    return sums


def write_sums(path: Path, sums: dict[str, str]) -> None:
    path.write_text("".join(f"{sums[n]}  {n}\n" for n in sorted(sums)), encoding="utf-8")


def _download(target: Path, authorization: str, opener: Opener) -> None:
    url = DOWNLOAD_URL.format(dataset=KAGGLE_DATASET, file=target.name)
    request = urllib.request.Request(
        url, headers={"Authorization": authorization, "User-Agent": "garda-ai-dataset"}
    )
    part = target.with_name(target.name + ".part")
    try:
        with opener(request) as response, part.open("wb") as fh:
            shutil.copyfileobj(response, fh, 1 << 20)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise FetchError(f"Kaggle returned HTTP {exc.code} for {target.name}") from None
    except urllib.error.URLError as exc:
        part.unlink(missing_ok=True)
        raise FetchError(f"could not reach Kaggle for {target.name}: {exc.reason}") from None
    with part.open("rb") as fh:
        is_zip = fh.read(4) == ZIP_MAGIC
    if not is_zip:
        part.replace(target)
        return
    with zipfile.ZipFile(part) as archive:
        member = next((n for n in archive.namelist() if Path(n).name == target.name), None)
        if member is None:
            part.unlink()
            raise FetchError(f"the zip Kaggle returned has no {target.name}")
        with archive.open(member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    part.unlink()


def run_fetch(
    paths: DatasetPaths, kaggle_json: Path, *, opener: Opener | None = None
) -> dict[str, str]:
    """Ensure the three raw files exist, and record or verify their sha256 in SHA256SUMS."""
    paths.raw_dir.mkdir(parents=True, exist_ok=True)
    sums = read_sums(paths.sha256sums)
    authorization: str | None = None
    for target in (paths.raw_trans, paths.raw_accounts, paths.raw_patterns):
        if target.exists():
            actual = sha256_file(target)
            recorded = sums.get(target.name)
            if recorded is not None and recorded != actual:
                raise RawInputError(
                    f"{target} does not match its recorded sha256 in {paths.sha256sums.name}; "
                    "delete it and re-run fetch"
                )
            sums[target.name] = actual
            continue
        if authorization is None:
            authorization = _authorization(kaggle_json)
        _download(target, authorization, opener or _urlopen)
        sums[target.name] = sha256_file(target)
    write_sums(paths.sha256sums, sums)
    return sums
