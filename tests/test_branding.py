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
    assert package["version"] == __version__ == product["version"] == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert Settings().app_name == "Luna"
    assert product["id"] == "luna"
    assert product["adapter"]["type"] == "installed-desktop"
    assert "com.instrumenta.luna" in electron
    assert "Luna Voice Studio" not in electron
    template = (ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "luna-brand-mark" in template
    assert "/static/brand/luna.svg" in template
    assert "/static/brand/fonts/fonts.css" in template


def test_brand_v2_assets_are_vendored() -> None:
    static = ROOT / "app" / "static" / "brand"
    for name in ("luna.svg", "luna-24.svg", "luna-16.svg", "luna-32.png", "instrumenta-icons.js",
                 "instrumenta-icons.css", "luna-icons.js", "luna-icons.css"):
        assert (static / name).is_file(), name
    fonts = static / "fonts"
    assert (fonts / "fonts.css").is_file()
    for family in ("commissioner", "fraunces", "splinesansmono"):
        assert (fonts / f"OFL-{family}.txt").is_file()
    assert len(list(fonts.glob("*.woff2"))) == 6
    # The Windows executable, installer and window icons keep their paths; only the art changed.
    ico = (ROOT / "assets" / "luna-icon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00" and int.from_bytes(ico[4:6], "little") >= 6
    assert (ROOT / "assets" / "luna-icon.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    product = json.loads((ROOT / "instrumenta" / "product.json").read_text(encoding="utf-8"))
    assert (ROOT / product["assets"]["mark"]).is_file()


def test_unlicensed_reference_audio_is_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "assets/egirl-source-reference.wav" in ignored
def test_python_package_discovery_is_explicit() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["setuptools"]["packages"]["find"]["include"] == ["app", "app.*"]
    assert project["tool"]["setuptools"]["package-data"]["app"] == ["static/*", "static/brand/*", "static/brand/fonts/*", "templates/*", "voice_packs.json"]
