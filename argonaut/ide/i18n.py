"""Editor language. English and Russian, switched inside the console.

Compiler and assembler errors are English keys. This module turns them
into a sentence in the language the editor is using right now.
"""

from __future__ import annotations

import locale
import os
import sys

from argonaut.paths import install_dir

_LANG = "en"

EN = {
    "at-line": "line {n}: {msg}",
    "ready": "THOTH 20.00 MHz ready.  Ctrl+R runs.",
    "build-fail": "build: {msg}",
    "running": "running.  Esc returns to the editor.  Arrows or WASD, Z/X buttons.",
    "stopped": "stopped.  Frame used {n} cycles.",
    "saved": "cart saved: {name}",
    "unreadable": "cannot read: {msg}",
    "loaded": "inserted cart {name}",
    "empty-cart": "blank cart",
    "no-cart": "no such cart",
    "commands": "commands: run, new, save name, load name",
    "lang-now": "Language: English.  F7 or the EN/RU chip switches.",
    "crash": "fault",
    "tab-code": "CODE",
    "tab-gfx": "SPRITES",
    "tab-map": "MAP",
    "tab-snd": "MUSIC",
    "tab-sfx": "SFX",
    "run-lamp": "RUN",
    "bot-code": "line {line}  col {col}",
    "bot-gfx": "color {c}  {tool}  G grid  F fill  1-8 flags",
    "bot-map": "tile {n}  arrows pan  [ ] sprite",
    "bot-snd": "oct {n}  Z-M notes  Tab wave  space play",
    "bot-sfx": "sfx {n}  oct {o}  Z-M note  space play",
    "bot-run": "colors {u}/511  palette clipped {c}  fault {f}",
    "tool-fill": "fill",
    "tool-brush": "brush",
    "run-a": "A left   D right",
    "run-zx": "Z button A   X button B",
    "log": "LOG",
    "gfx-pal": "PALETTE  [ ] page",
    "gfx-rgb": "R  G  B   click a channel cell",
    "gfx-slot": "slot {idx}   {r:02d} {g:02d} {b:02d}",
    "gfx-zero": "0 is transparent on a sprite",
    "gfx-pick": "right click picks a color",
    "gfx-flags": "flags of sprite {n}   bits 0-7, keys 1-8",
    "gfx-undo": "Ctrl+Z undo   Ctrl+Y redo",
    "map-title": "MAP  128x32 tiles of 8px.  0 is empty.",
    "map-picked": "tile {n}",
    "map-range": "sprites {a}-{b}",
    "map-page": ", . page",
    "snd-title": "STRIBOG  8 channels   space plays the pattern",
    "snd-pat": "PATTERN 32x8    O writes OFF    empty holds the note",
    "sfx-title": "SFX  sfx(0) … sfx(7)   channel 7   space plays the slot",
    "sfx-empty": "empty",
    "sfx-slot": "slot {n}    oct {o}",
    "sfx-keys": "Z-M writes a note   O is OFF",
    "sfx-play": "in a game: sfx(number)",
    "carts": "CARTS",
    "carts-empty": "folder is empty — Ctrl+S saves this cart",
    "dbg-cycles": "cycles {n}  LATE {late}  fault {fault}",
    "expected-token": "expected {kind}, found {got}",
    "extra-indent": "unexpected indent",
    "need-indent": "indent required; write pass for an empty block",
    "bad-assign": "the left side of = must be a name or a list item",
    "range-args": "range takes at most three arguments",
    "max-args": "at most 6 arguments",
    "call-name": "only a function name can be called",
    "expected-expr": "expected an expression, found {got}",
    "indent-spaces": "indent with spaces only",
    "bad-indent": "indent does not match an outer block",
    "no-float-div": "TPython has no fractions: use //",
    "empty-hex": "empty hexadecimal number",
    "no-float": "TPython has no fractions: use integers",
    "bad-escape": "unknown escape \\{esc}",
    "unclosed-string": "string is not closed",
    "bad-char": "unexpected character {ch}",
    "dup-func": "function {name} is already defined",
    "nested-func": "nested functions are not supported yet",
    "temps": "internal error: out of temporary cells",
    "break-outside": "break is outside a loop",
    "continue-outside": "continue is outside a loop",
    "uncompiled": "this construct is not compiled yet",
    "bad-store": "that assignment is not allowed",
    "bad-expr": "could not compile the expression",
    "no-op": "no operator {op}",
    "arity": "{name}() expects {need} args, got {got}",
    "bad-argc": "{name}() has the wrong number of arguments",
    "not-enough-args": "{name}() is missing arguments",
    "unknown-name": "unknown name {name}",
    "func-as-value": "{name} is a function and cannot be read as a number",
    "align-not-word": "alignment is not a multiple of a word",
    "no-label": "missing label {name}",
    "bl-far": "BL is out of range: {name}",
    "branch-far": "branch is out of range: {name}",
    "not-reg": "not a register: {token}",
    "asm-escape": "unknown escape \\{esc}",
    "equ-syntax": "expected .equ NAME VALUE",
    "dup-label": "duplicate label {name}",
    "empty-label": "empty label",
    "data-align": "data is not word-aligned — add .align 4",
    "size-mismatch": "instruction size does not match its encoding",
    "tail-align": "trailing data is not aligned",
    "not-number": "not a number or a label: {token}",
    "org-unsupported": ".org inside a program is not supported",
    "align-pow2": ".align expects a power of two",
    "dw-number": ".dw only accepts numbers for now",
    "db-byte": ".db expects a byte",
    "expected-string": "expected a string",
    "unknown-directive": "unknown directive .{name}",
    "li-syntax": "LI rd, value",
    "rd-syntax": "{op} rd",
    "neg-syntax": "NEG rd, rs",
    "alu-syntax": "{op} rd, rs, rt",
    "imm-syntax": "{op} rd, rs, imm",
    "ldr-form": "use LDR rd, rs, offset",
    "imm-number": "the offset must be a number",
    "shift-range": "shift must be 0..31",
    "imm-range": "immediate must be 0..65535",
    "off16": "offset does not fit in 16 bits",
    "lui-syntax": "LUI rd, imm",
    "lui-number": "LUI expects a 16-bit number",
    "lui-range": "LUI expects 0..65535",
    "branch-label": "{op} label",
    "jr-syntax": "JR rs",
    "jalr-syntax": "JALR rd, rs",
    "ldm-syntax": "{op} rs!, {{regs}}",
    "reglist": "register list must be in braces",
    "unknown-op": "unknown instruction {op}",
}

