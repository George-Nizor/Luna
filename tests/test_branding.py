from __future__ import annotations

import json
import tomllib
from pathlib import Path

from app import __version__
from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_luna_identity_is_consistent() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    product = json.loads((ROOT / "instrumenta" / "product.json").read_text(encoding="utf-8"))
    electron = (ROOT / "electron-builder.config.cjs").read_text(encoding="utf-8")

    assert package["name"] == "luna"
    assert package["productName"] == "Luna"
    assert package["version"] == __version__ == product["version"] == "0.3.0"
    assert Settings().app_name == "Luna"
    assert product["id"] == "luna"
    assert product["adapter"]["type"] == "installed-desktop"
    assert "com.instrumenta.luna" in electron
    assert "Luna Voice Studio" not in electron
    template = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "luna-brand-mark" in template
    assert "/static/luna-icon.png" in template


def test_unlicensed_reference_audio_is_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "assets/egirl-source-reference.wav" in ignored
def test_python_package_discovery_is_explicit() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["setuptools"]["packages"]["find"]["include"] == ["app", "app.*"]
    assert project["tool"]["setuptools"]["package-data"]["app"] == ["static/*", "templates/*"]
