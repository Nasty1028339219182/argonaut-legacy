"""Argonaut Legacy desktop console. Editors live in this window, not outside it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pygame

from argonaut.asm.assembler import AsmError
from argonaut.cart import Cart, blank_sound
from argonaut.demo import PALETTE, make_demo
from argonaut.hw import PALETTE_SLOTS, SCREEN_H, SCREEN_W, cycles_for_frame
from argonaut.ide import theme as T
from argonaut.ide.code_editor import CodeEditor
from argonaut.ide.i18n import blank_source, explain, help_lines, lang, toggle_lang, tr
from argonaut.machine.machine import Machine
from argonaut.machine.ppu import rgb555_to_888
from argonaut.paths import cart_dir, font_file
from argonaut.tpython.errors import TPyError

W, H = 1280, 800
TOP = 56
BOT = 32
WAVES = ["square", "triangle", "saw", "sine", "noise"]
PIANO = {
    pygame.K_z: "C",
    pygame.K_s: "C#",
    pygame.K_x: "D",
    pygame.K_d: "D#",
    pygame.K_c: "E",
    pygame.K_v: "F",
    pygame.K_g: "F#",
    pygame.K_b: "G",
    pygame.K_h: "A#",
    pygame.K_n: "A",
    pygame.K_j: "A#",
    pygame.K_m: "B",
}
# h was wrong above — A# is H in some layouts, J is A#. Fix map explicitly below.
PIANO = {
    pygame.K_z: "C",
    pygame.K_s: "C#",
    pygame.K_x: "D",
    pygame.K_d: "D#",
    pygame.K_c: "E",
    pygame.K_v: "F",
    pygame.K_g: "F#",
    pygame.K_b: "G",
    pygame.K_h: "G#",
    pygame.K_n: "A",
    pygame.K_j: "A#",
    pygame.K_m: "B",
}


def _sharp_display() -> None:
    """Draw 1:1 device pixels. Otherwise Windows stretches the window and blurs it."""
    os.environ["SDL_WINDOWS_DPI_AWARENESS"] = "permonitorv2"
    os.environ["SDL_RENDER_SCALE_QUALITY"] = "0"
    os.environ["SDL_VIDEO_CENTERED"] = "1"
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _ui_scale() -> int:
    try:
        sizes = pygame.display.get_desktop_sizes()
    except pygame.error:
        return 1
    if not sizes:
        return 1
    dw, dh = sizes[0]
    if dw < 400 or dh < 300:
        return 1
    dw = int(dw * 0.96)
    dh = int(dh * 0.92)
    scale = 1
    while scale < 3 and W * (scale + 1) <= dw and H * (scale + 1) <= dh:
        scale += 1
    return scale


def _safe(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_")
    return cleaned or "untitled"


def _rgb(rgb555_tuple) -> tuple[int, int, int]:
    r, g, b = rgb555_tuple
    return ((r & 31) << 3) | ((r & 31) >> 2), ((g & 31) << 3) | ((g & 31) >> 2), ((b & 31) << 3) | ((b & 31) >> 2)


def color_of(cart: Cart, index: int) -> tuple[int, int, int]:
    if index < 0 or index >= len(cart.palette):
        return (0, 0, 0)
    return _rgb(cart.palette[index])


class AudioOut:
    def __init__(self) -> None:
        self.ok = False
        self.ch = None
        try:
            pygame.mixer.init(22050, -16, 2, 512)
            pygame.mixer.set_num_channels(8)
            self.ch = pygame.mixer.Channel(0)
            self.ok = True
        except pygame.error:
            self.ok = False

    def push(self, data: bytes) -> None:
        if not self.ok or not data or self.ch is None:
            return
        sound = pygame.mixer.Sound(buffer=data)
        if not self.ch.get_busy():
            self.ch.play(sound)
        elif self.ch.get_queue() is None:
            self.ch.queue(sound)


class App:
    def __init__(self) -> None:
        _sharp_display()
        pygame.init()
        pygame.display.set_caption("Argonaut Legacy")
        self.scale = _ui_scale()
        self.window = pygame.display.set_mode((W * self.scale, H * self.scale))
        self.screen = pygame.Surface((W, H)).convert()
        self.clock = pygame.time.Clock()
        face = font_file()
        if face.is_file():
            self.font = pygame.font.Font(str(face), 16)
            self.small = pygame.font.Font(str(face), 13)
            self.big = pygame.font.Font(str(face), 22)
        else:
            self.font = pygame.font.SysFont("dejavusansmono", 16)
            self.small = pygame.font.SysFont("dejavusansmono", 13)
            self.big = pygame.font.SysFont("dejavusansmono", 22)
        self.cart = make_demo()
        self._normalize()
        self.code = CodeEditor(self.cart.code)
        self.machine = Machine()
        self.audio = AudioOut()
        self.mode = "code"
        self.prev_mode = "code"
        self.status = tr("ready")
        self.error_line = None
        self.overlay = None
        self.prompt = ""
        self.files: list[Path] = []
        self.file_i = 0
        self.alive = True
        self.clip = ""
        self.gfx_color = 1
        self.gfx_page = 0
        self.gfx_grid = True
        self.gfx_fill = False
        self.gfx_focus = 1
        self.gfx_undo: list[tuple] = []
        self.gfx_redo: list[tuple] = []
        self.map_sprite = 1
        self.map_ox = 0
        self.map_oy = 0
        self.map_page = 0
        self.snd_row = 0
        self.snd_ch = 0
        self.snd_oct = 4
        self.snd_preview = False
        self.sfx_slot = 0
        self.sfx_i = 0
        self.dragging = False
        try:
            pygame.scrap.init()
        except pygame.error:
            pass

    def _normalize(self) -> None:
        while len(self.cart.instruments) < 8:
            self.cart.instruments.append({"wave": "square", "volume": 100})
        while len(self.cart.pattern) < 32:
            self.cart.pattern.append([""] * 8)
        for row in self.cart.pattern:
            while len(row) < 8:
                row.append("")
        need = self.cart.gfx_w * self.cart.gfx_h
        if len(self.cart.gfx) < need:
            self.cart.gfx.extend(bytearray(need - len(self.cart.gfx)))
        need_cells = self.cart.map_w * self.cart.map_h
        if len(self.cart.map_cells) < need_cells:
            self.cart.map_cells.extend([0] * (need_cells - len(self.cart.map_cells)))
        while len(self.cart.sfx) < 8:
            self.cart.sfx.append([])
        self.cart.sfx = self.cart.sfx[:8]
        for i, row in enumerate(self.cart.sfx):
            if not isinstance(row, list):
                self.cart.sfx[i] = []
        if not isinstance(self.cart.flags, list):
            self.cart.flags = []
        self.cart.flags = [int(v) & 255 for v in self.cart.flags[:256]]
        while len(self.cart.flags) < 256:
            self.cart.flags.append(0)

    def sync(self) -> None:
        self.cart.code = self.code.source()

    def clip_get(self) -> str:
        try:
            raw = pygame.scrap.get(pygame.SCRAP_TEXT)
            if raw:
                return raw.decode("utf-8", "replace").replace("\x00", "")
        except pygame.error:
            pass
        return self.clip

    def clip_set(self, text: str) -> None:
        self.clip = text
        try:
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
        except pygame.error:
            pass

    def buttons(self) -> int:
        mods = pygame.key.get_mods()
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_ALT):
            return 0
        k = pygame.key.get_pressed()
        bits = 0
        if k[pygame.K_LEFT] or k[pygame.K_a]:
            bits |= 1 << 0
        if k[pygame.K_RIGHT] or k[pygame.K_d]:
            bits |= 1 << 1
        if k[pygame.K_UP] or k[pygame.K_w]:
            bits |= 1 << 2
        if k[pygame.K_DOWN] or k[pygame.K_s]:
            bits |= 1 << 3
        if k[pygame.K_z] or k[pygame.K_j]:
            bits |= 1 << 4
        if k[pygame.K_x] or k[pygame.K_k]:
            bits |= 1 << 5
        if k[pygame.K_RETURN]:
            bits |= 1 << 6
        if k[pygame.K_TAB] or k[pygame.K_RSHIFT]:
            bits |= 1 << 7
        return bits

    def run_cart(self) -> None:
        self.sync()
        self.snd_preview = False
        try:
            self.machine.load(self.cart)
        except (TPyError, AsmError) as exc:
            self.error_line = getattr(exc, "line", None)
            self.status = tr("build-fail", msg=explain(exc))
            self.mode = "code"
            return
        self.error_line = None
        self.prev_mode = self.mode if self.mode != "run" else self.prev_mode
        self.mode = "run"
        self.status = tr("running")

    def stop_run(self) -> None:
        if self.mode == "run":
            try:
                self.cart.flags = self.machine.pull_flags()
            except Exception:
                pass
            self.mode = self.prev_mode or "code"
            spent = self.machine.cpu.cycles
            self.status = tr("stopped", n=spent)

    def save(self, name: str | None = None) -> None:
        self.sync()
        if name:
            self.cart.name = _safe(name)
        folder = cart_dir()
        folder.mkdir(exist_ok=True)
        path = folder / f"{_safe(self.cart.name)}.alc"
        path.write_text(self.cart.to_json(), encoding="utf-8")
        self.status = tr("saved", name=path.name)

    def load_path(self, path: Path) -> bool:
        try:
            self.cart = Cart.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError) as exc:
            self.status = tr("unreadable", msg=exc)
            return False
        self.code.set_source(self.cart.code)
        self._normalize()
        self.gfx_undo.clear()
        self.gfx_redo.clear()
        self.error_line = None
        self.mode = "code"
        self.status = tr("loaded", name=self.cart.name)
        return True

    def new_cart(self) -> None:
        instruments, pattern, sfx = blank_sound()
        source = blank_source()
        self.cart = Cart(
            name="untitled",
            code=source,
            palette=list(PALETTE),
            gfx=bytearray(128 * 128),
            map_cells=[0] * (128 * 32),
            instruments=instruments,
            pattern=pattern,
            sfx=sfx,
        )
        self.code.set_source(source)
        self.gfx_undo.clear()
        self.gfx_redo.clear()
        self.mode = "code"
        self.status = tr("empty-cart")

    def command(self, line: str) -> None:
        parts = line.strip().split()
        if not parts:
            return
        cmd, *rest = parts
        cmd = cmd.lower()
        if cmd == "run":
            self.run_cart()
        elif cmd == "new":
            self.new_cart()
        elif cmd == "save":
            self.save(rest[0] if rest else None)
        elif cmd == "load" and rest:
            path = cart_dir() / f"{_safe(rest[0])}.alc"
            if not path.exists():
                self.status = tr("no-cart")
            else:
                self.load_path(path)
        else:
            self.status = tr("commands")

    def on_event(self, event) -> None:
        event = self._logical_event(event)
        if event.type == pygame.QUIT:
            self.alive = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
            self.alive = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F7 and self.overlay != "prompt":
            toggle_lang()
            self.status = tr("lang-now")
            return
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.overlay != "prompt"
            and self._lang_rect().collidepoint(event.pos)
        ):
            toggle_lang()
            self.status = tr("lang-now")
            return
        if self.overlay == "help":
            if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                self.overlay = None
            return
        if self.overlay == "files":
            self._files_event(event)
            return
        if self.overlay == "prompt":
            self._prompt_event(event)
            return
        if self.overlay == "debug":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_F12):
                self.overlay = None
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F1:
                self.overlay = "help"
                return
            if event.key == pygame.K_F12 and self.mode == "run":
                self.overlay = "debug"
                return
            if event.key == pygame.K_ESCAPE:
                if self.mode == "run":
                    self.stop_run()
                return
            if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_r:
                self.run_cart()
                return
            if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_s:
                self.save()
                return
            if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_o:
                self.files = sorted(cart_dir().glob("*.alc"))
                self.file_i = 0
                self.overlay = "files"
                return
            if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_n:
                self.new_cart()
                return
            if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_p:
                self.prompt = ""
                self.overlay = "prompt"
                return
            if event.key == pygame.K_F2:
                self._set_mode("code")
                return
            if event.key == pygame.K_F3:
                self._set_mode("gfx")
                return
            if event.key == pygame.K_F4:
                self._set_mode("map")
                return
            if event.key == pygame.K_F5:
                self._set_mode("snd")
                return
            if event.key == pygame.K_F6:
                self._set_mode("sfx")
                return
            if (
                self.mode == "gfx"
                and event.mod & pygame.KMOD_CTRL
                and event.key == pygame.K_z
            ):
                if event.mod & pygame.KMOD_SHIFT:
                    self._gfx_redo_do()
                else:
                    self._gfx_undo_do()
                return
            if self.mode == "gfx" and event.mod & pygame.KMOD_CTRL and event.key == pygame.K_y:
                self._gfx_redo_do()
                return
        if self.mode == "run":
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            tab = self._tab_at(event.pos)
            if tab:
                self._set_mode(tab)
                return
        if self.mode == "code":
            self._code_event(event)
        elif self.mode == "gfx":
            self._gfx_event(event)
        elif self.mode == "map":
            self._map_event(event)
        elif self.mode == "snd":
            self._snd_event(event)
        elif self.mode == "sfx":
            self._sfx_event(event)

    def _set_mode(self, mode: str) -> None:
        if self.mode == "code":
            self.sync()
        if mode != "snd":
            self.snd_preview = False
            self.machine.apu.playing = False
        if self.mode == "sfx" and mode != "sfx":
            self.machine.apu.sfx_notes = []
            if self.machine.apu.channels:
                self.machine.apu.channels[7].on = False
        self.mode = mode
        if mode == "code":
            pygame.key.start_text_input()
        else:
            pygame.key.stop_text_input()

    def _code_event(self, event) -> None:
        rect = self._body()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and rect.collidepoint(event.pos):
            row, col = self.code.pos_at(event.pos[0], event.pos[1], rect, self.font)
            self.code.click(col, row, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
            self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            row, col = self.code.pos_at(event.pos[0], event.pos[1], rect, self.font)
            self.code.cy, self.code.cx = row, col
            self.code._clamp()
        elif event.type == pygame.MOUSEWHEEL:
            self.code.scroll = max(0, self.code.scroll - event.y * 3)
        elif event.type == pygame.KEYDOWN:
            self.code.on_keydown(event, self.clip_get, self.clip_set)
        elif event.type == pygame.TEXTINPUT:
            if pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_ALT):
                return
            self.code.insert(event.text)

    def _files_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.overlay = None
        elif event.key == pygame.K_UP:
            self.file_i = max(0, self.file_i - 1)
        elif event.key == pygame.K_DOWN:
            self.file_i = min(max(0, len(self.files) - 1), self.file_i + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.files:
            self.load_path(self.files[self.file_i])
            self.overlay = None

    def _prompt_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.overlay = None
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.command(self.prompt)
                self.overlay = None
            elif event.key == pygame.K_BACKSPACE:
                self.prompt = self.prompt[:-1]
        elif event.type == pygame.TEXTINPUT:
            self.prompt += event.text

    def _gfx_snapshot(self) -> tuple:
        flags = [int(v) & 255 for v in self.cart.flags[:256]]
        while len(flags) < 256:
            flags.append(0)
        palette = [tuple(color) for color in self.cart.palette]
        return bytes(self.cart.gfx), flags, palette

    def _gfx_push_undo(self) -> None:
        self.gfx_undo.append(self._gfx_snapshot())
        if len(self.gfx_undo) > 40:
            del self.gfx_undo[:-40]
        self.gfx_redo.clear()

    def _gfx_restore(self, snap: tuple) -> None:
        gfx, flags, palette = snap
        self.cart.gfx[:] = gfx
        self.cart.flags = list(flags)
        self.cart.palette = [tuple(color) for color in palette]

    def _gfx_undo_do(self) -> None:
        if not self.gfx_undo:
            return
        self.gfx_redo.append(self._gfx_snapshot())
        self._gfx_restore(self.gfx_undo.pop())

    def _gfx_redo_do(self) -> None:
        if not self.gfx_redo:
            return
        self.gfx_undo.append(self._gfx_snapshot())
        self._gfx_restore(self.gfx_redo.pop())

    def _toggle_flag(self, bit: int, record: bool = True) -> None:
        if record:
            self._gfx_push_undo()
        sid = self.gfx_focus & 255
        while len(self.cart.flags) < 256:
            self.cart.flags.append(0)
        mask = 1 << (bit & 7)
        self.cart.flags[sid] = (int(self.cart.flags[sid]) ^ mask) & 255

    def _gfx_edits(self, pos) -> bool:
        return bool(
            self._gfx_canvas().collidepoint(pos)
            or self._flag_at(pos) is not None
            or self._channel_at(pos) is not None
        )

    def _gfx_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_g:
                self.gfx_grid = not self.gfx_grid
            elif event.key == pygame.K_f:
                self.gfx_fill = not self.gfx_fill
            elif event.key == pygame.K_LEFTBRACKET:
                self.gfx_page = max(0, self.gfx_page - 1)
            elif event.key == pygame.K_RIGHTBRACKET:
                self.gfx_page = min((PALETTE_SLOTS - 1) // 32, self.gfx_page + 1)
            elif pygame.K_1 <= event.key <= pygame.K_8 and not (
                event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT)
            ):
                self._toggle_flag(event.key - pygame.K_1)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self._gfx_edits(event.pos):
                self._gfx_push_undo()
            self._gfx_mouse(event.pos, event.button, True)
        elif event.type == pygame.MOUSEMOTION and event.buttons[0]:
            self._gfx_mouse(event.pos, 1, False)

    def _gfx_mouse(self, pos, button, click: bool) -> None:
        canvas = self._gfx_canvas()
        if canvas.collidepoint(pos):
            x = (pos[0] - canvas.x) // 4
            y = (pos[1] - canvas.y) // 4
            if not (0 <= x < 128 and 0 <= y < 128):
                return
            self.gfx_focus = (y // 8) * 16 + (x // 8)
            if button == 3:
                self.gfx_color = self.cart.gfx[y * 128 + x]
                return
            if self.gfx_fill and click:
                self._flood(x, y, self.gfx_color)
            else:
                self.cart.gfx[y * 128 + x] = self.gfx_color
            return
        sw = self._swatch_at(pos)
        if sw is not None and click:
            self.gfx_color = sw
            return
        flag = self._flag_at(pos)
        if flag is not None and click and button == 1:
            self._toggle_flag(flag, record=False)
            return
        ch = self._channel_at(pos)
        if ch is not None and click:
            self._set_channel(ch[0], ch[1])

    def _flood(self, x, y, color) -> None:
        target = self.cart.gfx[y * 128 + x]
        if target == color:
            return
        stack = [(x, y)]
        guard = 0
        while stack and guard < 20000:
            guard += 1
            x, y = stack.pop()
            if not (0 <= x < 128 and 0 <= y < 128):
                continue
            i = y * 128 + x
            if self.cart.gfx[i] != target:
                continue
            self.cart.gfx[i] = color
            stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    def _map_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.map_ox = max(0, self.map_ox - 1)
            elif event.key == pygame.K_RIGHT:
                self.map_ox = min(self.cart.map_w - 1, self.map_ox + 1)
            elif event.key == pygame.K_UP:
                self.map_oy = max(0, self.map_oy - 1)
            elif event.key == pygame.K_DOWN:
                self.map_oy = min(self.cart.map_h - 1, self.map_oy + 1)
            elif event.key == pygame.K_LEFTBRACKET:
                self.map_sprite = max(0, self.map_sprite - 1)
                self.map_page = self.map_sprite // 64
            elif event.key == pygame.K_RIGHTBRACKET:
                self.map_sprite = min(255, self.map_sprite + 1)
                self.map_page = self.map_sprite // 64
            elif event.key in (pygame.K_COMMA, pygame.K_PAGEUP):
                self.map_page = max(0, self.map_page - 1)
            elif event.key in (pygame.K_PERIOD, pygame.K_PAGEDOWN):
                self.map_page = min(3, self.map_page + 1)
        if event.type == pygame.MOUSEBUTTONDOWN or (
            event.type == pygame.MOUSEMOTION and event.buttons[0]
        ):
            button = event.button if event.type == pygame.MOUSEBUTTONDOWN else 1
            cell = self._map_cell_at(event.pos)
            if cell:
                x, y = cell
                if button == 3:
                    self.map_sprite = self.cart.map_cells[y * self.cart.map_w + x]
                else:
                    self.cart.map_cells[y * self.cart.map_w + x] = self.map_sprite
            picked = self._picker_at(event.pos)
            if picked is not None and event.type == pygame.MOUSEBUTTONDOWN:
                self.map_sprite = picked

    def _snd_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.snd_row = max(0, self.snd_row - 1)
        elif event.key == pygame.K_DOWN:
            self.snd_row = min(31, self.snd_row + 1)
        elif event.key == pygame.K_LEFT:
            self.snd_ch = max(0, self.snd_ch - 1)
        elif event.key == pygame.K_RIGHT:
            self.snd_ch = min(7, self.snd_ch + 1)
        elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            self.cart.pattern[self.snd_row][self.snd_ch] = ""
        elif event.key == pygame.K_o:
            self.cart.pattern[self.snd_row][self.snd_ch] = "OFF"
        elif event.key in (pygame.K_COMMA, pygame.K_MINUS):
            self.snd_oct = max(1, self.snd_oct - 1)
        elif event.key in (pygame.K_PERIOD, pygame.K_EQUALS):
            self.snd_oct = min(7, self.snd_oct + 1)
        elif event.key == pygame.K_SPACE:
            self._toggle_preview()
        elif event.key in PIANO:
            note = f"{PIANO[event.key]}{self.snd_oct}"
            self.cart.pattern[self.snd_row][self.snd_ch] = note
            self.snd_row = min(31, self.snd_row + 1)
        elif event.key == pygame.K_TAB:
            inst = self.cart.instruments[self.snd_ch]
            try:
                i = WAVES.index(inst["wave"])
            except ValueError:
                i = 0
            inst["wave"] = WAVES[(i + 1) % len(WAVES)]
        elif event.key == pygame.K_LEFTBRACKET:
            inst = self.cart.instruments[self.snd_ch]
            inst["volume"] = max(0, int(inst.get("volume", 120)) - 15)
        elif event.key == pygame.K_RIGHTBRACKET:
            inst = self.cart.instruments[self.snd_ch]
            inst["volume"] = min(255, int(inst.get("volume", 120)) + 15)

    def _sfx_notes(self) -> list:
        self._normalize()
        return self.cart.sfx[self.sfx_slot]

    def _sfx_insert(self, note: str) -> None:
        notes = self._sfx_notes()
        if self.sfx_i >= len(notes):
            notes.append(note)
            self.sfx_i = len(notes)
        else:
            notes.insert(self.sfx_i, note)
            self.sfx_i += 1
        if len(notes) > 32:
            del notes[32:]
            self.sfx_i = min(self.sfx_i, len(notes))

    def _preview_sfx(self) -> None:
        self.snd_preview = False
        self.machine.apu.playing = False
        self.machine.apu.load_waves(self.machine.mem.sram, self.cart.instruments)
        self.machine.apu.sfx_bank = [list(row) for row in self.cart.sfx]
        self.machine.apu.handle_event("sfx", self.sfx_slot)

    def _sfx_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.sfx_i = max(0, self.sfx_i - 1)
        elif event.key == pygame.K_DOWN:
            self.sfx_i = min(len(self._sfx_notes()), self.sfx_i + 1)
        elif event.key == pygame.K_LEFT:
            self.sfx_slot = max(0, self.sfx_slot - 1)
            self.sfx_i = 0
        elif event.key == pygame.K_RIGHT:
            self.sfx_slot = min(7, self.sfx_slot + 1)
            self.sfx_i = 0
        elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            notes = self._sfx_notes()
            if not notes:
                return
            index = self.sfx_i if self.sfx_i < len(notes) else len(notes) - 1
            notes.pop(index)
            self.sfx_i = min(self.sfx_i, len(notes))
        elif event.key == pygame.K_o:
            self._sfx_insert("OFF")
        elif event.key in (pygame.K_COMMA, pygame.K_MINUS):
            self.snd_oct = max(1, self.snd_oct - 1)
        elif event.key in (pygame.K_PERIOD, pygame.K_EQUALS):
            self.snd_oct = min(7, self.snd_oct + 1)
        elif event.key == pygame.K_SPACE:
            self._preview_sfx()
        elif event.key in PIANO:
            self._sfx_insert(f"{PIANO[event.key]}{self.snd_oct}")

    def _toggle_preview(self) -> None:
        self.snd_preview = not self.snd_preview
        self.machine.apu.load_waves(self.machine.mem.sram, self.cart.instruments)
        self.machine.apu.pattern = self.cart.pattern
        self.machine.apu.bpm = self.cart.bpm
        self.machine.apu.sfx_bank = self.cart.sfx
        self.machine.apu.playing = self.snd_preview
        self.machine.apu.row = 0
        self.machine.apu.accum = 0
        if self.snd_preview:
            self.machine.apu._apply_row()
        else:
            for ch in self.machine.apu.channels:
                ch.on = False

    def tick(self) -> None:
        voice = bool(self.machine.apu.sfx_notes)
        if self.mode == "run":
            self.machine.frame(self.buttons())
            self.audio.push(self.machine.apu.render(1, self.machine.mem.sram))
        elif self.snd_preview or voice:
            self.machine.apu.tick_frame()
            self.audio.push(self.machine.apu.render(1, self.machine.mem.sram))

    def draw(self) -> None:
        self.screen.fill(T.BG)
        self._draw_top()
        if self.mode == "code":
            self.code.draw(self.screen, self._body(), self.font, self.error_line)
        elif self.mode == "gfx":
            self._draw_gfx()
        elif self.mode == "map":
            self._draw_map()
        elif self.mode == "snd":
            self._draw_snd()
        elif self.mode == "sfx":
            self._draw_sfx()
        elif self.mode == "run":
            self._draw_run()
        self._draw_bot()
        if self.overlay == "help":
            self._draw_help()
        elif self.overlay == "files":
            self._draw_files()
        elif self.overlay == "prompt":
            self._draw_prompt()
        elif self.overlay == "debug":
            self._draw_debug()

    def _body(self) -> pygame.Rect:
        return pygame.Rect(0, TOP, W, H - TOP - BOT)

    def _tab_rects(self) -> list[tuple[str, pygame.Rect]]:
        labels = ("code", "gfx", "map", "snd", "sfx")
        rects = []
        x = 300
        for mode in labels:
            rect = pygame.Rect(x, 12, 112, 32)
            rects.append((mode, rect))
            x += 118
        return rects

    def _tab_at(self, pos) -> str | None:
        if pos[1] > TOP:
            return None
        for mode, rect in self._tab_rects():
            if rect.collidepoint(pos):
                return mode
        return None

    def _lang_rect(self) -> pygame.Rect:
        return pygame.Rect(908, 14, 78, 28)

    def _draw_top(self) -> None:
        pygame.draw.rect(self.screen, T.BG2, (0, 0, W, TOP))
        pygame.draw.line(self.screen, T.AMBER_DIM, (0, TOP - 1), (W, TOP - 1))
        title = self.big.render("ARGONAUT", True, T.AMBER)
        self.screen.blit(title, (16, 8))
        sub = self.small.render("LEGACY", True, T.TEAL)
        self.screen.blit(sub, (16, 32))
        chip = self.small.render("THOTH 20.00", True, T.MUTED)
        self.screen.blit(chip, (150, 20))
        for mode, rect in self._tab_rects():
            active = self.mode == mode or (self.mode == "run" and mode == self.prev_mode)
            pygame.draw.rect(self.screen, T.BG if not active else (28, 40, 36), rect, border_radius=3)
            if active:
                pygame.draw.line(self.screen, T.AMBER, (rect.x + 8, rect.bottom - 3), (rect.right - 8, rect.bottom - 3), 2)
            label = tr("tab-" + mode)
            img = self.small.render(label, True, T.AMBER if active else T.INK)
            self.screen.blit(img, img.get_rect(center=rect.center))
        self._draw_lang()
        if self.mode == "run":
            late = self.machine.late
            lamp = T.RED if late else T.TEAL
            pygame.draw.circle(self.screen, lamp, (1040, 28), 6)
            word = "LATE" if late else tr("run-lamp")
            self.screen.blit(self.small.render(word, True, lamp), (1054, 20))
            budget = cycles_for_frame(max(0, self.machine.frame_index - 1))
            spent = self.machine.cpu.cycles
            self.screen.blit(self.small.render(f"{spent} / {budget}", True, T.PAPER), (1120, 20))

    def _draw_lang(self) -> None:
        rect = self._lang_rect()
        pygame.draw.rect(self.screen, T.BG, rect, border_radius=3)
        pygame.draw.rect(self.screen, T.TEAL, rect, 1, border_radius=3)
        current = lang()
        en = self.small.render("EN", True, T.AMBER if current == "en" else T.MUTED)
        ru = self.small.render("RU", True, T.AMBER if current == "ru" else T.MUTED)
        self.screen.blit(en, (rect.x + 8, rect.y + 6))
        self.screen.blit(ru, (rect.x + 40, rect.y + 6))

    def _draw_bot(self) -> None:
        y = H - BOT
        pygame.draw.rect(self.screen, T.BG2, (0, y, W, BOT))
        pygame.draw.line(self.screen, T.LINE, (0, y), (W, y))
        if self.mode == "code":
            where = tr("bot-code", line=self.code.cy + 1, col=self.code.cx + 1)
        elif self.mode == "gfx":
            tool = tr("tool-fill") if self.gfx_fill else tr("tool-brush")
            where = tr("bot-gfx", c=self.gfx_color, tool=tool)
        elif self.mode == "map":
            where = tr("bot-map", n=self.map_sprite)
        elif self.mode == "snd":
            where = tr("bot-snd", n=self.snd_oct)
        elif self.mode == "sfx":
            where = tr("bot-sfx", n=self.sfx_slot, o=self.snd_oct)
        else:
            uniq = self.machine.ppu.unique_colors()
            where = tr(
                "bot-run",
                u=uniq,
                c=self.machine.mem.pal_clip,
                f=self.machine.mem.fault,
            )
        left = self.small.render(f"{self.cart.name}.alc", True, T.TEAL)
        self.screen.blit(left, (12, y + 8))
        mid = self.small.render(self.status[:90], True, T.CLAY if self.error_line else T.MUTED)
        self.screen.blit(mid, (160, y + 8))
        right = self.small.render(where, True, T.PAPER)
        self.screen.blit(right, (W - 12 - right.get_width(), y + 8))

    def _draw_run(self) -> None:
        body = self._body()
        scale = 3
        pw, ph = SCREEN_W * scale, SCREEN_H * scale
        ox = 16
        oy = body.y + (body.height - ph) // 2
        pygame.draw.rect(self.screen, (28, 20, 14), (ox - 10, oy - 10, pw + 20, ph + 20))
        pygame.draw.rect(self.screen, T.AMBER_DIM, (ox - 4, oy - 4, pw + 8, ph + 8), 1)
        frame = self.machine.ppu.present()
        surf = pygame.image.frombuffer(frame, (SCREEN_W, SCREEN_H), "RGB")
        big = pygame.transform.scale(surf, (pw, ph))
        self.screen.blit(big, (ox, oy))
        scan = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for y in range(0, ph, 3):
            pygame.draw.line(scan, (0, 0, 0, 36), (0, y), (pw, y))
        self.screen.blit(scan, (ox, oy))
        panel = pygame.Rect(ox + pw + 28, body.y + 16, W - (ox + pw + 44), body.height - 32)
        pygame.draw.rect(self.screen, T.BG2, panel)
        self._label(self.small, "AMATERASU", T.AMBER, panel.x + 16, panel.y + 16)
        self._label(self.small, "320×240  RGB555  511", T.MUTED, panel.x + 16, panel.y + 36)
        budget = cycles_for_frame(max(0, self.machine.frame_index - 1))
        spent = min(self.machine.cpu.cycles, budget)
        self._label(self.small, "THOTH", T.AMBER, panel.x + 16, panel.y + 70)
        bar = pygame.Rect(panel.x + 16, panel.y + 92, panel.width - 32, 10)
        pygame.draw.rect(self.screen, T.BG, bar)
        fill = int(bar.width * (spent / budget)) if budget else 0
        pygame.draw.rect(self.screen, T.RED if self.machine.late else T.TEAL, (bar.x, bar.y, max(0, fill), bar.height))
        self._label(self.small, "STRIBOG", T.AMBER, panel.x + 16, panel.y + 120)
        levels = self.machine.apu.levels()
        for i, level in enumerate(levels):
            h = int(36 * (level / 255)) if level else 0
            x = panel.x + 16 + i * 22
            pygame.draw.rect(self.screen, T.BG, (x, panel.y + 146, 14, 36))
            if h:
                pygame.draw.rect(self.screen, T.TEAL, (x, panel.y + 146 + 36 - h, 14, h))
        self._label(self.small, tr("log"), T.AMBER, panel.x + 16, panel.y + 200)
        for i, line in enumerate(self.machine.log_lines[-8:]):
            self._label(self.small, line[:28], T.PAPER, panel.x + 16, panel.y + 222 + i * 18)
        self._label(self.small, tr("run-a"), T.MUTED, panel.x + 16, panel.bottom - 48)
        self._label(self.small, tr("run-zx"), T.MUTED, panel.x + 16, panel.bottom - 28)

    def _gfx_canvas(self) -> pygame.Rect:
        return pygame.Rect(24, TOP + 20, 512, 512)

    def _draw_gfx(self) -> None:
        canvas = self._gfx_canvas()
        sheet = pygame.Surface((128, 128))
        px = pygame.PixelArray(sheet)
        for y in range(128):
            for x in range(128):
                idx = self.cart.gfx[y * 128 + x]
                if idx == 0:
                    px[x, y] = (18, 22, 24) if (x // 4 + y // 4) % 2 == 0 else (28, 32, 34)
                else:
                    px[x, y] = color_of(self.cart, idx)
        del px
        if self.gfx_grid:
            for t in range(0, 128, 8):
                pygame.draw.line(sheet, (60, 70, 66), (t, 0), (t, 127))
                pygame.draw.line(sheet, (60, 70, 66), (0, t), (127, t))
        self.screen.blit(pygame.transform.scale(sheet, (512, 512)), canvas.topleft)
        pygame.draw.rect(self.screen, T.AMBER_DIM, canvas, 1)
        self._label(self.small, tr("gfx-pal"), T.AMBER, 560, TOP + 20)
        self._draw_swatches(560, TOP + 44)
        self._label(self.small, tr("gfx-rgb"), T.MUTED, 560, TOP + 168)
        self._draw_channels(560, TOP + 192)
        idx = self.gfx_color
        rgb = self.cart.palette[idx] if idx < len(self.cart.palette) else (0, 0, 0)
        self._label(
            self.font,
            tr("gfx-slot", idx=idx, r=rgb[0], g=rgb[1], b=rgb[2]),
            T.PAPER,
            560,
            TOP + 300,
        )
        self._label(self.small, tr("gfx-zero"), T.MUTED, 560, TOP + 330)
        self._label(self.small, tr("gfx-pick"), T.MUTED, 560, TOP + 350)
        self._draw_flags()
        while len(self.cart.palette) <= idx:
            self.cart.palette.append((0, 0, 0))

    def _flag_rect(self, bit: int) -> pygame.Rect:
        return pygame.Rect(560 + bit * 34, TOP + 400, 28, 26)

    def _flag_at(self, pos) -> int | None:
        for bit in range(8):
            if self._flag_rect(bit).collidepoint(pos):
                return bit
        return None

    def _draw_flags(self) -> None:
        sid = self.gfx_focus & 255
        self._label(self.small, tr("gfx-flags", n=sid), T.AMBER, 560, TOP + 376)
        byte = int(self.cart.flags[sid]) & 255 if sid < len(self.cart.flags) else 0
        for bit in range(8):
            rect = self._flag_rect(bit)
            on = bool(byte & (1 << bit))
            pygame.draw.rect(self.screen, T.TEAL if on else T.BG2, rect)
            pygame.draw.rect(self.screen, T.AMBER if on else T.LINE, rect, 1)
            mark = self.small.render(str(bit), True, T.BG if on else T.INK)
            self.screen.blit(mark, mark.get_rect(center=rect.center))
        self._label(self.small, tr("gfx-undo"), T.MUTED, 560, TOP + 434)

    def _swatch_rect(self, n: int) -> pygame.Rect:
        col = n % 16
        row = n // 16
        return pygame.Rect(560 + col * 28, TOP + 44 + row * 28, 24, 24)

    def _draw_swatches(self, x, y) -> None:
        base = self.gfx_page * 32
        for n in range(32):
            idx = base + n
            rect = self._swatch_rect(n)
            if idx >= PALETTE_SLOTS:
                break
            pygame.draw.rect(self.screen, color_of(self.cart, idx) if idx < len(self.cart.palette) else (0, 0, 0), rect)
            if idx == self.gfx_color:
                pygame.draw.rect(self.screen, T.AMBER, rect, 2)
            else:
                pygame.draw.rect(self.screen, T.LINE, rect, 1)

    def _swatch_at(self, pos) -> int | None:
        base = self.gfx_page * 32
        for n in range(32):
            if self._swatch_rect(n).collidepoint(pos):
                idx = base + n
                return idx if idx < PALETTE_SLOTS else None
        return None

    def _draw_channels(self, x, y) -> None:
        idx = self.gfx_color
        while len(self.cart.palette) <= idx:
            self.cart.palette.append((0, 0, 0))
        rgb = list(self.cart.palette[idx])
        for c in range(3):
            for v in range(32):
                rect = pygame.Rect(x + c * 150 + v * 4, y, 4, 18)
                sample = [0, 0, 0]
                sample[c] = v
                pygame.draw.rect(self.screen, _rgb(tuple(sample)), rect)
            mark = pygame.Rect(x + c * 150 + rgb[c] * 4, y - 3, 4, 24)
            pygame.draw.rect(self.screen, T.INK, mark)

    def _channel_at(self, pos) -> tuple[int, int] | None:
        x, y = 560, TOP + 192
        for c in range(3):
            for v in range(32):
                rect = pygame.Rect(x + c * 150 + v * 4 - 1, y - 4, 6, 28)
                if rect.collidepoint(pos):
                    return c, v
        return None

    def _set_channel(self, channel: int, value: int) -> None:
        idx = self.gfx_color
        while len(self.cart.palette) <= idx:
            self.cart.palette.append((0, 0, 0))
        rgb = list(self.cart.palette[idx])
        rgb[channel] = value
        self.cart.palette[idx] = tuple(rgb)
        if len(self.cart.palette) > PALETTE_SLOTS:
            self.cart.palette = self.cart.palette[:PALETTE_SLOTS]

    def _draw_map(self) -> None:
        self._label(self.small, tr("map-title"), T.AMBER, 16, TOP + 8)
        origin = (16, TOP + 32)
        view_w, view_h = 22, 16
        cell = 24
        for sy in range(view_h):
            for sx in range(view_w):
                mx = self.map_ox + sx
                my = self.map_oy + sy
                rect = pygame.Rect(origin[0] + sx * cell, origin[1] + sy * cell, cell - 1, cell - 1)
                if mx >= self.cart.map_w or my >= self.cart.map_h:
                    continue
                sid = self.cart.map_cells[my * self.cart.map_w + mx]
                pygame.draw.rect(self.screen, T.BG2, rect)
                self._blit_sprite(sid, rect.inflate(-6, -6))
        pygame.draw.rect(
            self.screen,
            T.AMBER_DIM,
            (origin[0] - 2, origin[1] - 2, view_w * cell + 2, view_h * cell + 2),
            1,
        )
        panel = pygame.Rect(560, TOP, W - 560, H - TOP - BOT)
        pygame.draw.rect(self.screen, T.BG, panel)
        pygame.draw.line(self.screen, T.LINE, (560, TOP), (560, H - BOT))
        self._label(self.small, tr("map-picked", n=self.map_sprite), T.PAPER, 580, TOP + 16)
        self._blit_sprite(self.map_sprite, pygame.Rect(580, TOP + 40, 48, 48))
        start = self.map_page * 64
        self._label(self.small, tr("map-range", a=start, b=start + 63), T.MUTED, 648, TOP + 48)
        self._label(self.small, tr("map-page"), T.MUTED, 648, TOP + 68)
        for i in range(64):
            sid = start + i
            rect = pygame.Rect(580 + (i % 8) * 36, TOP + 100 + (i // 8) * 36, 32, 32)
            pygame.draw.rect(self.screen, T.BG2, rect)
            self._blit_sprite(sid, rect.inflate(-4, -4))
            if sid == self.map_sprite:
                pygame.draw.rect(self.screen, T.AMBER, rect, 2)

    def _picker_at(self, pos) -> int | None:
        start = self.map_page * 64
        for i in range(64):
            rect = pygame.Rect(580 + (i % 8) * 36, TOP + 100 + (i // 8) * 36, 32, 32)
            if rect.collidepoint(pos):
                return start + i
        return None

    def _map_cell_at(self, pos) -> tuple[int, int] | None:
        origin = (16, TOP + 32)
        cell = 24
        if pos[0] < origin[0] or pos[1] < origin[1]:
            return None
        sx = (pos[0] - origin[0]) // cell
        sy = (pos[1] - origin[1]) // cell
        if not (0 <= sx < 22 and 0 <= sy < 16):
            return None
        mx = self.map_ox + sx
        my = self.map_oy + sy
        if mx >= self.cart.map_w or my >= self.cart.map_h:
            return None
        return mx, my

    def _sprite_px(self, sid: int, x: int, y: int) -> int:
        cols = 16
        sx = (sid % cols) * 8 + x
        sy = (sid // cols) * 8 + y
        if not (0 <= sx < 128 and 0 <= sy < 128):
            return 0
        return self.cart.gfx[sy * 128 + sx]

    def _blit_sprite(self, sid: int, rect: pygame.Rect) -> None:
        surf = pygame.Surface((8, 8))
        px = pygame.PixelArray(surf)
        for y in range(8):
            for x in range(8):
                idx = self._sprite_px(sid, x, y)
                if idx == 0:
                    px[x, y] = (16, 20, 20)
                else:
                    px[x, y] = color_of(self.cart, idx)
        del px
        self.screen.blit(pygame.transform.scale(surf, (rect.width, rect.height)), rect.topleft)

    def _draw_snd(self) -> None:
        self._label(self.small, tr("snd-title"), T.AMBER, 20, TOP + 10)
        for i, inst in enumerate(self.cart.instruments):
            y = TOP + 40 + i * 28
            mark = T.AMBER if i == self.snd_ch else T.MUTED
            self._label(self.small, f"CH{i}  {inst.get('wave', 'square'):8}  {int(inst.get('volume', 0)):3d}", mark, 20, y)
        self._label(self.small, tr("snd-pat"), T.MUTED, 280, TOP + 10)
        header = "    " + "".join(f" CH{c} " for c in range(8))
        self._label(self.small, header, T.MUTED, 280, TOP + 36)
        for r in range(32):
            y = TOP + 56 + r * 20
            if y > H - BOT - 24:
                break
            bg = (28, 40, 36) if r == self.snd_row else None
            row = self.cart.pattern[r] if r < len(self.cart.pattern) else [""] * 8
            bits = [f"{r:02d}"]
            for c in range(8):
                note = row[c] if c < len(row) and row[c] else "---"
                bits.append(f"{note:4}")
            line = " ".join(bits)
            if bg and r == self.snd_row:
                pygame.draw.rect(self.screen, bg, (276, y - 2, 520, 18))
            color = T.PAPER if r == self.snd_row else T.INK
            self._label(self.small, line, color, 280, y)

    def _draw_sfx(self) -> None:
        self._label(self.small, tr("sfx-title"), T.AMBER, 20, TOP + 10)
        for i, notes in enumerate(self.cart.sfx[:8]):
            y = TOP + 48 + i * 36
            mark = T.AMBER if i == self.sfx_slot else T.INK
            preview = " ".join(notes[:8]) if notes else tr("sfx-empty")
            if len(notes) > 8:
                preview += " …"
            self._label(self.font, f"{i}  {preview}", mark, 24, y)
        self._label(self.small, tr("sfx-slot", n=self.sfx_slot, o=self.snd_oct), T.PAPER, 640, TOP + 48)
        notes = self.cart.sfx[self.sfx_slot] if self.cart.sfx else []
        for i in range(min(24, max(len(notes) + 1, 1))):
            y = TOP + 80 + i * 22
            if y > H - BOT - 28:
                break
            if i == self.sfx_i:
                pygame.draw.rect(self.screen, (28, 40, 36), (630, y - 2, 180, 20))
            if i < len(notes):
                label = notes[i]
            elif i == self.sfx_i:
                label = "···"
            else:
                continue
            color = T.AMBER if i == self.sfx_i else T.INK
            self._label(self.small, label, color, 640, y)
        self._label(self.small, tr("sfx-keys"), T.MUTED, 640, H - BOT - 64)
        self._label(self.small, tr("sfx-play"), T.MUTED, 640, H - BOT - 44)

    def _draw_help(self) -> None:
        panel = pygame.Rect(180, 80, 920, 620)
        pygame.draw.rect(self.screen, (10, 14, 13), panel)
        pygame.draw.rect(self.screen, T.AMBER, panel, 1)
        lines = help_lines()
        for i, line in enumerate(lines):
            color = T.AMBER if i == 0 else T.INK
            self._label(self.font if i == 0 else self.small, line, color, panel.x + 28, panel.y + 18 + i * 22)

    def _draw_files(self) -> None:
        panel = pygame.Rect(360, 140, 560, 480)
        pygame.draw.rect(self.screen, (10, 14, 13), panel)
        pygame.draw.rect(self.screen, T.TEAL, panel, 1)
        self._label(self.font, tr("carts"), T.AMBER, panel.x + 24, panel.y + 16)
        if not self.files:
            self._label(self.small, tr("carts-empty"), T.MUTED, panel.x + 24, panel.y + 60)
            return
        for i, path in enumerate(self.files[:16]):
            color = T.AMBER if i == self.file_i else T.INK
            self._label(self.font, path.stem, color, panel.x + 24, panel.y + 56 + i * 24)

    def _draw_prompt(self) -> None:
        y = H - BOT - 36
        pygame.draw.rect(self.screen, (8, 10, 10), (0, y, W, 36))
        self._label(self.font, "> " + self.prompt, T.AMBER, 16, y + 8)

    def _draw_debug(self) -> None:
        cpu = self.machine.cpu
        panel = pygame.Rect(760, TOP + 20, 500, 520)
        pygame.draw.rect(self.screen, (8, 12, 11), panel)
        pygame.draw.rect(self.screen, T.AMBER_DIM, panel, 1)
        from argonaut.machine.isa import disasm

        word = self.machine.mem.read_exec(cpu.pc) or 0
        lines = [
            f"PC {cpu.pc:08X}  {disasm(word)}",
            tr("dbg-cycles", n=cpu.cycles, late=self.machine.late, fault=self.machine.mem.fault),
        ]
        for i in range(15):
            name = "FP" if i == 12 else "SP" if i == 13 else "LR" if i == 14 else f"R{i}"
            lines.append(f"{name:3} {cpu.r[i]:08X}")
        lines.append(f"N{cpu.n} Z{cpu.z} C{cpu.c} V{cpu.v}")
        for i, line in enumerate(lines):
            self._label(self.small, line, T.PAPER, panel.x + 16, panel.y + 16 + i * 22)

    def _label(self, font, text, color, x, y) -> None:
        self.screen.blit(font.render(text, True, color), (x, y))

    def _logical_event(self, event):
        if self.scale == 1 or event.type not in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            return event
        x, y = event.pos
        data = dict(event.dict)
        data["pos"] = (x // self.scale, y // self.scale)
        return pygame.event.Event(event.type, data)

    def _present(self) -> None:
        if self.scale == 1:
            self.window.blit(self.screen, (0, 0))
        else:
            pygame.transform.scale(self.screen, self.window.get_size(), self.window)
        pygame.display.flip()

    def _note_error(self) -> None:
        import traceback

        text = traceback.format_exc()
        last = text.strip().splitlines()[-1] if text.strip() else tr("crash")
        self.status = last[:90]
        self.error_line = None
        if getattr(sys, "frozen", False):
            try:
                Path(sys.executable).resolve().parent.joinpath("argonaut.log").write_text(text, encoding="utf-8")
            except OSError:
                pass

    def loop(self) -> None:
        pygame.key.start_text_input()
        while self.alive:
            self.clock.tick(60)
            for event in pygame.event.get():
                try:
                    self.on_event(event)
                except Exception:
                    self._note_error()
            try:
                self.tick()
                self.draw()
            except Exception:
                self._note_error()
            self._present()
        pygame.quit()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    app = App()
    carts = [item for item in argv if not item.startswith("-")]
    if carts and "--selftest" not in argv:
        path = Path(carts[0])
        if path.suffix.lower() != ".alc":
            path = path.with_suffix(".alc")
        if not path.is_file():
            alt = cart_dir() / path.name
            if alt.is_file():
                path = alt
        if app.load_path(path):
            app.run_cart()
    if "--selftest" in argv:
        out = Path("/workspace/screenshots")
        out.mkdir(parents=True, exist_ok=True)
        app.draw()
        pygame.image.save(app.screen, str(out / "argonaut-code.png"))
        app.on_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (80, 140), "button": 1}))
        app.on_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (90, 160), "button": 1}))
        app.run_cart()
        for _ in range(12):
            app.tick()
        app.draw()
        pygame.image.save(app.screen, str(out / "argonaut-run.png"))
        app.mode = "gfx"
        app.draw()
        pygame.image.save(app.screen, str(out / "argonaut-gfx.png"))
        app.mode = "map"
        app.draw()
        pygame.image.save(app.screen, str(out / "argonaut-map.png"))
        app.mode = "sfx"
        app.draw()
        pygame.image.save(app.screen, str(out / "argonaut-sfx.png"))
        pygame.quit()
        print("selftest ok", app.status)
        return
    app.loop()
