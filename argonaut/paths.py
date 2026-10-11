"""Where the console keeps fonts and cartridges, source tree or frozen exe."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Folder the user can copy. Next to the exe when frozen, else the repo root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundle_dir() -> Path:
    """Read-only files packed into the build."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def font_file() -> Path:
    packaged = Path(__file__).resolve().parent / "fonts" / "DejaVuSansMono.ttf"
    bundled = bundle_dir() / "fonts" / "DejaVuSansMono.ttf"
    if bundled.is_file():
        return bundled
    return packaged


def cart_dir() -> Path:
    """Writable cartridges. A portable copy keeps this folder beside the exe."""
    folder = install_dir() / "carts"
    folder.mkdir(exist_ok=True)
    bundled = bundle_dir() / "carts"
    if bundled.is_dir() and bundled.resolve() != folder.resolve():
        for src in bundled.glob("*.alc"):
            dest = folder / src.name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())
    return folder
