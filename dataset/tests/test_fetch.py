import base64
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from email.message import Message
from pathlib import Path

import pytest

import grafin_ai_dataset.fetch as fetch_mod
from grafin_ai_dataset.errors import FetchError, RawInputError
from grafin_ai_dataset.fetch import run_fetch
from grafin_ai_dataset.paths import dataset_paths

NAMES = ["HI-Small_Trans.csv", "HI-Small_accounts.csv", "HI-Small_Patterns.txt"]


def _creds(tmp_path: Path) -> Path:
    path = tmp_path / "kaggle.json"
    path.write_text(json.dumps({"username": "u", "key": "SECRETKEY"}))
    return path


def _file_name(request: urllib.request.Request) -> str:
    return request.full_url.rsplit("/", 1)[1]


def test_downloads_and_records_hashes(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    calls: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request) -> io.BytesIO:
        calls.append(request)
        return io.BytesIO(f"payload {_file_name(request)}".encode())

    sums = run_fetch(paths, _creds(tmp_path), opener=opener)
    assert [_file_name(r) for r in calls] == NAMES
    assert calls[0].full_url.startswith(
        "https://www.kaggle.com/api/v1/datasets/download/"
        "ealtman2019/ibm-transactions-for-anti-money-laundering-aml/"
    )
    assert calls[0].get_header("Authorization") == "Basic " + base64.b64encode(
        b"u:SECRETKEY").decode()
    assert paths.raw_trans.read_bytes() == b"payload HI-Small_Trans.csv"
    assert sums["HI-Small_Trans.csv"] == hashlib.sha256(b"payload HI-Small_Trans.csv").hexdigest()
    assert "HI-Small_Patterns.txt" in paths.sha256sums.read_text()


def test_existing_files_are_adopted_without_credentials(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    paths.raw_dir.mkdir(parents=True)
    for name in NAMES:
        (paths.raw_dir / name).write_text(name)

    def opener(request: urllib.request.Request) -> io.BytesIO:
        raise AssertionError("must not download")

    sums = run_fetch(paths, tmp_path / "absent.json", opener=opener)
    assert set(sums) == set(NAMES)


def test_hash_mismatch_raises(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    paths.raw_dir.mkdir(parents=True)
    for name in NAMES:
        (paths.raw_dir / name).write_text(name)
    run_fetch(paths, tmp_path / "absent.json")
    paths.raw_trans.write_text("tampered")
    with pytest.raises(RawInputError, match="sha256"):
        run_fetch(paths, tmp_path / "absent.json")


def test_zip_payload_is_extracted(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    def opener(request: urllib.request.Request) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(_file_name(request), f"zipped {_file_name(request)}")
        return io.BytesIO(buffer.getvalue())

    run_fetch(paths, _creds(tmp_path), opener=opener)
    assert paths.raw_accounts.read_text() == "zipped HI-Small_accounts.csv"
    assert not list(paths.raw_dir.glob("*.part"))


def test_http_error_never_leaks_the_key(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    def opener(request: urllib.request.Request) -> io.BytesIO:
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    with pytest.raises(FetchError) as exc:
        run_fetch(paths, _creds(tmp_path), opener=opener)
    assert "401" in str(exc.value)
    assert "SECRETKEY" not in str(exc.value)
    assert not list(paths.raw_dir.glob("*.part"))


def test_missing_credentials(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="credentials"):
        run_fetch(dataset_paths(tmp_path, "small"), tmp_path / "nope.json")


def test_incomplete_credentials(tmp_path: Path) -> None:
    path = tmp_path / "kaggle.json"
    path.write_text("{}")
    with pytest.raises(FetchError, match="username"):
        run_fetch(dataset_paths(tmp_path, "small"), path)


def test_credentials_not_forwarded_across_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import http.server
    import threading

    seen: dict[str, str | None] = {}

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen["authorization"] = self.headers.get("Authorization")
            body = b"redirected body"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    target_server = http.server.HTTPServer(("127.0.0.1", 0), Target)
    target_url = f"http://127.0.0.1:{target_server.server_port}/blob"

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    redirect_server = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (target_server, redirect_server)
    ]
    for thread in threads:
        thread.start()
    try:
        monkeypatch.setattr(
            fetch_mod, "DOWNLOAD_URL",
            f"http://127.0.0.1:{redirect_server.server_port}/{{dataset}}/{{file}}",
        )
        target = tmp_path / "HI-Small_Trans.csv"
        fetch_mod._download(target, "Basic c2VjcmV0", fetch_mod._urlopen)
    finally:
        for server in (target_server, redirect_server):
            server.shutdown()
            server.server_close()
    assert seen["authorization"] is None
    assert target.read_bytes() == b"redirected body"


def _leftovers(raw_dir: Path) -> list[Path]:
    return [p for p in raw_dir.iterdir() if p.suffix in {".part", ".unzip"}]


def test_corrupt_zip_member_is_a_fetch_error(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    def opener(request: urllib.request.Request) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:  # stored, so the payload is plain bytes
            zf.writestr(_file_name(request), "zipped payload that will be damaged")
        data = bytearray(buffer.getvalue())
        data[data.index(b"zipped") + 1] ^= 0xFF
        return io.BytesIO(bytes(data))

    with pytest.raises(FetchError, match="HI-Small_Trans.csv"):
        run_fetch(paths, _creds(tmp_path), opener=opener)
    assert not paths.raw_trans.exists()
    assert _leftovers(paths.raw_dir) == []


def test_connection_reset_mid_download_is_a_fetch_error(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    class Resetting:
        def __enter__(self) -> "Resetting":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            raise ConnectionResetError("peer reset")

    def opener(request: urllib.request.Request) -> Resetting:
        return Resetting()

    with pytest.raises(FetchError, match="ConnectionResetError"):
        run_fetch(paths, _creds(tmp_path), opener=opener)
    assert not paths.raw_trans.exists()
    assert _leftovers(paths.raw_dir) == []
