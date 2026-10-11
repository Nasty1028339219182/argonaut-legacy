"""Cycle-accurate THOTH-Core interpreter."""

from __future__ import annotations

from argonaut.hw import ROM_BASE, s32
from argonaut.machine.isa import (
    F_ADD,
    F_AND,
    F_CMP,
    F_MOV,
    F_MUL,
    F_MVN,
    F_OR,
    F_SAR,
    F_SHL,
    F_SHR,
    F_SUB,
    F_TEST,
    F_XOR,
    OP_ADDI,
    OP_ALU,
    OP_ANDI,
    OP_BCC,
    OP_BL,
    OP_HALT,
    OP_JR,
    OP_LDM,
    OP_LDR,
    OP_LDRB,
    OP_LDRH,
    OP_LUI,
    OP_NOP,
    OP_ORI,
    OP_SARI,
    OP_SHLI,
    OP_SHRI,
    OP_STM,
    OP_STR,
    OP_STRB,
    OP_STRH,
    OP_WFI,
    OP_XORI,
    instruction_cycles,
    sext,
    sext16,
)
from argonaut.machine.memory import Memory


class CPU:
    def __init__(self, mem: Memory) -> None:
        self.mem = mem
        self.r = [0] * 15
        self.pc = ROM_BASE
        self.cycles = 0
        self.asleep = False
        self.halted = False
        self.n = 0
        self.z = 0
        self.c = 0
        self.v = 0
        mem.cpu = self

    def reset(self, pc: int) -> None:
        self.r = [0] * 15
        self.pc = pc & 0xFFFFFFFF
        self.cycles = 0
        self.asleep = False
        self.halted = False
        self.n = self.z = self.c = self.v = 0

    def run(self, budget: int) -> int:
        """Run until asleep, halted, or `budget` guest cycles have been spent.

        An instruction already started is finished even if it crosses the budget
        by a few cycles. The machine subtracts that overrun from the next frame.
        """
        self.cycles = 0
        while not self.asleep and not self.halted and self.cycles < budget:
            self.step()
        return self.cycles

    def _write_reg(self, index: int, value: int) -> None:
        if 1 <= index <= 14:
            self.r[index] = value & 0xFFFFFFFF

    def _set_nz(self, result: int) -> None:
        result &= 0xFFFFFFFF
        self.z = 1 if result == 0 else 0
        self.n = 1 if result & 0x80000000 else 0

    def _cmp(self, rs: int, rt: int) -> None:
        rs_u = rs & 0xFFFFFFFF
        rt_u = rt & 0xFFFFFFFF
        result = (rs_u - rt_u) & 0xFFFFFFFF
        self._set_nz(result)
        self.c = 1 if rs_u >= rt_u else 0
        rs_s = s32(rs_u)
        rt_s = s32(rt_u)
        res_s = s32(result)
        self.v = 1 if ((rs_s < 0) != (rt_s < 0)) and ((res_s < 0) != (rs_s < 0)) else 0

    def step(self) -> None:
        word = self.mem.read_exec(self.pc)
        if word is None:
            self.halted = True
            return
        self.pc = (self.pc + 4) & 0xFFFFFFFF
        cost = instruction_cycles(word)
        self.cycles += cost
        op = (word >> 26) & 0x3F
        rd = (word >> 21) & 31
        rs = (word >> 16) & 31
        rt = (word >> 11) & 31
        funct = (word >> 6) & 31
        imm = word & 0xFFFF

        def rr(index: int) -> int:
            if 0 <= index <= 14:
                return self.r[index]
            return 0

        if op == OP_ALU:
            self._alu(funct, rd, rr(rs), rr(rt))
            return
        if op == OP_ADDI:
            self._write_reg(rd, (rr(rs) + sext16(imm)) & 0xFFFFFFFF)
            return
        if op == OP_ANDI:
            self._write_reg(rd, rr(rs) & imm)
            return
        if op == OP_ORI:
            self._write_reg(rd, rr(rs) | imm)
            return
        if op == OP_XORI:
            self._write_reg(rd, rr(rs) ^ imm)
            return
        if op == OP_LUI:
            self._write_reg(rd, (imm & 0xFFFF) << 16)
            return
        if op == OP_LDR:
            self._write_reg(rd, self.mem.read32((rr(rs) + sext16(imm)) & 0xFFFFFFFF))
            return
        if op == OP_STR:
            self.mem.write32((rr(rs) + sext16(imm)) & 0xFFFFFFFF, rr(rd))
            return
        if op == OP_LDRB:
            self._write_reg(rd, self.mem.read8((rr(rs) + sext16(imm)) & 0xFFFFFFFF))
            return
        if op == OP_STRB:
            self.mem.write8((rr(rs) + sext16(imm)) & 0xFFFFFFFF, rr(rd) & 0xFF)
            return
        if op == OP_LDRH:
            self._write_reg(rd, self.mem.read16((rr(rs) + sext16(imm)) & 0xFFFFFFFF))
            return
        if op == OP_STRH:
            self.mem.write16((rr(rs) + sext16(imm)) & 0xFFFFFFFF, rr(rd) & 0xFFFF)
            return
        if op == OP_SHLI:
            self._write_reg(rd, (rr(rs) << rt) & 0xFFFFFFFF)
            return
        if op == OP_SHRI:
            self._write_reg(rd, (rr(rs) & 0xFFFFFFFF) >> rt)
            return
        if op == OP_SARI:
            self._write_reg(rd, (s32(rr(rs)) >> rt) & 0xFFFFFFFF)
            return
        if op == OP_BCC:
            if self._take_cond((word >> 22) & 0xF):
                off = sext(word & 0x3FFFFF, 22)
                self.pc = (self.pc + (off << 2)) & 0xFFFFFFFF
            return
        if op == OP_BL:
            off = sext(word & 0x3FFFFFF, 26)
            self._write_reg(14, self.pc)
            self.pc = (self.pc + (off << 2)) & 0xFFFFFFFF
            return
        if op == OP_JR:
            link = (word >> 15) & 1
            target = rr(rs)
            if link:
                self._write_reg(rd, self.pc)
            self.pc = target & 0xFFFFFFFF
            return
        if op == OP_LDM:
            self._block((word >> 21) & 31, (word >> 20) & 1, word & 0x7FFF, load=True)
            return
        if op == OP_STM:
            self._block((word >> 21) & 31, (word >> 20) & 1, word & 0x7FFF, load=False)
            return
        if op == OP_WFI:
            self.asleep = True
            return
        if op == OP_HALT:
            self.halted = True
            return
        if op == OP_NOP:
            return
        # Unknown opcode: treat as NOP so a bad cart doesn't explode the host.
        return

    def _alu(self, funct: int, rd: int, a: int, b: int) -> None:
        a &= 0xFFFFFFFF
        b &= 0xFFFFFFFF
        if funct == F_ADD:
            self._write_reg(rd, (a + b) & 0xFFFFFFFF)
        elif funct == F_SUB:
            self._write_reg(rd, (a - b) & 0xFFFFFFFF)
        elif funct == F_AND:
            self._write_reg(rd, a & b)
        elif funct == F_OR:
            self._write_reg(rd, a | b)
        elif funct == F_XOR:
            self._write_reg(rd, a ^ b)
        elif funct == F_SHL:
            self._write_reg(rd, (a << (b & 31)) & 0xFFFFFFFF)
        elif funct == F_SHR:
            self._write_reg(rd, a >> (b & 31))
        elif funct == F_SAR:
            self._write_reg(rd, (s32(a) >> (b & 31)) & 0xFFFFFFFF)
        elif funct == F_MUL:
            self._write_reg(rd, (s32(a) * s32(b)) & 0xFFFFFFFF)
        elif funct == F_MOV:
            self._write_reg(rd, a)
        elif funct == F_MVN:
            self._write_reg(rd, (~a) & 0xFFFFFFFF)
        elif funct == F_CMP:
            self._cmp(a, b)
        elif funct == F_TEST:
            self._set_nz(a & b)
            self.c = 0
            self.v = 0
        else:
            pass

    def _take_cond(self, cond: int) -> bool:
        n, z, c, v = self.n, self.z, self.c, self.v
        if cond == 0:
            return z == 1
        if cond == 1:
            return z == 0
        if cond == 2:
            return n != v
        if cond == 3:
            return n == v
        if cond == 4:
            return z == 1 or n != v
        if cond == 5:
            return z == 0 and n == v
        if cond == 6:
            return True
        if cond == 7:
            return c == 0
        if cond == 8:
            return c == 1
        if cond == 9:
            return c == 0 or z == 1
        if cond == 10:
            return c == 1 and z == 0
        return False

    def _block(self, base: int, writeback: int, mask: int, load: bool) -> None:
        if base > 14:
            return
        addr = self.r[base]
        for i in range(15):
            if mask & (1 << i):
                if load:
                    self._write_reg(i, self.mem.read32(addr & 0xFFFFFFFF))
                else:
                    self.mem.write32(addr & 0xFFFFFFFF, self.r[i])
                addr = (addr + 4) & 0xFFFFFFFF
        if writeback:
            self._write_reg(base, addr)