RU = {
    "at-line": "строка {n}: {msg}",
    "ready": "THOTH 20.00 МГц готов.  Ctrl+R — пуск.",
    "build-fail": "сборка: {msg}",
    "running": "пуск.  Esc — в редактор.  Стрелки или WASD, Z/X — кнопки.",
    "stopped": "стоп.  Кадр съел {n} тактов.",
    "saved": "кассета записана: {name}",
    "unreadable": "не читается: {msg}",
    "loaded": "вставлена кассета {name}",
    "empty-cart": "пустая кассета",
    "no-cart": "нет такой кассеты",
    "commands": "команды: run, new, save имя, load имя",
    "lang-now": "Язык: русский.  F7 или метка EN/RU переключает.",
    "crash": "сбой",
    "tab-code": "КОД",
    "tab-gfx": "СПРАЙТЫ",
    "tab-map": "КАРТА",
    "tab-snd": "МУЗЫКА",
    "tab-sfx": "ЭФФЕКТЫ",
    "run-lamp": "ПУСК",
    "bot-code": "стр {line}  стлб {col}",
    "bot-gfx": "цвет {c}  {tool}  G сетка  F заливка  1–8 флаги",
    "bot-map": "тайл {n}  стрелки — камера  [ ] спрайт",
    "bot-snd": "окт {n}  Z–M ноты  Tab волна  пробел слушать",
    "bot-sfx": "sfx {n}  окт {o}  Z–M нота  пробел слушать",
    "bot-run": "цвета {u}/511  палитра отсечено {c}  fault {f}",
    "tool-fill": "заливка",
    "tool-brush": "кисть",
    "run-a": "A влево   D вправо",
    "run-zx": "Z кнопка A   X кнопка B",
    "log": "ЖУРНАЛ",
    "gfx-pal": "ПАЛИТРА  [ ] страница",
    "gfx-rgb": "R  G  B   клик по клетке канала",
    "gfx-slot": "слот {idx}   {r:02d} {g:02d} {b:02d}",
    "gfx-zero": "0 прозрачен на спрайте",
    "gfx-pick": "ПКМ — пипетка",
    "gfx-flags": "флаги спрайта {n}   биты 0–7, клавиши 1–8",
    "gfx-undo": "Ctrl+Z отмена   Ctrl+Y повтор",
    "map-title": "КАРТА  128×32 тайлов по 8px.  0 — пусто.",
    "map-picked": "выбран тайл {n}",
    "map-range": "спрайты {a}–{b}",
    "map-page": ", . страница",
    "snd-title": "STRIBOG  8 каналов   пробел — слушать паттерн",
    "snd-pat": "ПАТТЕРН 32×8    O пишет OFF    пусто — держать ноту",
    "sfx-title": "ЭФФЕКТЫ  sfx(0) … sfx(7)   канал 7   пробел — слушать слот",
    "sfx-empty": "пусто",
    "sfx-slot": "слот {n}    окт {o}",
    "sfx-keys": "Z–M пишет ноту   O — пауза OFF",
    "sfx-play": "в игре: sfx(номер)",
    "carts": "КАССЕТЫ",
    "carts-empty": "папка пуста — Ctrl+S сохранит текущую",
    "dbg-cycles": "такты {n}  LATE {late}  fault {fault}",
    "expected-token": "ожидалось {kind}, а тут {got}",
    "extra-indent": "лишний отступ",
    "need-indent": "нужен отступ; пустой блок пишите как pass",
    "bad-assign": "слева от = нужно имя или элемент списка",
    "range-args": "у range максимум три аргумента",
    "max-args": "не больше 6 аргументов",
    "call-name": "вызов только по имени функции",
    "expected-expr": "ожидалось выражение, а тут {got}",
    "indent-spaces": "отступ только пробелами",
    "bad-indent": "сбитый отступ",
    "no-float-div": "в TPython нет дробей: используйте //",
    "empty-hex": "пустое шестнадцатеричное число",
    "no-float": "в TPython нет дробей: используйте целые",
    "bad-escape": "неизвестное \\{esc}",
    "unclosed-string": "строка не закрыта",
    "bad-char": "непонятный символ {ch}",
    "dup-func": "функция {name} уже есть",
    "nested-func": "вложенные функции пока нельзя",
    "temps": "внутренний сбой: не хватило временных ячеек",
    "break-outside": "break не внутри цикла",
    "continue-outside": "continue не внутри цикла",
    "uncompiled": "эта конструкция пока не собрана",
    "bad-store": "так присваивать нельзя",
    "bad-expr": "не собралось выражение",
    "no-op": "нет оператора {op}",
    "arity": "{name}() ждёт {need} арг., а получила {got}",
    "bad-argc": "{name}() — неверное число аргументов",
    "not-enough-args": "{name}() не хватает аргументов",
    "unknown-name": "неизвестное имя {name}",
    "func-as-value": "{name} — функция, её нельзя читать как число",
    "align-not-word": "выравнивание не кратно слову",
    "no-label": "нет метки {name}",
    "bl-far": "BL слишком далеко: {name}",
    "branch-far": "ветвление слишком далеко: {name}",
    "not-reg": "не регистр: {token}",
    "asm-escape": "неизвестное экранирование \\{esc}",
    "equ-syntax": "ожидалось .equ ИМЯ ЗНАЧЕНИЕ",
    "dup-label": "повтор метки {name}",
    "empty-label": "пустая метка",
    "data-align": "данные не выровнены на слово — поставьте .align 4",
    "size-mismatch": "размер команды разъехался с кодированием",
    "tail-align": "хвост данных не выровнен",
    "not-number": "не число и не метка: {token}",
    "org-unsupported": ".org внутри программы не поддерживается",
    "align-pow2": ".align ждёт степень двойки",
    "dw-number": ".dw пока только для чисел",
    "db-byte": ".db ждёт байт",
    "expected-string": "ожидалась строка",
    "unknown-directive": "неизвестная директива .{name}",
    "li-syntax": "LI rd, значение",
    "rd-syntax": "{op} rd",
    "neg-syntax": "NEG rd, rs",
    "alu-syntax": "{op} rd, rs, rt",
    "imm-syntax": "{op} rd, rs, imm",
    "ldr-form": "используйте LDR rd, rs, смещение",
    "imm-number": "смещение должно быть числом",
    "shift-range": "сдвиг 0..31",
    "imm-range": "непосредственное 0..65535",
    "off16": "смещение не влезает в 16 бит",
    "lui-syntax": "LUI rd, imm",
    "lui-number": "LUI ждёт 16-битное число",
    "lui-range": "LUI ждёт 0..65535",
    "branch-label": "{op} метка",
    "jr-syntax": "JR rs",
    "jalr-syntax": "JALR rd, rs",
    "ldm-syntax": "{op} rs!, {{regs}}",
    "reglist": "список регистров в фигурных скобках",
    "unknown-op": "неизвестная команда {op}",
}


