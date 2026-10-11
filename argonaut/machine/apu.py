"""STRIBOG-8 — 8-channel wavetable mixer at 22.05 kHz, stereo, 16-bit.

Mixing runs on the host side of the chip. The guest CPU only writes triggers.
Sample bytes live in MÍMIR SRAM (the 128 KiB audio window).
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field

from argonaut.hw import AUDIO_BASE, s32

SAMPLE_RATE = 22050
WAVE_LEN = 256


def make_wave(kind: str) -> bytes:
    data = bytearray(WAVE_LEN)
    for i in range(WAVE_LEN):
        t = i / WAVE_LEN
        if kind == "square":
            v = 110 if i < 128 else -110
        elif kind == "triangle":
            tri = 1 - 4 * abs(((t + 0.25) % 1) - 0.5)
            v = int(tri * 110)
        elif kind == "saw":
            v = int((t * 2 - 1) * 100)
        elif kind == "sine":
            v = int(math.sin(t * math.tau) * 110)
        else:
            v = 0
        data[i] = (v + 128) & 255
    return bytes(data)


_NOTE_SEMI = {
    "C": -9,
    "C#": -8,
    "DB": -8,
    "D": -7,
    "D#": -6,
    "EB": -6,
    "E": -5,
    "F": -4,
    "F#": -3,
    "GB": -3,
    "G": -2,
    "G#": -1,
    "AB": -1,
    "A": 0,
    "A#": 1,
    "BB": 1,
    "B": 2,
}


def parse_note(text: str) -> float | None:
    """Return frequency in Hz, or None to hold, or 0.0 for note-off."""
    raw = text.strip().upper()
    if raw in ("", ".", "---", "…"):
        return None
    if raw in ("OFF", "===", "---"):
        return 0.0
    if raw == "OFF":
        return 0.0
    name = raw
    octave = 4
    if name[-1].isdigit():
        octave = int(name[-1])
        name = name[:-1]
    if name not in _NOTE_SEMI:
        return None
    semi = _NOTE_SEMI[name] + (octave - 4) * 12
    return 440.0 * (2.0 ** (semi / 12.0))


def step_for(freq: float) -> int:
    if freq <= 0:
        return 0
    return int(freq / SAMPLE_RATE * WAVE_LEN * 65536)


@dataclass
class Channel:
    on: bool = False
    noise: bool = False
    base: int = AUDIO_BASE
    pos: int = 0
    step: int = 0
    vol: int = 0
    lfsr: int = 0xACE1


@dataclass
class APU:
    channels: list[Channel] = field(default_factory=lambda: [Channel() for _ in range(8)])
    pattern: list[list[str]] = field(default_factory=list)
    instruments: list[dict] = field(default_factory=list)
    bpm: int = 112
    playing: bool = False
    row: int = 0
    accum: float = 0.0
    sfx_left: list[tuple[int, list[str]]] = field(default_factory=list)  # (index, notes) unused
    sfx_row_timer: int = 0
    sfx_notes: list[str] = field(default_factory=list)
    sfx_pos: int = 0
    sfx_bank: list[list[str]] = field(default_factory=list)

    def silence(self) -> None:
        for ch in self.channels:
            ch.on = False
        self.playing = False
        self.sfx_notes = []

    def load_waves(self, sram: bytearray, instruments: list[dict]) -> None:
        self.instruments = instruments
        for i, inst in enumerate(instruments[:8]):
            wave = make_wave(inst.get("wave", "square"))
            base = AUDIO_BASE + i * WAVE_LEN
            sram[base : base + WAVE_LEN] = wave
            self.channels[i].base = base
            self.channels[i].noise = inst.get("wave") == "noise"

    def note_on(self, channel: int, freq: float, volume: int, noise: bool, base: int) -> None:
        if not 0 <= channel < 8:
            return
        ch = self.channels[channel]
        if freq <= 0:
            ch.on = False
            return
        ch.on = True
        ch.noise = noise
        ch.base = base
        ch.pos = 0
        ch.step = step_for(freq)
        ch.vol = max(0, min(255, volume))
        ch.lfsr = 0xACE1 ^ (channel * 97)

    def handle_event(self, kind: str, value: int) -> None:
        value = s32(value)
        if kind == "music":
            if value < 0:
                self.playing = False
                for i in range(7):
                    self.channels[i].on = False
            else:
                self.playing = True
                self.row = 0
                self.accum = 0.0
                self._apply_row()
        elif kind == "sfx":
            if 0 <= value < len(self.sfx_bank):
                self.sfx_notes = list(self.sfx_bank[value])
                self.sfx_pos = 0
                self.sfx_row_timer = 0
                self._sfx_step()

    def _inst(self, index: int) -> tuple[bool, int, int]:
        inst = self.instruments[index] if index < len(self.instruments) else {"wave": "square", "volume": 160}
        return inst.get("wave") == "noise", AUDIO_BASE + (index % 8) * WAVE_LEN, int(inst.get("volume", 160))

    def _apply_row(self) -> None:
        if not self.pattern:
            return
        row = self.pattern[self.row % len(self.pattern)]
        for ch in range(min(7, len(row))):
            freq = parse_note(row[ch])
            if freq is None:
                continue
            noise, base, vol = self._inst(ch)
            self.note_on(ch, freq, vol, noise, base)

    def _sfx_step(self) -> None:
        if self.sfx_pos >= len(self.sfx_notes):
            self.channels[7].on = False
            self.sfx_notes = []
            return
        freq = parse_note(self.sfx_notes[self.sfx_pos])
        noise, base, vol = self._inst(7)
        if freq is None:
            freq = 880.0
        self.note_on(7, freq, min(255, vol + 30), noise, base)
        self.sfx_pos += 1

    def tick_frame(self) -> None:
        if self.sfx_notes:
            self.sfx_row_timer += 1
            if self.sfx_row_timer >= 4:
                self.sfx_row_timer = 0
                self._sfx_step()
        if not self.playing or not self.pattern or self.bpm <= 0:
            return
        # 4 rows per beat → frames per row = 900 / bpm
        self.accum += self.bpm / 900.0
        while self.accum >= 1.0:
            self.accum -= 1.0
            self.row = (self.row + 1) % len(self.pattern)
            self._apply_row()

    def render(self, frames: int, sram: bytearray) -> bytes:
        n = max(1, int(SAMPLE_RATE / 60 * frames))
        out = array("h", [0] * (n * 2))
        for ch in self.channels:
            if not ch.on or ch.vol <= 0:
                continue
            pos = ch.pos
            step = ch.step
            vol = ch.vol
            lfsr = ch.lfsr
            base = ch.base
            if ch.noise:
                for i in range(n):
                    bit = ((lfsr >> 0) ^ (lfsr >> 2) ^ (lfsr >> 3) ^ (lfsr >> 5)) & 1
                    lfsr = ((lfsr >> 1) | (bit << 15)) & 0xFFFF
                    sample = 90 if bit else -90
                    s = sample * vol // 160
                    out[i * 2] += s
                    out[i * 2 + 1] += s
                ch.lfsr = lfsr
                continue
            for i in range(n):
                idx = (pos >> 16) & 255
                sample = sram[base + idx] - 128
                pos = (pos + step) & 0xFFFFFFFF
                s = sample * vol // 140
                out[i * 2] += s
                out[i * 2 + 1] += s
            ch.pos = pos
        for i in range(len(out)):
            v = out[i]
            if v > 32767:
                v = 32767
            elif v < -32768:
                v = -32768
            out[i] = v
        return out.tobytes()

    def levels(self) -> list[int]:
        return [ch.vol if ch.on else 0 for ch in self.channels]
