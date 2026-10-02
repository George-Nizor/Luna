"""Copy old bundled weights to persistent user storage before NSIS removes them."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def preserve(resources: Path, destination: Path) -> dict:
    resources = resources.resolve(strict=True)
    destination = destination.resolve()
    sources = [(resources / "model-data", destination),
               (resources / "python/Lib/site-packages/rvc_python/base_model", destination / "rvc-runtime/base_model")]
    copied = 0
    verified = 0
    for source, target in sources:
        if not source.is_dir():
            continue
        for item in sorted(source.rglob("*")):
            if item.is_symlink():
                raise ValueError(f"Cannot preserve a linked model asset: {item}")
            if not item.is_file():
                continue
            output = target / item.relative_to(source)
            if destination not in output.resolve().parents:
                raise ValueError("Model preservation target escaped its destination")
            expected = digest(item)
            if output.exists():
                if output.is_symlink() or output.stat().st_size != item.stat().st_size or digest(output) != expected:
                    raise ValueError(f"An existing preserved model differs: {output}")
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                temporary = output.with_name(output.name + ".luna-copy")
                if temporary.is_symlink():
                    raise ValueError("Model preservation temporary file cannot be a link")
                shutil.copyfile(item, temporary)
                if temporary.stat().st_size != item.stat().st_size or digest(temporary) != expected:
                    raise OSError(f"Model preservation verification failed: {item.name}")
                temporary.replace(output)
                copied += 1
            verified += 1
    result = {"source": str(resources), "copied_files": copied, "verified_files": verified}
    if verified:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "preserved.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(preserve(args.resources, args.destination)))
