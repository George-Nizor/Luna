"""Rebuild the pure-Python wheels Luna ships for packages with no Python 3.12 wheel on PyPI.

The wheels in packaging/runtime/wheels are built from the PyPI source archives below, each checked
against its SHA-256 first. fairseq is built with READTHEDOCS set, which is fairseq's own switch for a
build without native extensions: Luna only needs the HuBERT feature extractor RVC loads, and the 0.4.1
runtime used the same extension-free build. The wheels are committed, and uv.lock pins their hashes,
so this only runs when one of them changes:

    python scripts/build_runtime_wheels.py --uv <path to uv>
    uv lock --project packaging/runtime
    python scripts/runtime_lock.py
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / "packaging" / "runtime" / "wheels"

SOURCES = [
    {
        "name": "fairseq",
        "url": "https://files.pythonhosted.org/packages/30/36/db42846570f479ac859be3b48d8b47f2ae9b0b9c77487a512f2f2ecbcb6b/fairseq-0.12.2.tar.gz",
        "sha256": "34f1b18426bf3844714534162f065ab733e049597476daa35fffb4d06a92b524",
        "env": {"READTHEDOCS": "1"},
    },
    {
        "name": "antlr4-python3-runtime",
        "url": "https://files.pythonhosted.org/packages/56/02/789a0bddf9c9b31b14c3e79ec22b9656185a803dc31c15f006f9855ece0d/antlr4-python3-runtime-4.8.tar.gz",
        "sha256": "15793f5d0512a372b4e7d2284058ad32ce7dd27126b105fb0b2245130445db33",
        "env": {},
    },
    {
        "name": "sox",
        "url": "https://files.pythonhosted.org/packages/3d/a2/d8e0d8fd7abf509ead4a2cb0fb24e5758b5330166bf9223d5cb9f98a7e8d/sox-1.5.0.tar.gz",
        "sha256": "12c7be5bb1f548d891fe11e82c08cf5f1a1d74e225298f60082e5aeb2469ada0",
        "env": {},
    },
]


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build(uv: str) -> None:
    WHEELS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for source in SOURCES:
            archive = work / source["url"].rsplit("/", 1)[1]
            urllib.request.urlretrieve(source["url"], archive)
            if sha256(archive) != source["sha256"]:
                raise SystemExit(f"{archive.name} does not match its pinned SHA-256")
            env = {**os.environ, "SOURCE_DATE_EPOCH": "1759708800", **source["env"]}
            output = work / f"out-{source['name']}"
            subprocess.run([uv, "build", "--wheel", "--python", "3.12", "-o", str(output), str(archive)], check=True, env=env)
            for wheel in output.glob("*.whl"):
                if not wheel.name.endswith("-py3-none-any.whl"):
                    raise SystemExit(f"{wheel.name} is not a pure-Python wheel")
                shutil.copy2(wheel, WHEELS / wheel.name)
                print(f"{wheel.name}  {sha256(WHEELS / wheel.name)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uv", default="uv")
    build(parser.parse_args().uv)
