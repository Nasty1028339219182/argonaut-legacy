"""Entry point PyInstaller freezes into ArgonautLegacy.exe."""

import argonaut.ide.app  # noqa: F401  — keep the package on the frozen graph
from argonaut.__main__ import run

if __name__ == "__main__":
    run()
