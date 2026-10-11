"""AMATERASU — 320×240 indexed framebuffer, 511-color RGB555 palette."""

from __future__ import annotations

from argonaut.font8x8 import FONT
from argonaut.hw import (
    CMD_CIRC,
    CMD_CIRCFILL,
    CMD_CLIP,
    CMD_CLS,
    CMD_FILL,
    CMD_GLYPH,
    CMD_LINE,
    CMD_MAP,
    CMD_PGET,
    CMD_PSET,
    CMD_RECT,
    CMD_SPR,
    CMD_TEXT_NUM,
    CMD_TEXT_STR,
    PALETTE_SLOTS,
    PIXELS,
    PIXEL_BUDGET,
    PPU_CAMX,
    PPU_CAMY,
    PPU_COLOR,
    PPU_H,
    PPU_PIXELS,
    PPU_SRC,
    PPU_STATUS,
    PPU_SX,
    PPU_SY,
    PPU_W,
    PPU_X,
    PPU_Y,
    SCREEN_H,
    SCREEN_W,
    STR_MAGIC,
    s32,
)
from argonaut.machine.memory import Memory


def rgb555_to_888(value: int) -> tuple[int, int, int]:
    r = (value >> 10) & 31
    g = (value >> 5) & 31
    b = value & 31
    return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2)


