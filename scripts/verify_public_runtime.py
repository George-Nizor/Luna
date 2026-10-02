"""Check a reviewed public runtime before it is copied into an installer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def verify(root: Path, plan_path: Path) -> None:
    root = root.resolve(strict=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    if {p["name"].lower().replace("_", "-"): p["version"] for p in manifest["packages"]} != {k.lower().replace("_", "-"): v for k, v in plan["packages"].items()}:
        raise ValueError("Runtime inventory differs from the reviewed package plan")
    for package in manifest["packages"]:
        notice = package.get("noticeFile")
        if not notice or not (root / notice).is_file():
            raise ValueError(f"Missing licence: {package['name']}")
    recorded = set()
    for line in (root / "runtime-files.sha256").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        file = (root / relative).resolve(strict=True)
        if not file.is_relative_to(root) or file.is_symlink():
            raise ValueError("Invalid runtime inventory path")
        with file.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != digest:
            raise ValueError(f"Runtime checksum mismatch: {relative}")
        recorded.add(relative)
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != "runtime-files.sha256" and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}}
    if actual != recorded:
        raise ValueError("Runtime contains unrecorded or missing files")
    print(f"Verified {len(manifest['packages'])} packages and {len(recorded)} runtime files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--plan", type=Path, default=Path(__file__).resolve().parents[1] / "packaging/runtime-packages.json")
    args = parser.parse_args()
    verify(args.root, args.plan)
