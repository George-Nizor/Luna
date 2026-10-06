"""Turn packaging/runtime/uv.lock into the download plan Luna's first-run setup follows.

uv.lock is universal: it records every wheel each package publishes. Luna installs on one platform,
Windows x64 with CPython 3.12, so this picks the one wheel per package that platform installs and
writes packaging/runtime/runtime-lock.json: file name, URL, SHA-256 and byte size of each, the
CPython build, the bundled uv version and the lock hash that names the environment
(%LOCALAPPDATA%\\Luna\\runtime\\<lock hash>). Electron reads only this file; it never parses TOML.

    python scripts/runtime_lock.py           # rewrite runtime-lock.json (asks PyTorch's index for sizes)
    python scripts/runtime_lock.py --check   # fail if runtime-lock.json is stale (offline)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
import urllib.request
from pathlib import Path

from packaging.markers import Marker
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "packaging" / "runtime"
LOCK = RUNTIME / "uv.lock"
OUTPUT = RUNTIME / "runtime-lock.json"
PATCHES = RUNTIME / "apply_patches.py"

PYTHON_VERSION = "3.12.15"
UV_VERSION = "0.12.23"
ENVIRONMENT = {
    "implementation_name": "cpython",
    "implementation_version": PYTHON_VERSION,
    "os_name": "nt",
    "platform_machine": "AMD64",
    "platform_python_implementation": "CPython",
    "platform_release": "10",
    "platform_system": "Windows",
    "platform_version": "10.0",
    "python_full_version": PYTHON_VERSION,
    "python_version": "3.12",
    "sys_platform": "win32",
    "extra": "",
}
SUPPORTED_TAGS = list(cpython_tags((3, 12), abis=["cp312", "abi3", "none"], platforms=["win_amd64"]))
SUPPORTED_TAGS += list(compatible_tags((3, 12), "cp312", platforms=["win_amd64"]))
TAG_RANK = {tag: index for index, tag in enumerate(SUPPORTED_TAGS)}


def applies(marker: str | None) -> bool:
    return marker is None or Marker(marker).evaluate(ENVIRONMENT)


def installed_packages(lock: dict) -> list[dict]:
    """Walk the lock from the project root, following only dependencies that apply on the target."""
    packages = {canonicalize_name(p["name"]): p for p in lock["package"]}
    root = next(p for p in lock["package"] if "virtual" in p["source"])
    seen: dict[str, dict] = {}
    pending = [root]
    while pending:
        package = pending.pop()
        groups = [package.get("dependencies", [])]
        for dependency_list in groups:
            for dependency in dependency_list:
                if not applies(dependency.get("marker")):
                    continue
                name = canonicalize_name(dependency["name"])
                for extra in dependency.get("extra", []):
                    groups.append(packages[name].get("optional-dependencies", {}).get(extra, []))
                if name not in seen:
                    seen[name] = packages[name]
                    pending.append(packages[name])
    return [seen[name] for name in sorted(seen)]


def best_wheel(package: dict) -> dict:
    candidates = []
    for wheel in package.get("wheels", []):
        filename = wheel.get("filename") or wheel["url"].rsplit("/", 1)[1].replace("%2B", "+")
        _, _, _, tags = parse_wheel_filename(filename)
        ranks = [TAG_RANK[tag] for tag in tags if tag in TAG_RANK]
        if ranks:
            candidates.append((min(ranks), filename, wheel))
    if not candidates:
        raise SystemExit(f"{package['name']} {package['version']} has no wheel for CPython 3.12 on Windows x64; "
                         "build one with scripts/build_runtime_wheels.py")
    _, filename, wheel = min(candidates, key=lambda item: item[0])
    return {"file": filename, **wheel}


def remote_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "luna-runtime-lock"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"])


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build_plan(lock: dict, known_sizes: dict[str, int] | None = None, fetch_size=remote_size) -> dict:
    known_sizes = known_sizes or {}
    entries = []
    for package in installed_packages(lock):
        wheel = best_wheel(package)
        algorithm, digest = wheel["hash"].split(":", 1)
        if algorithm != "sha256":
            raise SystemExit(f"{package['name']} is not pinned by SHA-256")
        entry = {"name": canonicalize_name(package["name"]), "version": package["version"], "file": wheel["file"], "sha256": digest}
        if "path" in package["source"]:
            bundled = RUNTIME / package["source"]["path"]
            if sha256_file(bundled) != digest:
                raise SystemExit(f"{bundled} does not match uv.lock")
            entry.update(bundled=f"wheels/{bundled.name}", size=bundled.stat().st_size)
        else:
            size = wheel.get("size") or known_sizes.get(wheel["file"]) or fetch_size(wheel["url"])
            entry.update(url=wheel["url"], size=int(size))
        entries.append(entry)
    identity = {
        "python": PYTHON_VERSION,
        "packages": [[e["name"], e["version"], e["file"], e["sha256"]] for e in entries],
        "patches": sha256_file(PATCHES),
    }
    lock_hash = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return {
        "schemaVersion": 1,
        "lockHash": lock_hash,
        "platform": "windows-x64",
        "python": PYTHON_VERSION,
        "uv": UV_VERSION,
        "downloadBytes": sum(e["size"] for e in entries if "url" in e),
        "bundledBytes": sum(e["size"] for e in entries if "bundled" in e),
        "packages": entries,
    }


def render(plan: dict) -> str:
    return json.dumps(plan, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if runtime-lock.json does not match uv.lock")
    options = parser.parse_args()
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"packages": []}
    known = {p["file"]: p["size"] for p in previous["packages"]}

    def offline(url: str) -> int:
        raise SystemExit(f"runtime-lock.json is stale: no recorded size for {url}")

    plan = build_plan(lock, known, offline if options.check else remote_size)
    if options.check:
        if OUTPUT.read_text(encoding="utf-8") != render(plan):
            print("runtime-lock.json is stale; run scripts/runtime_lock.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(render(plan), encoding="utf-8")
    print(f"{len(plan['packages'])} wheels, {plan['downloadBytes'] / 1e9:.2f} GB to download, lock {plan['lockHash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
