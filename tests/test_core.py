"""Guest-machine tests. No window, no pygame."""

from __future__ import annotations

import unittest

from argonaut.asm.assembler import assemble
from argonaut.hw import (
    FB_BASE,
    FB_BYTES,
    PAL_BASE,
    PALETTE_SLOTS,
    PIXELS,
    ROM_BASE,
    SRAM_SIZE,
    cycles_for_frame,
)
from argonaut.machine.cpu import CPU
from argonaut.machine.memory import Memory


def _run(source: str, budget: int = 10000):
    prog = assemble(source)
    mem = Memory()
    mem.load_rom_image(prog.image)
    cpu = CPU(mem)
    cpu.reset(prog.symbols.get("_start", ROM_BASE))
    cpu.run(budget)
    return cpu, mem, prog


class HardwareBudgetTests(unittest.TestCase):
    def test_frame_cycle_average_is_exactly_20mhz(self):
        self.assertEqual(sum(cycles_for_frame(i) for i in range(3)), 1_000_000)
        self.assertEqual(FB_BYTES, 153_600)
        self.assertEqual(PIXELS, 320 * 240)
        self.assertEqual(SRAM_SIZE, 512 * 1024)
        self.assertEqual(PALETTE_SLOTS, 511)

    def test_palette_rejects_512th_slot(self):
        mem = Memory()
        mem.write16(PAL_BASE + 510 * 2, 0x7FFF)
        mem.write16(PAL_BASE + 511 * 2, 0x001F)
        self.assertEqual(mem.pal[510], 0x7FFF)
        self.assertGreaterEqual(mem.pal_clip, 1)
        self.assertEqual(len(mem.pal), 511)


class CpuTests(unittest.TestCase):
    def test_addi_and_halt_cycles(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 1
    ADDI R1, R1, 1
    HALT
"""
        )
        self.assertEqual(cpu.r[1], 2)
        self.assertEqual(cpu.cycles, 3)
        self.assertTrue(cpu.halted)

    def test_branch_cycle_cost(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 0
    ADDI R2, R0, 3
loop:
    ADDI R1, R1, 1
    CMP R1, R2
    BLT loop
    HALT
"""
        )
        # prelude 2, three trips of (ADDI+CMP+BLT=5), plus HALT
        self.assertEqual(cpu.r[1], 3)
        self.assertEqual(cpu.cycles, 2 + 3 * 5 + 1)

    def test_mul_costs_four(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 6
    ADDI R2, R0, 7
    MUL R3, R1, R2
    HALT
"""
        )
        self.assertEqual(cpu.r[3], 42)
        self.assertEqual(cpu.cycles, 1 + 1 + 4 + 1)

    def test_load_store_costs_two_and_xip_ignores_writes(self):
        cpu, mem, prog = _run(
            """
_start:
    ADDI R1, R0, 5
    ADDI R2, R0, 32
    STR R1, R2, 0
    LDR R3, R2, 0
    LI R4, marker
    LDR R5, R4, 0
    STR R1, R4, 0
    HALT
marker:
    .dw 0x11223344
    .align 4
"""
        )
        self.assertEqual(cpu.r[3], 5)
        self.assertEqual(cpu.r[5], 0x11223344)
        # ROM word unchanged
        off = prog.symbols["marker"] - ROM_BASE
        self.assertEqual(int.from_bytes(mem.rom[off : off + 4], "little"), 0x11223344)
        self.assertNotEqual(mem.fault, 0)

    def test_stack_and_call(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 40
    ADDI R2, R0, 2
    LI SP, 0x00060000
    BL double
    HALT
double:
    PUSH LR
    ADD R1, R1, R1
    POP LR
    RET
"""
        )
        self.assertEqual(cpu.r[1], 80)
        self.assertTrue(cpu.halted)

    def test_wfi_stops_early(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 1
    WFI
    ADDI R1, R1, 1
    HALT
""",
            budget=100,
        )
        self.assertTrue(cpu.asleep)
        self.assertEqual(cpu.r[1], 1)
        self.assertEqual(cpu.cycles, 2)

    def test_signed_compare(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 1
    ADDI R2, R0, -1
    CMP R1, R2
    BGT great
    ADDI R3, R0, 0
    B done
great:
    ADDI R3, R0, 7
done:
    HALT
"""
        )
        self.assertEqual(cpu.r[3], 7)

    def test_ldm_cycle_and_values(self):
        cpu, _, _ = _run(
            """
_start:
    ADDI R1, R0, 11
    ADDI R2, R0, 22
    ADDI R3, R0, 33
    ADDI R4, R0, 64
    STR R1, R4, 0
    STR R2, R4, 4
    STR R3, R4, 8
    LDM R4!, {R5, R6, R7}
    HALT
"""
        )
        self.assertEqual(cpu.r[5], 11)
        self.assertEqual(cpu.r[6], 22)
        self.assertEqual(cpu.r[7], 33)
        self.assertEqual(cpu.r[4], 64 + 12)

    def test_frame_budget_stops(self):
        cpu, _, _ = _run(
            """
_start:
loop:
    ADDI R1, R1, 1
    B loop
""",
            budget=50,
        )
        self.assertFalse(cpu.asleep)
        self.assertGreaterEqual(cpu.cycles, 50)
        self.assertLess(cpu.cycles, 60)
        self.assertGreater(cpu.r[1], 0)


if __name__ == "__main__":
    unittest.main()