def lang() -> str:
    return _LANG


def _path():
    return install_dir() / "language.txt"


def _system_lang() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            primary = int(ctypes.windll.kernel32.GetUserDefaultUILanguage()) & 0x3FF
            if primary == 0x19:
                return "ru"
        except Exception:
            pass
    parts: list[str] = []
    for reader in (locale.getlocale, locale.getdefaultlocale):
        try:
            got = reader()
        except Exception:
            got = None
        if got:
            parts.extend(str(item) for item in got if item)
    parts.append(os.environ.get("LANG", ""))
    parts.append(os.environ.get("LC_ALL", ""))
    blob = " ".join(parts).lower()
    if blob.startswith("ru") or "_ru" in blob or "ru_" in blob or blob.startswith("russian"):
        return "ru"
    return "en"


def _load() -> None:
    global _LANG
    path = _path()
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip().lower()
        if text in ("en", "ru"):
            _LANG = text
            return
    _LANG = _system_lang()


def set_lang(code: str, persist: bool = True) -> None:
    global _LANG
    _LANG = "ru" if str(code).lower().startswith("ru") else "en"
    if not persist:
        return
    try:
        _path().write_text(_LANG + "\n", encoding="utf-8")
    except OSError:
        pass


def toggle_lang() -> str:
    set_lang("en" if _LANG == "ru" else "ru")
    return _LANG


