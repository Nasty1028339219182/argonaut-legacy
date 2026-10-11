"""Ferry of Thoth — the cart that ships in the console."""

from __future__ import annotations

from argonaut.cart import Cart, blank_sound

PALETTE = [
    (1, 6, 8),
    (28, 18, 6),
    (6, 22, 18),
    (30, 28, 22),
    (3, 10, 16),
    (8, 18, 26),
    (31, 22, 8),
    (20, 8, 6),
    (31, 31, 31),
    (0, 0, 0),
    (31, 8, 10),
    (10, 26, 12),
    (16, 12, 8),
    (22, 14, 26),
    (14, 16, 20),
    (28, 18, 14),
]

# Sprite sheet is 128×128, 16 tiles across. Color 0 is transparent.
_CMAP = {str(i): i for i in range(10)}
_CMAP.update({"a": 10, "b": 11, "c": 12, "d": 13, "e": 14, "f": 15, ".": 0})

BOAT = [
    "................",
    "......111.......",
    ".....12221......",
    "....1222221.....",
    "...122222221....",
    "..1ffffffff1....",
    ".13ffffffff31...",
    "1333ffffff3331..",
    "13333333333331..",
    ".2222222222222..",
    "..666666666666..",
    "...6666666666...",
    "................",
    "................",
    "................",
    "................",
]

GEM = [
    "..66....",
    ".6886...",
    "688886..",
    "688886..",
    ".6886...",
    "..66....",
    "..11....",
    "........",
]

REED = [
    "..b.b...",
    ".b...b..",
    "..b.b...",
    "...b....",
    "...c....",
    "...c....",
    "..ccc...",
    ".ccccc..",
]

CODE = """# Паром Тота. Стрелки или WASD — ход, Esc — назад в редактор.
# Цвет 0 на спрайте прозрачный. pal(511, ...) железо отбросит.

px = 148
py = 118
score = 0
gx = 0
gy = 0
alive = 0

def _init():
    global gx, gy, alive
    # Палитра кассеты уже залита в AMATERASU. Это — живая запись слота.
    pal(6, 31, 22, 8)
    gx = [36, 96, 160, 220, 280]
    gy = [48, 96, 64, 140, 168]
    alive = [1, 1, 1, 1, 1]
    music(0)

def _update():
    global px, py, score
    if btn(0):
        px = px - 2
    if btn(1):
        px = px + 2
    if btn(2):
        py = py - 2
    if btn(3):
        py = py + 2
    if px < 4:
        px = 4
    if px > 300:
        px = 300
    if py < 32:
        py = 32
    if py > 210:
        py = 210
    i = 0
    while i < 5:
        if alive[i] == 1:
            dx = px + 8 - gx[i]
            dy = py + 8 - gy[i]
            if dx < 0:
                dx = 0 - dx
            if dy < 0:
                dy = 0 - dy
            if dx < 14:
                if dy < 14:
                    alive[i] = 0
                    score = score + 1
                    sfx(0)
        i = i + 1
    left = 0
    i = 0
    while i < 5:
        if alive[i] == 1:
            left = left + 1
        i = i + 1
    if left == 0:
        alive[0] = 1
        alive[1] = 1
        alive[2] = 1
        alive[3] = 1
        alive[4] = 1
        gx[0] = 24 + rnd(250)
        gx[1] = 24 + rnd(250)
        gx[2] = 24 + rnd(250)
        gx[3] = 24 + rnd(250)
        gx[4] = 24 + rnd(250)
        gy[0] = 40 + rnd(140)
        gy[1] = 40 + rnd(140)
        gy[2] = 40 + rnd(140)
        gy[3] = 40 + rnd(140)
        gy[4] = 40 + rnd(140)

def _draw():
    cls(4)
    y = frame() % 16
    while y < 240:
        rectfill(0, y, 320, 1, 5)
        y = y + 16
    rectfill(0, 0, 320, 26, 0)
    rectfill(0, 26, 320, 1, 1)
    text("FERRY OF THOTH", 8, 6, 1)
    text(score, 168, 6, 6)
    text(cycles(), 220, 6, 3)
    spr(33, 8, 200)
    spr(33, 300, 78)
    i = 0
    while i < 5:
        if alive[i] == 1:
            spr(32, gx[i], gy[i])
        i = i + 1
    spr(1, px, py, 2, 2)
    if score >= 5:
        text("THE RIVER REMEMBERS", 64, 214, 3)
"""


def _paint(gfx: bytearray, width: int, ox: int, oy: int, rows: list[str]) -> None:
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            gfx[(oy + y) * width + ox + x] = _CMAP.get(ch, 0)


def _pattern() -> list[list[str]]:
    lead = ["C4", "", "D#4", "", "G4", "", "A#4", "", "G4", "", "D#4", "", "C4", "", "G4", ""]
    bass = ["C3", "", "", "", "G2", "", "", "", "A#2", "", "", "", "D#3", "", "", ""]
    rows = []
    for i in range(32):
        row = [""] * 8
        row[0] = lead[i % len(lead)]
        row[1] = bass[i % len(bass)]
        rows.append(row)
    return rows


def make_demo() -> Cart:
    instruments, _, sfx = blank_sound()
    instruments[0] = {"wave": "square", "volume": 120}
    instruments[1] = {"wave": "triangle", "volume": 150}
    instruments[7] = {"wave": "square", "volume": 180}
    gfx = bytearray(128 * 128)
    _paint(gfx, 128, 8, 0, BOAT)  # sprite 1, 16×16
    _paint(gfx, 128, 0, 16, GEM)  # sprite 32
    _paint(gfx, 128, 8, 16, REED)  # sprite 33
    return Cart(
        name="ferry",
        code=CODE,
        palette=list(PALETTE),
        gfx=gfx,
        gfx_w=128,
        gfx_h=128,
        map_w=128,
        map_h=32,
        map_cells=[0] * (128 * 32),
        instruments=instruments,
        pattern=_pattern(),
        sfx=sfx,
        bpm=104,
    )
