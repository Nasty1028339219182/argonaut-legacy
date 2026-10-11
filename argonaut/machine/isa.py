"""THOTH instruction encoding.

32-bit fixed instructions. R0 is hardwired to zero.
R12 is FP, R13 is SP, R14 is LR. R1–R11 are general purpose.

Cycle costs, before the region wait added at execution time:
  ALU / immediate / shift-immediate / NOP : 1
  MUL                                       : 4
  LDR/STR and byte/half variants            : 2
  LDM/STM                                   : 1 + n
  any branch, JR, BL                        : 3
  WFI / HALT                                : 1

SRAM and wave RAM add nothing. A data access in ROM adds 1.
Framebuffer, palette, and device ports add 2. Instruction fetch is
already inside the costs above and is not charged again.
"""

from __future__ import annotations

OP_ALU = 0x00
OP_ADDI = 0x01
OP_ANDI = 0x02
OP_ORI = 0x03
OP_XORI = 0x04
OP_LUI = 0x05
OP_LDR = 0x06
OP_STR = 0x07
OP_LDRB = 0x08
OP_STRB = 0x09
OP_LDRH = 0x0A
OP_STRH = 0x0B
OP_BCC = 0x0C
OP_BL = 0x0D
OP_JR = 0x0E
OP_LDM = 0x10
OP_STM = 0x11
OP_WFI = 0x12
OP_HALT = 0x13
OP_NOP = 0x14
OP_SHLI = 0x15
OP_SHRI = 0x16
OP_SARI = 0x17

F_ADD, F_SUB, F_AND, F_OR, F_XOR = 0, 1, 2, 3, 4
F_SHL, F_SHR, F_SAR, F_MUL, F_MOV = 5, 6, 7, 8, 9
F_CMP, F_MVN, F_TEST = 10, 11, 13

COND = {
    "EQ": 0,
    "NE": 1,
    "LT": 2,
    "GE": 3,
    "LE": 4,
    "GT": 5,
    "AL": 6,
    "LTU": 7,
    "GEU": 8,
    "LEU": 9,
    "GTU": 10,
}
COND_NAME = {v: k for k, v in COND.items()}

FUNCT_NAME = {
    F_ADD: "ADD",
    F_SUB: "SUB",
    F_AND: "AND",
    F_OR: "OR",
    F_XOR: "XOR",
    F_SHL: "SHL",
    F_SHR: "SHR",
    F_SAR: "SAR",
    F_MUL: "MUL",
    F_MOV: "MOV",
    F_CMP: "CMP",
    F_MVN: "MVN",
    F_TEST: "TEST",
}

REG_NAME = [f"R{i}" for i in range(15)]
REG_NAME[12] = "FP"
REG_NAME[13] = "SP"
REG_NAME[14] = "LR"


def sext16(value: int) -> int:
    value &= 0xFFFF
    if value & 0x8000:
        return value - 0x10000
    return value


