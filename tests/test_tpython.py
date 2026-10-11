"""TPython compiled onto THOTH and executed for a frame."""

from __future__ import annotations

import unittest

from argonaut.cart import Cart, blank_sound
from argonaut.hw import FAULT_DIV0, PAL_BASE
from argonaut.machine.machine import Machine
from argonaut.tpython.errors import TPyError


def cart_with(code: str, palette=None) -> Cart:
    instruments, pattern, sfx = blank_sound()
    return Cart(
        name="test",
        code=code,
        palette=palette or [(0, 0, 0), (31, 31, 31), (0, 31, 10), (31, 20, 0)],
        gfx=bytearray(128 * 128),
        map_cells=[0] * (128 * 32),
        instruments=instruments,
        pattern=pattern,
        sfx=sfx,
    )


def run_code(code: str, frames: int = 1, pad: int = 0, palette=None) -> Machine:
    machine = Machine()
    machine.load(cart_with(code, palette))
    for _ in range(frames):
        machine.frame(pad)
    return machine


class TPythonTests(unittest.TestCase):
    def test_cls_and_pset(self):
        m = run_code(
            """
def _draw():
    cls(2)
    pset(3, 4, 1)
"""
        )
        self.assertEqual(m.read_pixel(0, 0), 2)
        self.assertEqual(m.read_pixel(3, 4), 1)
        self.assertEqual(m.mem.fault, 0)
        self.assertFalse(m.late)

    def test_arithmetic_and_return(self):
        m = run_code(
            """
def fact(n):
    if n < 2:
        return 1
    return n * fact(n - 1)

def _draw():
    cls(0)
    text(fact(6), 0, 0, 1)
"""
        )
        # 720 drawn at 0,0 as glyphs. First glyph of '7' is not empty.
        self.assertEqual(m.mem.fault, 0)
        self.assertGreater(sum(m.mem.fb), 0)

    def test_floor_div_and_mod(self):
        m = run_code(
            """
def _draw():
    cls(0)
    print((-5) // 2)
    print((-5) % 2)
    print(7 // 2)
"""
        )
        self.assertEqual(m.mem.fault, 0)
        self.assertEqual(m.log_lines, ["-3", "1", "3"])

    def test_globals_button_and_list(self):
        m = run_code(
            """
px = 10
gx = 0

def _init():
    global gx
    gx = [4, 5, 6]

def _update():
    global px
    if btn(0):
        px = px - 1
    if btn(1):
        px = px + 3

def _draw():
    cls(0)
    pset(px, 2, 1)
    pset(gx[1], 3, 1)
""",
            frames=2,
            pad=0b0010,  # right
        )
        self.assertEqual(m.read_pixel(16, 2), 1)  # 10+3+3
        self.assertEqual(m.read_pixel(5, 3), 1)
        self.assertEqual(m.mem.fault, 0)

    def test_for_and_print(self):
        m = run_code(
            """
def _draw():
    cls(0)
    s = 0
    for i in range(1, 4):
        s = s + i
    print(s)
    print("ok")
"""
        )
        self.assertEqual(m.log_lines[0], "6")
        self.assertEqual(m.log_lines[1], "ok")

    def test_palette_clip_from_code(self):
        m = run_code(
            """
def _init():
    pal(510, 31, 0, 0)
    pal(511, 0, 31, 0)
"""
        )
        self.assertEqual(m.mem.pal[510], (31 << 10))
        self.assertGreaterEqual(m.mem.pal_clip, 1)
        # slot 511 does not exist
        self.assertEqual(len(m.mem.pal), 511)

    def test_div0_sets_fault(self):
        m = run_code(
            """
def _draw():
    cls(0)
    text(1 // 0, 0, 0, 1)
"""
        )
        self.assertEqual(m.mem.fault, FAULT_DIV0)

    def test_string_concat(self):
        m = run_code(
            """
def _draw():
    cls(0)
    text("A" + "B", 0, 0, 1)
"""
        )
        self.assertEqual(m.mem.fault, 0)
        # 'A' and 'B' both have ink
        self.assertGreater(m.read_pixel(2, 1) + m.read_pixel(10, 1), 0)

    def test_demo_cart_runs(self):
        from argonaut.demo import make_demo

        machine = Machine()
        machine.load(make_demo())
        for _ in range(8):
            machine.frame(0b0010)  # right
        self.assertEqual(machine.mem.fault, 0)
        self.assertEqual(machine.late, 0)
        self.assertLess(machine.cpu.cycles, 333333)
        # 16×16 boat starts at (164, 118) after eight steps right. Gold hull is row 10.
        self.assertTrue(any(machine.read_pixel(x, 128) == 6 for x in range(164, 180)))
        with self.assertRaises(TPyError) as caught:
            run_code(
                """
def _draw():
    cls(
"""
            )
        self.assertGreaterEqual(caught.exception.line, 1)

    def test_sprite_skips_transparent_zero(self):
        instruments, pattern, sfx = blank_sound()
        gfx = bytearray(128 * 128)
        gfx[0] = 0
        gfx[1] = 3
        cart = cart_with(
            """
def _draw():
    cls(1)
    spr(0, 0, 0)
""",
        )
        cart.gfx = gfx
        cart.instruments = instruments
        m = Machine()
        m.load(cart)
        m.frame()
        self.assertEqual(m.read_pixel(0, 0), 1)  # transparent, cls color remains
        self.assertEqual(m.read_pixel(1, 0), 3)

    def test_late_when_budget_blown(self):
        m = run_code(
            """
def _update():
    while 1:
        pass
"""
        )
        self.assertEqual(m.late, 1)


if __name__ == "__main__":
    unittest.main()
