"""Cartridge: source, pixels, map, sound. Saved as JSON."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii")) if text else b""


@dataclass
class Cart:
    name: str = "untitled"
    code: str = ""
    palette: list = field(default_factory=list)  # (r,g,b) 0..31, up to 511
    gfx: bytearray = field(default_factory=lambda: bytearray(128 * 128))
    gfx_w: int = 128
    gfx_h: int = 128
    map_w: int = 128
    map_h: int = 32
    map_cells: list = field(default_factory=lambda: [0] * (128 * 32))
    instruments: list = field(default_factory=list)
    pattern: list = field(default_factory=list)
    sfx: list = field(default_factory=list)
    bpm: int = 112

    def to_json(self) -> str:
        payload = {
            "magic": "ALCART1",
            "name": self.name,
            "code": self.code,
            "palette": [list(c) for c in self.palette],
            "gfx": {"w": self.gfx_w, "h": self.gfx_h, "data": _b64(bytes(self.gfx))},
            "map": {
                "w": self.map_w,
                "h": self.map_h,
                "data": _b64(b"".join(int(c & 0xFFFF).to_bytes(2, "little") for c in self.map_cells)),
            },
            "instruments": self.instruments,
            "pattern": self.pattern,
            "sfx": self.sfx,
            "bpm": self.bpm,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Cart":
        raw = json.loads(text)
        if raw.get("magic") != "ALCART1":
            raise ValueError("это не картридж Argonaut Legacy")
        gfx = raw["gfx"]
        mp = raw["map"]
        cells_b = _unb64(mp["data"])
        cells = [int.from_bytes(cells_b[i : i + 2], "little") for i in range(0, len(cells_b), 2)]
        cart = cls(
            name=raw.get("name") or "untitled",
            code=raw.get("code") or "",
            palette=[tuple(c) for c in raw.get("palette") or []],
            gfx=bytearray(_unb64(gfx["data"])),
            gfx_w=int(gfx["w"]),
            gfx_h=int(gfx["h"]),
            map_w=int(mp["w"]),
            map_h=int(mp["h"]),
            map_cells=cells,
            instruments=raw.get("instruments") or [],
            pattern=raw.get("pattern") or [],
            sfx=raw.get("sfx") or [],
            bpm=int(raw.get("bpm") or 112),
        )
        return cart


def blank_sound():
    instruments = [
        {"wave": "square", "volume": 150},
        {"wave": "triangle", "volume": 130},
        {"wave": "sine", "volume": 80},
        {"wave": "saw", "volume": 70},
        {"wave": "square", "volume": 60},
        {"wave": "triangle", "volume": 60},
        {"wave": "sine", "volume": 40},
        {"wave": "noise", "volume": 90},
    ]
    row = [""] * 8
    pattern = [row[:] for _ in range(32)]
    sfx = [["C6", "E6", "G6"]] + [[] for _ in range(7)]
    return instruments, pattern, sfx
