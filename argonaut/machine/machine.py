"""One Argonaut: CPU, PPU, APU and a frame of guest time."""

from __future__ import annotations

from argonaut.asm.assembler import assemble
from argonaut.hw import (
    PALETTE_SLOTS,
    ROM_BASE,
    STR_MAGIC,
    cycles_for_frame,
    s32,
)
from argonaut.machine.apu import APU
from argonaut.machine.cpu import CPU
from argonaut.machine.memory import Memory
from argonaut.machine.ppu import PPU
from argonaut.tpython.compiler import compile_source
from argonaut.tpython.runtime import runtime_source


class Machine:
    def __init__(self) -> None:
        self.mem = Memory()
        self.cpu = CPU(self.mem)
        self.ppu = PPU(self.mem)
        self.apu = APU()
        self.overrun = 0
        self.frame_index = 0
        self.prev_pad = 0
        self.late = 0
        self.log_lines: list[str] = []
        self.asm_text = ""
        self.entry = ROM_BASE

    def load(self, cart) -> None:
        user = compile_source(cart.code)
        self.asm_text = runtime_source() + "\n" + user
        prog = assemble(self.asm_text)
        self.mem.reset()
        self.mem.cpu = self.cpu
        self.mem.ppu = self.ppu
        for i, rgb in enumerate(cart.palette[:PALETTE_SLOTS]):
            r, g, b = rgb
            self.mem.pal[i] = ((r & 31) << 10) | ((g & 31) << 5) | (b & 31)
        if len(cart.palette) > PALETTE_SLOTS:
            self.mem.pal_clip += len(cart.palette) - PALETTE_SLOTS
        image = bytearray(prog.image)
        gfx = bytes(cart.gfx)
        cells = bytearray()
        for cell in cart.map_cells:
            cells += int(cell & 0xFFFF).to_bytes(2, "little")
        gfx_off = _align(len(image), 256)
        map_off = _align(gfx_off + len(gfx), 256)
        blob = bytearray(map_off + len(cells))
        blob[: len(image)] = image
        blob[gfx_off : gfx_off + len(gfx)] = gfx
        blob[map_off : map_off + len(cells)] = cells
        self.mem.load_rom_image(bytes(blob))
        self.ppu.gfx_addr = ROM_BASE + gfx_off
        self.ppu.gfx_w = cart.gfx_w
        self.ppu.gfx_h = cart.gfx_h
        self.ppu.map_addr = ROM_BASE + map_off
        self.ppu.map_w = cart.map_w
        self.ppu.map_h = cart.map_h
        self.ppu.begin_frame()
        self.apu.load_waves(self.mem.sram, cart.instruments)
        self.apu.pattern = cart.pattern
        self.apu.bpm = cart.bpm
        self.apu.sfx_bank = cart.sfx
        self.apu.playing = False
        self.apu.sfx_notes = []
        for ch in self.apu.channels:
            ch.on = False
        self.cpu.reset(prog.symbols["_start"])
        self.entry = prog.symbols["_start"]
        self.overrun = 0
        self.frame_index = 0
        self.prev_pad = 0
        self.late = 0
        self.log_lines.clear()

    def frame(self, pad: int = 0) -> None:
        self.ppu.begin_frame()
        pad &= 0xFF
        self.mem.pad = pad
        self.mem.edge = pad & ~self.prev_pad
        self.prev_pad = pad
        self.mem.frame = self.frame_index & 0xFFFFFFFF
        nominal = cycles_for_frame(self.frame_index)
        budget = nominal - self.overrun
        if budget < 1:
            self.overrun = -budget if budget < 0 else 0
            self.late = 1
            self.mem.late = 1
            self.frame_index += 1
            self._after_cpu()
            return
        self.cpu.asleep = False
        if not self.cpu.halted:
            self.cpu.run(budget)
        self.overrun = max(0, self.cpu.cycles - budget)
        finished = self.cpu.asleep or self.cpu.halted
        self.late = 0 if finished and self.overrun == 0 else 1
        self.mem.late = self.late
        self.frame_index += 1
        self._after_cpu()

    def _after_cpu(self) -> None:
        for kind, value in self.mem.apu_events:
            self.apu.handle_event(kind, value)
        self.mem.apu_events.clear()
        self.apu.tick_frame()
        for value in self.mem.logs:
            self.log_lines.append(self._format_log(value))
            if len(self.log_lines) > 12:
                self.log_lines = self.log_lines[-12:]
        self.mem.logs.clear()

    def _format_log(self, value: int) -> str:
        if value >= 0x10000 and (value & 3) == 0 and self.mem.read32(value) == STR_MAGIC:
            length = self.mem.read32(value + 4) & 0xFFFF
            chars = bytes(self.mem.read8(value + 8 + i) for i in range(min(length, 80)))
            return chars.decode("utf-8", "replace")
        return str(s32(value))

    def read_pixel(self, x: int, y: int) -> int:
        return self.mem.fb_index(y * 320 + x) & 0x1FF


def _align(value: int, bound: int) -> int:
    return (value + bound - 1) & ~(bound - 1)
