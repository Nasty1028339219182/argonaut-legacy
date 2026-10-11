"""python -m argonaut"""

from __future__ import annotations

import os
import sys

if "--selftest" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from argonaut.ide.app import main


if __name__ == "__main__":
    main()
