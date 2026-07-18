#!/usr/bin/env python3
"""Download the repository's canonical backtesting data.

The backtests deliberately do not silently fall back to a developer's local
Google Drive.  This helper downloads the parquet files from the public GitHub
``master`` tree into ``backtesting_data/`` and verifies GitHub's blob SHA-1.
Existing, verified files are left untouched unless ``--force`` is supplied.

Examples
--------
    python scripts/download_backtesting_data.py
    python scripts/download_backtesting_data.py --force
    python scripts/download_backtesting_data.py --verify-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_API = "https://api.github.com/repos/kbsingh1399/coinglass-trading/contents/backtesting_data"
RAW_BASE = "https://raw.githubusercontent.com/kbsingh1399/coinglass-trading/master/backtesting_data"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "backtesting_data"


def github_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    h = hashlib.sha1()
    h.update(f"blob {size}\0".encode())
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_manifest() -> list[dict]:
    request = urllib.request.Request(
        REPO_API + "?ref=master",
        headers={"User-Agent": "coinglass-trading-backtest/1.0", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    files = [x for x in payload if x.get("type") == "file" and x.get("name", "").endswith(".parquet")]
    if not files:
        raise RuntimeError("GitHub returned no parquet files in backtesting_data")
    return sorted(files, key=lambda x: x["name"])


def download_one(item: dict, force: bool) -> str:
    name = item["name"]
    target = DEST / name
    expected = item.get("sha", "")
    if target.exists() and not force:
        actual = github_blob_sha1(target)
        if expected and actual == expected:
            return f"verified {name}"
        if expected:
            print(f"checksum mismatch; replacing {name}", file=sys.stderr)
    DEST.mkdir(parents=True, exist_ok=True)
    url = item.get("download_url") or f"{RAW_BASE}/{name}"
    tmp = target.with_suffix(target.suffix + ".download")
    request = urllib.request.Request(url, headers={"User-Agent": "coinglass-trading-backtest/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, tmp.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    if expected and github_blob_sha1(tmp) != expected:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"checksum verification failed for {name}")
    os.replace(tmp, target)
    return f"downloaded {name} ({target.stat().st_size / 1024 / 1024:.1f} MiB)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="redownload even when the local blob is verified")
    parser.add_argument("--verify-only", action="store_true", help="do not download; verify local files against GitHub")
    args = parser.parse_args()
    try:
        manifest = remote_manifest()
        print(f"GitHub master: {len(manifest)} parquet files")
        missing_or_bad = 0
        for item in manifest:
            target = DEST / item["name"]
            ok = target.exists() and (not item.get("sha") or github_blob_sha1(target) == item["sha"])
            if args.verify_only:
                print(f"{'OK      ' if ok else 'MISSING '}{item['name']}")
                missing_or_bad += not ok
            else:
                print(download_one(item, args.force), flush=True)
        if args.verify_only and missing_or_bad:
            print(f"{missing_or_bad} local files are missing or changed", file=sys.stderr)
            return 1
        print(f"Data ready at {DEST}")
        return 0
    except Exception as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
