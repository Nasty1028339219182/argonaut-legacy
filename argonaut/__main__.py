"""python -m argonaut"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


if "--selftest" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _crash_log() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent / "argonaut.log"


def _write_crash() -> None:
    path = _crash_log()
    if path is None:
        return
    try:
        path.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass


def run() -> None:
    try:
        from argonaut.ide.app import main

        main()
    except Exception:
        _write_crash()
        raise


if __name__ == "__main__":
    run()