def tr(key: str, **fmt) -> str:
    table = RU if _LANG == "ru" else EN
    text = table.get(key) or EN.get(key) or key
    if not fmt:
        return text
    try:
        return text.format(**fmt)
    except (IndexError, KeyError, ValueError):
        return text


def explain(exc: BaseException) -> str:
    key = getattr(exc, "key", None)
    fmt = getattr(exc, "fmt", None) or {}
    if not isinstance(fmt, dict):
        fmt = {}
    text = tr(str(key), **fmt) if key else str(exc)
    line = getattr(exc, "line", None)
    if line:
        return tr("at-line", n=line, msg=text)
    return text


def blank_source() -> str:
    if _LANG == "ru":
        head = "# Новая кассета. Ctrl+R — пуск, Esc — стоп, F1 — справка, F7 — язык."
        title = "АРГОНАВТ"
    else:
        head = "# New cart. Ctrl+R run, Esc stop, F1 help, F7 language."
        title = "ARGONAUT"
    return f"""{head}

def _init():
    pass

def _update():
    pass

def _draw():
    cls(0)
    text("{title}", 96, 100, 1)
"""


def help_lines() -> list[str]:
    if _LANG == "ru":
        return [
            "ARGONAUT LEGACY",
            "",
            "Ctrl+R пуск    Esc стоп    Ctrl+S запись    Ctrl+O кассеты",
            "Ctrl+N новая   Ctrl+P команда (save / load / run / new)",
            "F2 код  F3 спрайты  F4 карта  F5 музыка  F6 эффекты  F7 язык",
            "Ctrl+Q выход.  Всё пишется здесь, снаружи редактора нет.",
            "",
            "В игре: стрелки или WASD.  Z — кнопка A,  X — кнопка B.",
            "A влево, D вправо.  Кадр — 333333 такта, каждый третий 333334.",
            "Опоздание кадра — лампа LATE.  Конвейера и луча развёртки нет.",
            "",
            "TPython: отступы, целые 32 бита, списки чисел. Дробей нет, только //.",
            "line circ circfill clip fget fset — вместе со старым рисунком.",
            "cls pset spr rect rectfill text pal map camera btn btnp",
            "music sfx print frame cycles rnd peek poke",
            "",
            "Первый cls кадра бесплатный. Дальше каждый осмотренный пиксель",
            "блиттера стоит 1 такт, в том числе прозрачный пиксель спрайта.",
            "Потолок записей на кадр — 76800. SRAM без ожидания, данные ROM +1,",
            "экран, палитра и порты +2. Выборка команды повторно не тарифицируется.",
            "Строка паттерна — 48 тактов, взятие ноты — 8. Микшер на стороне хоста.",
            "",
            "Флаги спрайта: 8 бит, клавиши 1–8 в редакторе спрайтов. Ctrl+Z отмена.",
            "Запуск сразу в игру: argonaut cart.alc.  Esc возвращает в редактор.",
            "Кассета — файл .alc в папке carts.  Цвет 0 на спрайте прозрачный.",
        ]
    return [
        "ARGONAUT LEGACY",
        "",
        "Ctrl+R run    Esc stop    Ctrl+S save    Ctrl+O carts",
        "Ctrl+N new    Ctrl+P command (save / load / run / new)",
        "F2 code  F3 sprites  F4 map  F5 music  F6 sfx  F7 language",
        "Ctrl+Q quits.  The cart is edited in this window, nowhere else.",
        "",
        "In a game: arrows or WASD.  Z is button A,  X is button B.",
        "A is left, D is right.  A frame is 333333 cycles, every third is 333334.",
        "A late frame lights LATE.  There is no pipeline and no scanline beam.",
        "",
        "TPython: indentation, signed 32-bit integers, lists of numbers. No floats.",
        "line circ circfill clip fget fset sit beside the older draw calls.",
        "cls pset spr rect rectfill text pal map camera btn btnp",
        "music sfx print frame cycles rnd peek poke",
        "",
        "The first cls of a frame is free. After that every pixel the blitter",
        "inspects costs 1 cycle, including a transparent sprite pixel.",
        "The write cap is still 76800 per frame. SRAM waits 0, ROM data waits +1,",
        "framebuffer, palette and ports wait +2. Fetch is not charged again.",
        "A pattern row costs 48 cycles, a note-on costs 8. The mixer stays on the host.",
        "",
        "Sprite flags: 8 bits, keys 1-8 in the sprite editor. Ctrl+Z undoes a stroke.",
        "Launch straight into play: argonaut cart.alc.  Esc returns to the editor.",
        "A cart is an .alc file in the carts folder.  Color 0 on a sprite is clear.",
    ]


_load()