def sext(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    sign = 1 << (bits - 1)
    if value & sign:
        return value - (1 << bits)
    return value


def enc_alu(funct: int, rd: int, rs: int, rt: int) -> int:
    return (OP_ALU << 26) | ((rd & 31) << 21) | ((rs & 31) << 16) | ((rt & 31) << 11) | ((funct & 31) << 6)


def enc_imm(op: int, rd: int, rs: int, imm: int) -> int:
    return (op << 26) | ((rd & 31) << 21) | ((rs & 31) << 16) | (imm & 0xFFFF)


def enc_lui(rd: int, imm: int) -> int:
    return (OP_LUI << 26) | ((rd & 31) << 21) | (imm & 0xFFFF)


def enc_bcc(cond: int, word_off: int) -> int:
    return (OP_BCC << 26) | ((cond & 15) << 22) | (word_off & 0x3FFFFF)


def enc_bl(word_off: int) -> int:
    return (OP_BL << 26) | (word_off & 0x3FFFFFF)


def enc_jr(rd: int, rs: int, link: int) -> int:
    return (OP_JR << 26) | ((rd & 31) << 21) | ((rs & 31) << 16) | ((1 if link else 0) << 15)


def enc_ldm(op: int, base: int, writeback: int, mask: int) -> int:
    return (op << 26) | ((base & 31) << 21) | ((1 if writeback else 0) << 20) | (mask & 0x7FFF)


def enc_shift_imm(op: int, rd: int, rs: int, sh: int) -> int:
    return (op << 26) | ((rd & 31) << 21) | ((rs & 31) << 16) | ((sh & 31) << 11)


def enc_op(op: int) -> int:
    return op << 26


def instruction_cycles(word: int) -> int:
    op = (word >> 26) & 0x3F
    if op == OP_ALU:
        funct = (word >> 6) & 0x1F
        return 4 if funct == F_MUL else 1
    if op in (OP_LDR, OP_STR, OP_LDRB, OP_STRB, OP_LDRH, OP_STRH):
        return 2
    if op in (OP_LDM, OP_STM):
        mask = word & 0x7FFF
        return 1 + bin(mask).count("1")
    if op in (OP_BCC, OP_BL, OP_JR):
        return 3
    return 1


def _reg(i: int) -> str:
    if 0 <= i < 15:
        return REG_NAME[i]
    return f"R{i}"


def disasm(word: int) -> str:
    op = (word >> 26) & 0x3F
    rd = (word >> 21) & 0x1F
    rs = (word >> 16) & 0x1F
    rt = (word >> 11) & 0x1F
    funct = (word >> 6) & 0x1F
    imm = word & 0xFFFF
    if op == OP_ALU:
        name = FUNCT_NAME.get(funct, f"ALU{funct}")
        if funct in (F_CMP, F_TEST):
            return f"{name} {_reg(rs)}, {_reg(rt)}"
        if funct in (F_MOV, F_MVN):
            return f"{name} {_reg(rd)}, {_reg(rs)}"
        return f"{name} {_reg(rd)}, {_reg(rs)}, {_reg(rt)}"
    imm_ops = {
        OP_ADDI: "ADDI",
        OP_ANDI: "ANDI",
        OP_ORI: "ORI",
        OP_XORI: "XORI",
        OP_LDR: "LDR",
        OP_STR: "STR",
        OP_LDRB: "LDRB",
        OP_STRB: "STRB",
        OP_LDRH: "LDRH",
        OP_STRH: "STRH",
    }
    if op in imm_ops:
        return f"{imm_ops[op]} {_reg(rd)}, {_reg(rs)}, {sext16(imm)}"
    if op == OP_LUI:
        return f"LUI {_reg(rd)}, 0x{imm:04X}"
    if op == OP_BCC:
        cond = COND_NAME.get((word >> 22) & 0xF, "?")
        off = sext(word & 0x3FFFFF, 22)
        return f"B{cond} {off:+d}"
    if op == OP_BL:
        off = sext(word & 0x3FFFFFF, 26)
        return f"BL {off:+d}"
    if op == OP_JR:
        link = (word >> 15) & 1
        if link:
            return f"JALR {_reg(rd)}, {_reg(rs)}"
        return f"JR {_reg(rs)}"
    if op in (OP_LDM, OP_STM):
        base = (word >> 21) & 31
        wb = "!" if (word >> 20) & 1 else ""
        mask = word & 0x7FFF
        regs = ",".join(_reg(i) for i in range(15) if mask & (1 << i))
        mnem = "LDM" if op == OP_LDM else "STM"
        return f"{mnem} {_reg(base)}{wb}, {{{regs}}}"
    if op == OP_SHLI:
        return f"SHLI {_reg(rd)}, {_reg(rs)}, {rt}"
    if op == OP_SHRI:
        return f"SHRI {_reg(rd)}, {_reg(rs)}, {rt}"
    if op == OP_SARI:
        return f"SARI {_reg(rd)}, {_reg(rs)}, {rt}"
    if op == OP_WFI:
        return "WFI"
    if op == OP_HALT:
        return "HALT"
    if op == OP_NOP:
        return "NOP"
    return f".dw 0x{word:08X}"
