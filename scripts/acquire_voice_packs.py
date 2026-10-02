"""Download only curated, revision-pinned packs, with progress and verification."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.model_catalog import PACKS, ModelCatalog  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("packs", nargs="+", choices=tuple(PACKS))
parser.add_argument("--data-directory", type=Path)
args = parser.parse_args()
settings = Settings.from_env(Path(__file__).resolve().parents[1])
if args.data_directory:
    settings.data_directory = args.data_directory.resolve()
settings.ensure_directories()
catalog = ModelCatalog(settings)
try:
    for pack_id in args.packs:
        result = catalog.start_download(pack_id)
        if result["status"] == "installed":
            print(f"{pack_id}: already installed", flush=True)
            continue
        while True:
            job = catalog.snapshot()["download"]
            print(f"{pack_id}: {job['status']} {job['downloaded_bytes'] / 10**9:.2f}/{job['total_bytes'] / 10**9:.2f} GB {job['filename']}", flush=True)
            if job["status"] in {"installed", "paused", "failed"}:
                if job["status"] != "installed":
                    raise RuntimeError(job["error"])
                break
            time.sleep(10)
finally:
    catalog.shutdown()