class PPU:
    def __init__(self, mem: Memory) -> None:
        self.mem = mem
        self.reg = [0] * 16
        self.pixels = 0
        self.overflow = 0
        self.cls_used = False
        self.gfx_addr = 0
        self.gfx_w = 128
        self.gfx_h = 128
        self.map_addr = 0
        self.map_w = 128
        self.map_h = 32
        self.clipx = 0
        self.clipy = 0
        self.clipw = SCREEN_W
        self.cliph = SCREEN_H
        mem.ppu = self

    def begin_frame(self) -> None:
        self.pixels = 0
        self.overflow = 0
        self.cls_used = False

    def take(self, n: int = 1) -> bool:
        if self.pixels >= PIXEL_BUDGET:
            self.overflow = 1
            return False
        self.pixels += n
        if self.pixels > PIXEL_BUDGET:
            self.overflow = 1
        return True

    def read(self, offset: int) -> int:
        if offset == PPU_STATUS:
            return self.overflow & 1
        if offset == PPU_PIXELS:
            return self.pixels & 0xFFFFFFFF
        idx = offset // 4
        if 0 <= idx < len(self.reg):
            return self.reg[idx] & 0xFFFFFFFF
        return 0

    def write(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        idx = offset // 4
        if 0 <= idx < len(self.reg):
            self.reg[idx] = value
        if offset == 0:
            self._exec(value)

    def _s(self, offset: int) -> int:
        return s32(self.reg[offset // 4])

    def _exec(self, cmd: int) -> None:
        if cmd == CMD_CLS:
            self.cls(self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_PSET:
            self.pset(self._s(PPU_X), self._s(PPU_Y), self.reg[PPU_COLOR // 4] & 0x1FF, camera=True)
        elif cmd == CMD_FILL:
            self.fill(self._s(PPU_X), self._s(PPU_Y), self._s(PPU_W), self._s(PPU_H), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_RECT:
            self.rect(self._s(PPU_X), self._s(PPU_Y), self._s(PPU_W), self._s(PPU_H), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_SPR:
            self.spr(
                self.reg[PPU_SRC // 4],
                self._s(PPU_X),
                self._s(PPU_Y),
                self._s(PPU_W),
                self._s(PPU_H),
            )
        elif cmd == CMD_GLYPH:
            self.glyph(self.reg[PPU_SRC // 4] & 127, self._s(PPU_X), self._s(PPU_Y), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_MAP:
            self.map_blit(
                self._s(PPU_SX),
                self._s(PPU_SY),
                self._s(PPU_X),
                self._s(PPU_Y),
                self._s(PPU_W),
                self._s(PPU_H),
            )
        elif cmd == CMD_TEXT_STR:
            self.text_ptr(self.reg[PPU_SRC // 4], self._s(PPU_X), self._s(PPU_Y), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_TEXT_NUM:
            self.text_num(s32(self.reg[PPU_SRC // 4]), self._s(PPU_X), self._s(PPU_Y), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_PGET:
            self.reg[PPU_SRC // 4] = self.pget(self._s(PPU_X), self._s(PPU_Y)) & 0xFFFFFFFF
        elif cmd == CMD_LINE:
            self.line(
                self._s(PPU_X),
                self._s(PPU_Y),
                self._s(PPU_W),
                self._s(PPU_H),
                self.reg[PPU_COLOR // 4] & 0x1FF,
            )
        elif cmd == CMD_CIRC:
            self.circ(self._s(PPU_X), self._s(PPU_Y), self._s(PPU_W), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_CIRCFILL:
            self.circfill(self._s(PPU_X), self._s(PPU_Y), self._s(PPU_W), self.reg[PPU_COLOR // 4] & 0x1FF)
        elif cmd == CMD_CLIP:
            self.set_clip(self._s(PPU_X), self._s(PPU_Y), self._s(PPU_W), self._s(PPU_H))

    def _pay(self, n: int) -> None:
        cpu = self.mem.cpu
        if cpu is not None and n > 0:
            cpu.cycles += n

    def _inside(self, x: int, y: int) -> bool:
        return (
            self.clipx <= x < self.clipx + self.clipw
            and self.clipy <= y < self.clipy + self.cliph
            and 0 <= x < SCREEN_W
            and 0 <= y < SCREEN_H
        )

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        if w < 0:
            x += w
            w = -w
        if h < 0:
            y += h
            h = -h
        self.clipx, self.clipy, self.clipw, self.cliph = x, y, w, h

    def cls(self, color: int) -> None:
        if color > 510:
            color = 0
            self.mem.pal_clip += 1
        if not self.cls_used:
            self._fill_all(color)
            self.cls_used = True
            return
        self.fill(0, 0, SCREEN_W, SCREEN_H, color, camera=False)

    def _fill_all(self, color: int) -> None:
        lo = color & 0xFF
        hi = (color >> 8) & 0xFF
        fb = self.mem.fb
        for i in range(0, len(fb), 2):
            fb[i] = lo
            fb[i + 1] = hi

    def pset(self, x: int, y: int, color: int, camera: bool = False, pay: bool = True) -> None:
        if camera:
            x += self._s(PPU_CAMX)
            y += self._s(PPU_CAMY)
        if pay:
            self._pay(1)
        if not self._inside(x, y):
            return
        self.mem.set_fb_index(y * SCREEN_W + x, color, count=True)

    def pget(self, x: int, y: int) -> int:
        x += self._s(PPU_CAMX)
        y += self._s(PPU_CAMY)
        if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
            return 0
        return self.mem.fb_index(y * SCREEN_W + x) & 0x1FF

    def fill(self, x: int, y: int, w: int, h: int, color: int, camera: bool = True) -> None:
        if camera:
            x += self._s(PPU_CAMX)
            y += self._s(PPU_CAMY)
        if w < 0:
            x += w
            w = -w
        if h < 0:
            y += h
            h = -h
        x0 = max(x, self.clipx, 0)
        y0 = max(y, self.clipy, 0)
        x1 = min(SCREEN_W, self.clipx + self.clipw, x + w)
        y1 = min(SCREEN_H, self.clipy + self.cliph, y + h)
        if x1 > x0 and y1 > y0:
            self._pay((x1 - x0) * (y1 - y0))
        for yy in range(y0, y1):
            row = yy * SCREEN_W
            for xx in range(x0, x1):
                if not self.mem.set_fb_index(row + xx, color, count=True):
                    return

    def rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        x += self._s(PPU_CAMX)
        y += self._s(PPU_CAMY)
        if w < 0:
            x += w
            w = -w
        if h < 0:
            y += h
            h = -h
        if w == 0 or h == 0:
            return
        for i in range(w):
            self.pset(x + i, y, color, camera=False)
            self.pset(x + i, y + h - 1, color, camera=False)
        for i in range(1, h - 1):
            self.pset(x, y + i, color, camera=False)
            self.pset(x + w - 1, y + i, color, camera=False)

    def _gfx_at(self, x: int, y: int) -> int:
        if not (0 <= x < self.gfx_w and 0 <= y < self.gfx_h):
            return 0
        off = (self.gfx_addr - 0x02000000) + y * self.gfx_w + x
        if off < 0 or off >= len(self.mem.rom):
            return 0
        return self.mem.rom[off]

    def spr(self, sid: int, x: int, y: int, tw: int, th: int) -> None:
        x += self._s(PPU_CAMX)
        y += self._s(PPU_CAMY)
        if tw <= 0:
            tw = 1
        if th <= 0:
            th = 1
        cols = max(1, self.gfx_w // 8)
        for ty in range(th):
            for tx in range(tw):
                tile = sid + tx + ty * cols
                sx0 = (tile % cols) * 8
                sy0 = (tile // cols) * 8
                for py in range(8):
                    for px in range(8):
                        color = self._gfx_at(sx0 + px, sy0 + py)
                        self._pay(1)
                        if color == 0:
                            continue
                        self.pset(x + tx * 8 + px, y + ty * 8 + py, color, camera=False, pay=False)

    def map_blit(self, tx: int, ty: int, dx: int, dy: int, tw: int, th: int) -> None:
        dx += self._s(PPU_CAMX)
        dy += self._s(PPU_CAMY)
        if tw <= 0 or th <= 0:
            return
        base = self.map_addr - 0x02000000
        for my in range(th):
            for mx in range(tw):
                cell_x = tx + mx
                cell_y = ty + my
                if not (0 <= cell_x < self.map_w and 0 <= cell_y < self.map_h):
                    continue
                off = base + (cell_y * self.map_w + cell_x) * 2
                if off < 0 or off + 1 >= len(self.mem.rom):
                    continue
                sid = self.mem.rom[off] | (self.mem.rom[off + 1] << 8)
                if sid == 0:
                    continue
                # draw one tile without applying camera a second time
                cols = max(1, self.gfx_w // 8)
                sx0 = (sid % cols) * 8
                sy0 = (sid // cols) * 8
                ox = dx + mx * 8
                oy = dy + my * 8
                for py in range(8):
                    for px in range(8):
                        color = self._gfx_at(sx0 + px, sy0 + py)
                        self._pay(1)
                        if color == 0:
                            continue
                        self.pset(ox + px, oy + py, color, camera=False, pay=False)

    def glyph(self, ch: int, x: int, y: int, color: int) -> None:
        ch &= 127
        bits = FONT[ch * 8 : ch * 8 + 8]
        self._pay(64)
        for row in range(8):
            line = bits[row]
            for col in range(8):
                if line & (0x80 >> col):
                    self.pset(x + col, y + row, color, camera=False, pay=False)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: int) -> None:
        x0 += self._s(PPU_CAMX)
        y0 += self._s(PPU_CAMY)
        x1 += self._s(PPU_CAMX)
        y1 += self._s(PPU_CAMY)
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        guard = dx + dy + 1
        while guard > 0:
            guard -= 1
            self.pset(x0, y0, color, camera=False)
            if x0 == x1 and y0 == y1:
                return
            e2 = err * 2
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def circ(self, cx: int, cy: int, r: int, color: int) -> None:
        cx += self._s(PPU_CAMX)
        cy += self._s(PPU_CAMY)
        if r < 0:
            return
        x = r
        y = 0
        d = 1 - r
        while x >= y:
            for px, py in (
                (x, y),
                (y, x),
                (-x, y),
                (-y, x),
                (x, -y),
                (y, -x),
                (-x, -y),
                (-y, -x),
            ):
                self.pset(cx + px, cy + py, color, camera=False)
            y += 1
            if d < 0:
                d += 2 * y + 1
            else:
                x -= 1
                d += 2 * (y - x) + 1

    def circfill(self, cx: int, cy: int, r: int, color: int) -> None:
        cx += self._s(PPU_CAMX)
        cy += self._s(PPU_CAMY)
        if r < 0:
            return
        for dy in range(-r, r + 1):
            span = 0
            while (span + 1) * (span + 1) + dy * dy <= r * r:
                span += 1
            self.fill(cx - span, cy + dy, span * 2 + 1, 1, color, camera=False)

    def text_ptr(self, ptr: int, x: int, y: int, color: int) -> None:
        x += self._s(PPU_CAMX)
        y += self._s(PPU_CAMY)
        if self.mem.read32(ptr) != STR_MAGIC:
            self.text_num(s32(ptr), x, y, color, camera=False)
            return
        length = self.mem.read32(ptr + 4) & 0xFFFF
        for i in range(min(length, 64)):
            ch = self.mem.read8(ptr + 8 + i)
            self.glyph(ch, x + i * 8, y, color)

    def text_num(self, value: int, x: int, y: int, color: int, camera: bool = True) -> None:
        if camera:
            x += self._s(PPU_CAMX)
            y += self._s(PPU_CAMY)
        text = str(int(value))
        for i, ch in enumerate(text[:16]):
            self.glyph(ord(ch), x + i * 8, y, color)

    def present(self) -> bytes:
        pal = [rgb555_to_888(self.mem.pal[i]) for i in range(PALETTE_SLOTS)]
        out = bytearray(PIXELS * 3)
        fb = self.mem.fb
        for i in range(PIXELS):
            idx = fb[i * 2] | (fb[i * 2 + 1] << 8)
            if idx > 510:
                idx = 0
            r, g, b = pal[idx]
            o = i * 3
            out[o] = r
            out[o + 1] = g
            out[o + 2] = b
        return bytes(out)

    def unique_colors(self) -> int:
        used = [0] * PALETTE_SLOTS
        fb = self.mem.fb
        for i in range(PIXELS):
            idx = fb[i * 2] | (fb[i * 2 + 1] << 8)
            if idx <= 510:
                used[idx] = 1
        seen = set()
        for i, flag in enumerate(used):
            if flag:
                seen.add(self.mem.pal[i] & 0x7FFF)
        return len(seen)
