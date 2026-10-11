"""MÍMIR SRAM, cartridge ROM (XIP), and MMIO for the other chips."""

from __future__ import annotations

from argonaut.hw import (
    APU_BASE,
    APU_MUSIC,
    APU_SFX,
    AUDIO_BASE,
    AUDIO_SIZE,
    FAULT_ALIGN,
    FAULT_ROM_WRITE,
    FB_BASE,
    FB_BYTES,
    PAD_BASE,
    PAL_BASE,
    PALETTE_SLOTS,
    PIXELS,
    PPU_BASE,
    ROM_BASE,
    ROM_SIZE,
    SRAM_SIZE,
    SYS_BASE,
    SYS_CYCLES,
    SYS_FAULT,
    SYS_FRAME,
    SYS_LATE,
    SYS_LOG,
    SYS_PALCLIP,
)


class Memory:
    def __init__(self) -> None:
        self.sram = bytearray(SRAM_SIZE)
        self.rom = bytearray(ROM_SIZE)
        self.rom_used = 0
        self.fb = bytearray(FB_BYTES)  # little-endian RGB555/index pairs, low 9 bits
        self.pal = [0] * PALETTE_SLOTS
        self.cpu = None
        self.ppu = None
        self.pad = 0
        self.edge = 0
        self.frame = 0
        self.late = 0
        self.fault = 0
        self.pal_clip = 0
        self.logs: list[int] = []
        self.apu_events: list[tuple[str, int]] = []
        self.exec_ok = True

    def reset(self) -> None:
        self.sram[:] = bytes(SRAM_SIZE)
        self.rom[:] = bytes(ROM_SIZE)
        self.rom_used = 0
        self.fb[:] = bytes(FB_BYTES)
        self.pal = [0] * PALETTE_SLOTS
        self.pad = 0
        self.edge = 0
        self.frame = 0
        self.late = 0
        self.fault = 0
        self.pal_clip = 0
        self.logs.clear()
        self.apu_events.clear()

    def _fault(self, code: int) -> None:
        if self.fault == 0:
            self.fault = code

    def read8(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        if addr < SRAM_SIZE:
            return self.sram[addr]
        if ROM_BASE <= addr < ROM_BASE + ROM_SIZE:
            return self.rom[addr - ROM_BASE]
        if FB_BASE <= addr < FB_BASE + FB_BYTES:
            return self.fb[addr - FB_BASE]
        if PAL_BASE <= addr < PAL_BASE + PALETTE_SLOTS * 2:
            off = addr - PAL_BASE
            slot = off // 2
            half = self.pal[slot]
            return (half >> (8 * (off & 1))) & 0xFF
        return 0

    def read16(self, addr: int) -> int:
        if addr & 1:
            self._fault(FAULT_ALIGN)
            return 0
        return self.read8(addr) | (self.read8(addr + 1) << 8)

    def read32(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        if addr == SYS_BASE + SYS_CYCLES:
            return self.cpu.cycles if self.cpu is not None else 0
        if addr == SYS_BASE + SYS_FRAME:
            return self.frame & 0xFFFFFFFF
        if addr == SYS_BASE + SYS_LATE:
            return self.late & 0xFFFFFFFF
        if addr == SYS_BASE + SYS_FAULT:
            return self.fault & 0xFFFFFFFF
        if addr == SYS_BASE + SYS_PALCLIP:
            return self.pal_clip & 0xFFFFFFFF
        if addr == PAD_BASE:
            return self.pad & 0xFFFFFFFF
        if addr == PAD_BASE + 4:
            return self.edge & 0xFFFFFFFF
        if PPU_BASE <= addr < PPU_BASE + 64 and self.ppu is not None:
            return self.ppu.read(addr - PPU_BASE)
        if addr & 3:
            self._fault(FAULT_ALIGN)
            return 0
        if addr + 3 < SRAM_SIZE:
            return int.from_bytes(self.sram[addr : addr + 4], "little")
        if ROM_BASE <= addr <= ROM_BASE + ROM_SIZE - 4:
            off = addr - ROM_BASE
            return int.from_bytes(self.rom[off : off + 4], "little")
        if FB_BASE <= addr <= FB_BASE + FB_BYTES - 4:
            off = addr - FB_BASE
            return int.from_bytes(self.fb[off : off + 4], "little")
        if PAL_BASE <= addr <= PAL_BASE + PALETTE_SLOTS * 2 - 4:
            return self.read16(addr) | (self.read16(addr + 2) << 16)
        return 0

    def read_exec(self, addr: int) -> int | None:
        addr &= 0xFFFFFFFF
        if addr & 3:
            self._fault(FAULT_ALIGN)
            return None
        if addr + 3 < SRAM_SIZE:
            return int.from_bytes(self.sram[addr : addr + 4], "little")
        if ROM_BASE <= addr <= ROM_BASE + ROM_SIZE - 4:
            off = addr - ROM_BASE
            return int.from_bytes(self.rom[off : off + 4], "little")
        self._fault(FAULT_FETCH)
        return None

    def write8(self, addr: int, value: int) -> None:
        addr &= 0xFFFFFFFF
        value &= 0xFF
        if addr < SRAM_SIZE:
            self.sram[addr] = value
            return
        if ROM_BASE <= addr < ROM_BASE + ROM_SIZE:
            self._fault(FAULT_ROM_WRITE)
            return
        if FB_BASE <= addr < FB_BASE + FB_BYTES:
            # Byte writes into the 16-bit pixel are allowed; the paired byte stays.
            self.fb[addr - FB_BASE] = value
            return
        if PAL_BASE <= addr < PAL_BASE + PALETTE_SLOTS * 2:
            off = addr - PAL_BASE
            slot = off // 2
            cur = self.pal[slot]
            if off & 1:
                cur = (cur & 0x00FF) | (value << 8)
            else:
                cur = (cur & 0xFF00) | value
            self.pal[slot] = cur & 0x7FFF
            return
        if PAL_BASE + PALETTE_SLOTS * 2 <= addr < PAL_BASE + 1024:
            self.pal_clip += 1

    def write16(self, addr: int, value: int) -> None:
        if addr & 1:
            self._fault(FAULT_ALIGN)
            return
        value &= 0xFFFF
        if FB_BASE <= addr < FB_BASE + FB_BYTES:
            self._write_pixel(addr, value)
            return
        if PAL_BASE <= addr < PAL_BASE + PALETTE_SLOTS * 2:
            slot = (addr - PAL_BASE) // 2
            self.pal[slot] = value & 0x7FFF
            return
        if PAL_BASE + PALETTE_SLOTS * 2 <= addr < PAL_BASE + 2048:
            self.pal_clip += 1
            return
        self.write8(addr, value & 0xFF)
        self.write8(addr + 1, (value >> 8) & 0xFF)

    def _write_pixel(self, addr: int, value: int) -> None:
        if self.ppu is not None and not self.ppu.take(1):
            return
        pix = (addr - FB_BASE) // 2
        idx = value & 0x1FF
        if idx > 510:
            idx = 0
            self.pal_clip += 1
        # store little-endian index in the halfword
        off = pix * 2
        self.fb[off] = idx & 0xFF
        self.fb[off + 1] = (idx >> 8) & 0xFF

    def fb_index(self, pix: int) -> int:
        off = pix * 2
        return self.fb[off] | (self.fb[off + 1] << 8)

    def set_fb_index(self, pix: int, idx: int, count: bool = True) -> bool:
        if count and self.ppu is not None and not self.ppu.take(1):
            return False
        if idx > 510:
            idx = 0
            self.pal_clip += 1
        off = pix * 2
        self.fb[off] = idx & 0xFF
        self.fb[off + 1] = (idx >> 8) & 0xFF
        return True

    def write32(self, addr: int, value: int) -> None:
        addr &= 0xFFFFFFFF
        value &= 0xFFFFFFFF
        if addr == SYS_BASE + SYS_LOG:
            self.logs.append(value)
            return
        if addr == SYS_BASE + SYS_FAULT:
            self.fault = value
            return
        if addr == SYS_BASE + SYS_PALCLIP:
            self.pal_clip = value
            return
        if PPU_BASE <= addr < PPU_BASE + 64 and self.ppu is not None:
            self.ppu.write(addr - PPU_BASE, value)
            return
        if addr == APU_BASE + APU_SFX:
            self.apu_events.append(("sfx", value))
            return
        if addr == APU_BASE + APU_MUSIC:
            self.apu_events.append(("music", value))
            return
        if addr & 3:
            self._fault(FAULT_ALIGN)
            return
        if addr + 3 < SRAM_SIZE:
            self.sram[addr : addr + 4] = value.to_bytes(4, "little")
            return
        if ROM_BASE <= addr < ROM_BASE + ROM_SIZE:
            self._fault(FAULT_ROM_WRITE)
            return
        if FB_BASE <= addr <= FB_BASE + FB_BYTES - 4:
            self.write16(addr, value & 0xFFFF)
            self.write16(addr + 2, (value >> 16) & 0xFFFF)
            return
        if PAL_BASE <= addr <= PAL_BASE + PALETTE_SLOTS * 2 - 4:
            self.write16(addr, value & 0xFFFF)
            self.write16(addr + 2, (value >> 16) & 0xFFFF)
            return
        if PAL_BASE <= addr < PAL_BASE + 2048:
            self.pal_clip += 1

    def load_rom_image(self, data: bytes, offset: int = 0) -> None:
        end = offset + len(data)
        if end > ROM_SIZE:
            raise ValueError("картридж больше 8 МБ")
        self.rom[offset:end] = data
        self.rom_used = max(self.rom_used, end)

    def audio_region(self) -> memoryview:
        return memoryview(self.sram)[AUDIO_BASE : AUDIO_BASE + AUDIO_SIZE]
