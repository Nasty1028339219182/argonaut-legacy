"""Code editor inside the console. Indentation is part of the language."""

from __future__ import annotations

import pygame

from argonaut.ide import theme as T
from argonaut.tpython.compiler import BUILTIN_FN

KEYWORDS = {
    "def",
    "return",
    "if",
    "elif",
    "else",
    "while",
    "for",
    "in",
    "range",
    "global",
    "pass",
    "and",
    "or",
    "not",
    "break",
    "continue",
}


class CodeEditor:
    def __init__(self, source: str) -> None:
        self.set_source(source)
        self.undo: list[tuple] = []
        self.redo: list[tuple] = []
        self.blink = 0

    def set_source(self, source: str) -> None:
        self.lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not self.lines:
            self.lines = [""]
        self.cx = 0
        self.cy = 0
        self.anchor: tuple[int, int] | None = None
        self.scroll = 0
        self.hscroll = 0

    def source(self) -> str:
        return "\n".join(self.lines)

    def snapshot(self) -> None:
        state = (self.lines[:], self.cx, self.cy, self.anchor)
        if self.undo and self.undo[-1][0] == state[0] and self.undo[-1][1] == self.cx:
            return
        self.undo.append(state)
        if len(self.undo) > 80:
            self.undo.pop(0)
        self.redo.clear()

    def undo_once(self) -> None:
        if not self.undo:
            return
        self.redo.append((self.lines[:], self.cx, self.cy, self.anchor))
        self.lines, self.cx, self.cy, self.anchor = self.undo.pop()

    def redo_once(self) -> None:
        if not self.redo:
            return
        self.undo.append((self.lines[:], self.cx, self.cy, self.anchor))
        self.lines, self.cx, self.cy, self.anchor = self.redo.pop()

    def _clamp(self) -> None:
        self.cy = max(0, min(len(self.lines) - 1, self.cy))
        self.cx = max(0, min(len(self.lines[self.cy]), self.cx))

    def selection(self):
        if self.anchor is None:
            return None
        a = self.anchor
        b = (self.cy, self.cx)
        if a == b:
            return None
        if a > b:
            a, b = b, a
        return a, b

    def selected_text(self) -> str | None:
        rng = self.selection()
        if not rng:
            return None
        (y1, x1), (y2, x2) = rng
        if y1 == y2:
            return self.lines[y1][x1:x2]
        parts = [self.lines[y1][x1:]]
        parts.extend(self.lines[y1 + 1 : y2])
        parts.append(self.lines[y2][:x2])
        return "\n".join(parts)

    def delete_selection(self) -> bool:
        rng = self.selection()
        if not rng:
            return False
        (y1, x1), (y2, x2) = rng
        if y1 == y2:
            self.lines[y1] = self.lines[y1][:x1] + self.lines[y1][x2:]
        else:
            self.lines[y1] = self.lines[y1][:x1] + self.lines[y2][x2:]
            del self.lines[y1 + 1 : y2 + 1]
        self.cy, self.cx = y1, x1
        self.anchor = None
        return True

    def insert(self, text: str) -> None:
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        if not text:
            return
        self.snapshot()
        self.delete_selection()
        parts = text.split("\n")
        line = self.lines[self.cy]
        if len(parts) == 1:
            self.lines[self.cy] = line[: self.cx] + parts[0] + line[self.cx :]
            self.cx += len(parts[0])
        else:
            head = line[: self.cx] + parts[0]
            tail = parts[-1] + line[self.cx :]
            self.lines[self.cy] = head
            self.lines[self.cy + 1 : self.cy + 1] = parts[1:-1] + [tail]
            self.cy += len(parts) - 1
            self.cx = len(parts[-1])
        self.anchor = None

    def enter(self) -> None:
        self.snapshot()
        self.delete_selection()
        line = self.lines[self.cy]
        left, right = line[: self.cx], line[self.cx :]
        base = len(left) - len(left.lstrip(" "))
        extra = 0
        if line.rstrip().endswith(":") and self.cx >= len(line.rstrip()):
            extra = 4
            base = len(line) - len(line.lstrip(" "))
        pad = " " * (base + extra)
        self.lines[self.cy] = left
        self.lines.insert(self.cy + 1, pad + right)
        self.cy += 1
        self.cx = len(pad)
        self.anchor = None

    def backspace(self) -> None:
        self.snapshot()
        if self.delete_selection():
            return
        if self.cx > 0:
            line = self.lines[self.cy]
            self.lines[self.cy] = line[: self.cx - 1] + line[self.cx :]
            self.cx -= 1
            return
        if self.cy == 0:
            return
        prev = self.lines[self.cy - 1]
        self.cx = len(prev)
        self.lines[self.cy - 1] = prev + self.lines[self.cy]
        del self.lines[self.cy]
        self.cy -= 1

    def delete(self) -> None:
        self.snapshot()
        if self.delete_selection():
            return
        line = self.lines[self.cy]
        if self.cx < len(line):
            self.lines[self.cy] = line[: self.cx] + line[self.cx + 1 :]
            return
        if self.cy >= len(self.lines) - 1:
            return
        self.lines[self.cy] = line + self.lines[self.cy + 1]
        del self.lines[self.cy + 1]

    def tab(self, shift: bool) -> None:
        self.snapshot()
        if shift:
            line = self.lines[self.cy]
            if line.startswith("    "):
                self.lines[self.cy] = line[4:]
                self.cx = max(0, self.cx - 4)
            return
        self.insert("    ")

    def move(self, dx: int, dy: int, shift: bool) -> None:
        if shift and self.anchor is None:
            self.anchor = (self.cy, self.cx)
        if not shift:
            self.anchor = None
        if dy:
            self.cy += dy
            self._clamp()
        if dx:
            self.cx += dx
            if self.cx < 0 and self.cy > 0:
                self.cy -= 1
                self.cx = len(self.lines[self.cy])
            elif self.cx > len(self.lines[self.cy]) and self.cy < len(self.lines) - 1:
                self.cy += 1
                self.cx = 0
        self._clamp()

    def word_move(self, direction: int, shift: bool) -> None:
        if shift and self.anchor is None:
            self.anchor = (self.cy, self.cx)
        if not shift:
            self.anchor = None
        line = self.lines[self.cy]
        if direction < 0:
            i = max(0, self.cx - 1)
            while i > 0 and line[i - 1].isalnum():
                i -= 1
            self.cx = i
        else:
            i = self.cx
            while i < len(line) and line[i].isalnum():
                i += 1
            while i < len(line) and line[i] == " ":
                i += 1
            self.cx = i

    def select_all(self) -> None:
        self.anchor = (0, 0)
        self.cy = len(self.lines) - 1
        self.cx = len(self.lines[self.cy])

    def reveal(self, rows: int) -> None:
        if self.cy < self.scroll:
            self.scroll = self.cy
        if self.cy >= self.scroll + rows:
            self.scroll = self.cy - rows + 1
        self.scroll = max(0, self.scroll)

    def click(self, col: int, row: int, shift: bool) -> None:
        if shift and self.anchor is None:
            self.anchor = (self.cy, self.cx)
        if not shift:
            self.anchor = (row, col)
        self.cy, self.cx = row, col
        self._clamp()

    def on_keydown(self, event, clip_get, clip_set) -> bool:
        key = event.key
        mod = event.mod
        ctrl = bool(mod & pygame.KMOD_CTRL)
        shift = bool(mod & pygame.KMOD_SHIFT)
        if ctrl and key == pygame.K_a:
            self.select_all()
            return True
        if ctrl and key == pygame.K_c:
            text = self.selected_text()
            if text is not None:
                clip_set(text)
            return True
        if ctrl and key == pygame.K_x:
            text = self.selected_text()
            if text is not None:
                self.snapshot()
                clip_set(text)
                self.delete_selection()
            return True
        if ctrl and key == pygame.K_v:
            self.insert(clip_get())
            return True
        if ctrl and key == pygame.K_z:
            self.undo_once()
            return True
        if ctrl and key == pygame.K_y:
            self.redo_once()
            return True
        if ctrl and key == pygame.K_LEFT:
            self.word_move(-1, shift)
            return True
        if ctrl and key == pygame.K_RIGHT:
            self.word_move(1, shift)
            return True
        if key == pygame.K_LEFT:
            self.move(-1, 0, shift)
            return True
        if key == pygame.K_RIGHT:
            self.move(1, 0, shift)
            return True
        if key == pygame.K_UP:
            self.move(0, -1, shift)
            return True
        if key == pygame.K_DOWN:
            self.move(0, 1, shift)
            return True
        if key == pygame.K_HOME:
            if shift and self.anchor is None:
                self.anchor = (self.cy, self.cx)
            if not shift:
                self.anchor = None
            self.cx = 0
            return True
        if key == pygame.K_END:
            if shift and self.anchor is None:
                self.anchor = (self.cy, self.cx)
            if not shift:
                self.anchor = None
            self.cx = len(self.lines[self.cy])
            return True
        if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            self.move(0, -20 if key == pygame.K_PAGEUP else 20, shift)
            return True
        if key == pygame.K_BACKSPACE:
            self.backspace()
            return True
        if key == pygame.K_DELETE:
            self.delete()
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.enter()
            return True
        if key == pygame.K_TAB:
            self.tab(shift)
            return True
        return False

    def draw(self, surf: pygame.Surface, rect: pygame.Rect, font: pygame.font.Font, error_line: int | None) -> None:
        self.blink += 1
        char_w, char_h = font.size("M")
        gutter = 54
        rows = max(1, rect.height // char_h)
        self.reveal(rows)
        pygame.draw.rect(surf, T.BG, rect)
        g = pygame.Rect(rect.x, rect.y, gutter, rect.height)
        pygame.draw.rect(surf, T.GUTTER, g)
        rng = self.selection()
        for i in range(rows):
            ln = self.scroll + i
            if ln >= len(self.lines):
                break
            y = rect.y + i * char_h
            if error_line and ln + 1 == error_line:
                pygame.draw.rect(surf, (48, 24, 22), (rect.x + gutter, y, rect.width - gutter, char_h))
            if ln == self.cy:
                pygame.draw.rect(surf, (24, 34, 32), (rect.x + gutter, y, rect.width - gutter, char_h))
            num = font.render(str(ln + 1), True, T.AMBER if ln == self.cy else T.MUTED)
            surf.blit(num, (rect.x + gutter - 8 - num.get_width(), y))
            self._draw_line(surf, font, self.lines[ln], rect.x + gutter + 8, y, char_w, ln, rng)
        if self.blink % 60 < 36:
            cx = rect.x + gutter + 8 + self.cx * char_w
            cy = rect.y + (self.cy - self.scroll) * char_h
            if rect.y <= cy < rect.bottom:
                pygame.draw.rect(surf, T.AMBER, (cx, cy + 2, 2, char_h - 4))

    def _draw_line(self, surf, font, text, x, y, char_w, ln, rng) -> None:
        colors = _colorize(text)
        col = 0
        for piece, color in colors:
            if rng:
                (y1, x1), (y2, x2) = rng
                for i, ch in enumerate(piece):
                    absolute = col + i
                    selected = _in_sel(ln, absolute, y1, x1, y2, x2)
                    if selected:
                        pygame.draw.rect(surf, T.SELECT, (x + absolute * char_w, y, char_w, font.get_height()))
            img = font.render(piece, True, color)
            surf.blit(img, (x + col * char_w, y))
            col += len(piece)

    def pos_at(self, mx, my, rect, font) -> tuple[int, int]:
        char_w, char_h = font.size("M")
        gutter = 54
        col = round((mx - (rect.x + gutter + 8)) / char_w)
        row = self.scroll + (my - rect.y) // char_h
        row = max(0, min(len(self.lines) - 1, row))
        col = max(0, min(len(self.lines[row]), col))
        return row, col


def _in_sel(ln, col, y1, x1, y2, x2) -> bool:
    if ln < y1 or ln > y2:
        return False
    if y1 == y2:
        return x1 <= col < x2
    if ln == y1:
        return col >= x1
    if ln == y2:
        return col < x2
    return True


def _colorize(text: str) -> list[tuple[str, tuple]]:
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "#":
            out.append((text[i:], T.CMT))
            break
        if text[i] in ("'", '"'):
            q = text[i]
            j = i + 1
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if text[j] == q:
                    j += 1
                    break
                j += 1
            out.append((text[i:j], T.STRC))
            i = j
            continue
        if text[i].isdigit():
            j = i + 1
            while j < n and (text[j].isdigit() or text[j] in "xXabcdefABCDEF"):
                j += 1
            out.append((text[i:j], T.NUM))
            i = j
            continue
        if text[i].isalpha() or text[i] == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            if word in KEYWORDS:
                color = T.KW
            elif word in BUILTIN_FN:
                color = T.BI
            else:
                color = T.INK
            out.append((word, color))
            i = j
            continue
        j = i + 1
        while j < n and not (text[j].isalnum() or text[j] in "_#'\""):
            j += 1
        out.append((text[i:j], T.PAPER))
        i = j
    return out or [("", T.INK)]
