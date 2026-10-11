"""Two-pass assembler for THOTH.

Labels resolve to absolute addresses. R0 is ZERO, R12 is FP, R13 is SP, R14 is LR.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from argonaut.hw import ROM_BASE
from argonaut.machine.isa import (
    COND,
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
    OP_ANDI,
    OP_HALT,
    OP_LDR,
    OP_LDRB,
    OP_LDRH,
    OP_NOP,
    OP_ORI,
    OP_SARI,
    OP_SHLI,
    OP_SHRI,
    OP_STR,
    OP_STRB,
    OP_STRH,
    OP_WFI,
    OP_XORI,
    enc_alu,
    enc_bcc,
    enc_bl,
    enc_imm,
    enc_jr,
    enc_ldm,
    enc_lui,
    enc_op,
    enc_shift_imm,
)

REGS = {f"R{i}": i for i in range(15)}
REGS.update({"ZERO": 0, "FP": 12, "SP": 13, "LR": 14})

ALU3 = {
    "ADD": F_ADD,
    "SUB": F_SUB,
    "AND": F_AND,
    "OR": F_OR,
    "XOR": F_XOR,
    "SHL": F_SHL,
    "SHR": F_SHR,
    "SAR": F_SAR,
    "MUL": F_MUL,
}

IMM = {
    "ADDI": OP_ADDI,
    "ANDI": OP_ANDI,
    "ORI": OP_ORI,
    "XORI": OP_XORI,
    "LDR": OP_LDR,
    "STR": OP_STR,
    "LDRB": OP_LDRB,
    "STRB": OP_STRB,
    "LDRH": OP_LDRH,
    "STRH": OP_STRH,
}

SHIFTS = {"SHLI": OP_SHLI, "SHRI": OP_SHRI, "SARI": OP_SARI}

BCC = {
    "B": "AL",
    "BEQ": "EQ",
    "BNE": "NE",
    "BLT": "LT",
    "BGE": "GE",
    "BLE": "LE",
    "BGT": "GT",
    "BLTU": "LTU",
    "BGEU": "GEU",
    "BLEU": "LEU",
    "BGTU": "GTU",
}


class AsmError(Exception):
    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(message if line is None else f"строка {line}: {message}")


@dataclass
class Program:
    origin: int
    words: list[int]
    symbols: dict[str, int]
    source_map: list[int] = field(default_factory=list)

    @property
    def image(self) -> bytes:
        return b"".join(w.to_bytes(4, "little") for w in self.words)

    def disassembly(self) -> str:
        from argonaut.machine.isa import disasm

        lines = []
        for i, word in enumerate(self.words):
            addr = self.origin + i * 4
            lines.append(f"{addr:08X}: {word:08X}  {disasm(word)}")
        return "\n".join(lines)


class _Item:
    def size(self) -> int:
        return 4

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        raise NotImplementedError


class _Word(_Item):
    def __init__(self, value: int) -> None:
        self.value = value & 0xFFFFFFFF

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        return [self.value]


class _Bytes(_Item):
    def __init__(self, data: bytes) -> None:
        self.data = data

    def size(self) -> int:
        return len(self.data)

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        raise RuntimeError("bytes are packed separately")


class _Align(_Item):
    def __init__(self, bound: int, pc_at_parse: int | None = None) -> None:
        self.bound = bound
        self.pad = 0

    def size(self) -> int:
        return self.pad

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        if self.pad % 4:
            raise AsmError("выравнивание не кратно слову")
        return [enc_op(OP_NOP)] * (self.pad // 4) if False else []


class _LI(_Item):
    def __init__(self, rd: int, value: int | str) -> None:
        self.rd = rd
        self.value = value

    def size(self) -> int:
        if isinstance(self.value, str):
            return 8
        if -32768 <= self.value <= 32767:
            return 4
        return 8

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        if isinstance(self.value, str):
            if self.value not in labels:
                raise AsmError(f"нет метки {self.value}")
            val = labels[self.value]
            force_two = True
        else:
            val = self.value & 0xFFFFFFFF
            if val & 0x80000000:
                # keep the bit pattern; small negative already handled as signed int
                pass
            force_two = not (-32768 <= (self.value if isinstance(self.value, int) else val) <= 32767)
            if isinstance(self.value, int) and -32768 <= self.value <= 32767:
                return [enc_imm(OP_ADDI, self.rd, 0, self.value & 0xFFFF)]
        hi = (val >> 16) & 0xFFFF
        lo = val & 0xFFFF
        words = [enc_lui(self.rd, hi)]
        words.append(enc_imm(OP_ORI, self.rd, self.rd, lo) if lo or force_two else enc_op(OP_NOP))
        if not lo:
            words[1] = enc_op(OP_NOP)
        return words


class _Branch(_Item):
    def __init__(self, cond: str, label: str) -> None:
        self.cond = cond
        self.label = label

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        if self.label not in labels:
            raise AsmError(f"нет метки {self.label}")
        off = (labels[self.label] - (pc + 4)) // 4
        if self.cond == "BL":
            if not -(1 << 25) <= off < (1 << 25):
                raise AsmError(f"BL слишком далеко: {self.label}")
            return [enc_bl(off)]
        if not -(1 << 21) <= off < (1 << 21):
            raise AsmError(f"ветвление слишком далеко: {self.label}")
        return [enc_bcc(COND[self.cond], off)]


def _strip_comment(line: str) -> str:
    out = []
    i = 0
    in_str = False
    quote = ""
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = True
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#" or ch == ";":
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def _parse_int(text: str) -> int:
    text = text.strip()
    neg = False
    if text.startswith("-"):
        neg = True
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    if text.lower().startswith("0x"):
        val = int(text, 16)
    else:
        val = int(text, 10)
    return -val if neg else val


def _reg(token: str, line: int) -> int:
    name = token.strip().upper()
    if name not in REGS:
        raise AsmError(f"не регистр: {token}", line)
    return REGS[name]


def _split_ops(rest: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = False
    quote = ""
    for ch in rest:
        if in_str:
            buf.append(ch)
            if ch == quote:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            quote = ch
            buf.append(ch)
            continue
        if ch in "[{":
            depth += 1
            buf.append(ch)
            continue
        if ch in "]}":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _unescape(text: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            n = text[i + 1]
            mapping = {"n": 10, "t": 9, "0": 0, "\\": 92, "'": 39, '"': 34, "r": 13}
            if n not in mapping:
                raise AsmError(f"неизвестное экранирование \\{n}")
            out.append(mapping[n])
            i += 2
            continue
        out.append(ord(ch) & 0xFF)
        i += 1
    return bytes(out)


def assemble(source: str, origin: int = ROM_BASE) -> Program:
    equ: dict[str, int] = {}
    raw_lines: list[tuple[int, str]] = []
    for n, line in enumerate(source.splitlines(), 1):
        text = _strip_comment(line)
        if not text:
            continue
        if text.lower().startswith(".equ "):
            body = text[5:].strip()
            name, _, val = body.partition(" ")
            # also allow comma
            if "," in body and " " not in body.split(",")[0]:
                name, val = [p.strip() for p in body.split(",", 1)]
            else:
                bits = body.split()
                if len(bits) != 2:
                    raise AsmError("ожидалось .equ ИМЯ ЗНАЧЕНИЕ", n)
                name, val = bits
            equ[name] = _parse_int(val)
            continue
        raw_lines.append((n, text))

    items: list[tuple[int, _Item | _Bytes | _Align]] = []
    labels_at: list[tuple[int, str]] = []  # item index, name
    pc = origin
    # First we need sizes, but align depends on pc. We'll compute pc as we parse,
    # storing pad into _Align. Labels bind to the pc at that point.

    pending_labels: list[tuple[int, str]] = []
    symbols_build: dict[str, int] = {}
    seq: list[tuple[int, object]] = []

    def bind_labels(addr: int) -> None:
        for line_no, name in pending_labels:
            if name in symbols_build or name in equ:
                raise AsmError(f"повтор метки {name}", line_no)
            symbols_build[name] = addr
        pending_labels.clear()

    for line_no, text in raw_lines:
        if text.endswith(":") and " " not in text:
            name = text[:-1].strip()
            if not name:
                raise AsmError("пустая метка", line_no)
            pending_labels.append((line_no, name))
            continue
        # label and instruction on one line: `name: ADD ...` not required
        bind_labels(pc)
        try:
            item, size = _parse_item(text, line_no, equ, pc)
        except AsmError as exc:
            if exc.line is None:
                raise AsmError(str(exc), line_no) from exc
            raise
        if isinstance(item, _Align):
            pad = (item.bound - (pc % item.bound)) % item.bound
            item.pad = pad
            size = pad
        seq.append((line_no, item))
        pc += size
    bind_labels(pc)

    # Encode
    words: list[int] = []
    source_map: list[int] = []
    cursor = origin
    byte_buf = bytearray()

    def flush_bytes() -> None:
        nonlocal cursor
        if not byte_buf:
            return
        if len(byte_buf) % 4 != 0:
            raise AsmError("данные не выровнены на слово — поставьте .align 4")
        for i in range(0, len(byte_buf), 4):
            words.append(int.from_bytes(byte_buf[i : i + 4], "little"))
            source_map.append(0)
        cursor += len(byte_buf)
        byte_buf.clear()

    for line_no, item in seq:
        if isinstance(item, _Bytes):
            byte_buf.extend(item.data)
            continue
        if isinstance(item, _Align):
            if item.pad:
                # padding bytes, not instructions, unless we are in word stream
                if byte_buf or item.pad % 4:
                    byte_buf.extend(b"\x00" * item.pad)
                else:
                    flush_bytes()
                    for _ in range(item.pad // 4):
                        words.append(0)
                        source_map.append(line_no)
                    cursor += item.pad
            continue
        flush_bytes()
        try:
            encoded = item.encode(cursor, symbols_build)
        except AsmError as exc:
            raise AsmError(str(exc), line_no) from exc
        if sum(4 for _ in encoded) != item.size():
            raise AsmError("размер команды разъехался с кодированием", line_no)
        for word in encoded:
            words.append(word & 0xFFFFFFFF)
            source_map.append(line_no)
        cursor += item.size()
    flush_bytes()
    if len(byte_buf):
        raise AsmError("хвост данных не выровнен")
    return Program(origin, words, symbols_build, source_map)


def _value(token: str, equ: dict[str, int], line: int) -> int | str:
    token = token.strip()
    if token in equ:
        return equ[token]
    if token[:1].isalpha() or token.startswith("_") or token.startswith("."):
        return token
    try:
        return _parse_int(token)
    except ValueError as exc:
        raise AsmError(f"не число и не метка: {token}", line) from exc


def _parse_item(text: str, line: int, equ: dict[str, int], pc: int):
    if text.startswith("."):
        head, _, rest = text[1:].partition(" ")
        head = head.lower()
        rest = rest.strip()
        if head == "org":
            raise AsmError(".org внутри программы не поддерживается", line)
        if head == "align":
            bound = _parse_int(rest or "4")
            if bound <= 0 or bound & (bound - 1):
                raise AsmError(".align ждёт степень двойки", line)
            return _Align(bound), 0
        if head == "dw":
            vals = _split_ops(rest)
            data = bytearray()
            for v in vals:
                num = _value(v, equ, line)
                if not isinstance(num, int):
                    raise AsmError(".dw пока только для чисел", line)
                data += (num & 0xFFFFFFFF).to_bytes(4, "little")
            return _Bytes(bytes(data)), len(data)
        if head == "db":
            vals = _split_ops(rest)
            data = bytearray()
            for v in vals:
                if v.startswith(("'", '"')):
                    data += _unescape(v[1:-1])
                else:
                    num = _value(v, equ, line)
                    if not isinstance(num, int):
                        raise AsmError(".db ждёт байт", line)
                    data.append(num & 0xFF)
            return _Bytes(bytes(data)), len(data)
        if head in ("ascii", "asciiz"):
            if not rest or rest[0] not in ("'", '"'):
                raise AsmError("ожидалась строка", line)
            raw = _unescape(rest[1:-1])
            if head == "asciiz":
                raw += b"\x00"
            return _Bytes(raw), len(raw)
        raise AsmError(f"неизвестная директива .{head}", line)

    parts = text.replace(",", " ").split()
    # restore because we need commas for reg lists... do a better split
    mnemonic, _, rest = text.partition(" ")
    mnemonic = mnemonic.upper()
    rest = rest.strip()
    ops = _split_ops(rest) if rest else []

    if mnemonic in ("NOP", "HALT", "WFI", "RET"):
        if mnemonic == "NOP":
            return _Word(enc_op(OP_NOP)), 4
        if mnemonic == "HALT":
            return _Word(enc_op(OP_HALT)), 4
        if mnemonic == "WFI":
            return _Word(enc_op(OP_WFI)), 4
        return _Word(enc_jr(0, REGS["LR"], 0)), 4

    if mnemonic == "LI":
        if len(ops) != 2:
            raise AsmError("LI rd, значение", line)
        rd = _reg(ops[0], line)
        val = _value(ops[1], equ, line)
        item = _LI(rd, val)
        return item, item.size()

    if mnemonic in ("PUSH", "POP"):
        if len(ops) != 1:
            raise AsmError(f"{mnemonic} rd", line)
        rd = _reg(ops[0], line)
        if mnemonic == "PUSH":
            # ADDI SP, SP, -4 ; STR rd, SP, 0
            return _Pair(
                enc_imm(OP_ADDI, REGS["SP"], REGS["SP"], (-4) & 0xFFFF),
                enc_imm(OP_STR, rd, REGS["SP"], 0),
            ), 8
        return _Pair(
            enc_imm(OP_LDR, rd, REGS["SP"], 0),
            enc_imm(OP_ADDI, REGS["SP"], REGS["SP"], 4),
        ), 8

    if mnemonic == "NEG":
        if len(ops) != 2:
            raise AsmError("NEG rd, rs", line)
        rd = _reg(ops[0], line)
        rs = _reg(ops[1], line)
        return _Word(enc_alu(F_SUB, rd, 0, rs)), 4

    if mnemonic in ALU3:
        if len(ops) != 3:
            raise AsmError(f"{mnemonic} rd, rs, rt", line)
        rd, rs, rt = _reg(ops[0], line), _reg(ops[1], line), _reg(ops[2], line)
        return _Word(enc_alu(ALU3[mnemonic], rd, rs, rt)), 4

    if mnemonic == "MOV":
        rd, rs = _reg(ops[0], line), _reg(ops[1], line)
        return _Word(enc_alu(F_MOV, rd, rs, 0)), 4
    if mnemonic == "MVN":
        rd, rs = _reg(ops[0], line), _reg(ops[1], line)
        return _Word(enc_alu(F_MVN, rd, rs, 0)), 4
    if mnemonic in ("CMP", "TEST"):
        rs, rt = _reg(ops[0], line), _reg(ops[1], line)
        funct = F_CMP if mnemonic == "CMP" else F_TEST
        return _Word(enc_alu(funct, 0, rs, rt)), 4

    if mnemonic in IMM or mnemonic in SHIFTS:
        if len(ops) != 3:
            raise AsmError(f"{mnemonic} rd, rs, imm", line)
        rd = _reg(ops[0], line)
        # allow LDR R1, [R2, -4]
        second = ops[1].strip()
        third = ops[2].strip()
        if second.startswith("["):
            raise AsmError("используйте LDR rd, rs, смещение", line)
        rs = _reg(second, line)
        imm_v = _value(third, equ, line)
        if not isinstance(imm_v, int):
            raise AsmError("смещение должно быть числом", line)
        if mnemonic in SHIFTS:
            if not 0 <= imm_v <= 31:
                raise AsmError("сдвиг 0..31", line)
            return _Word(enc_shift_imm(SHIFTS[mnemonic], rd, rs, imm_v)), 4
        if mnemonic in ("ANDI", "ORI", "XORI"):
            if not 0 <= imm_v <= 0xFFFF:
                raise AsmError("непосредственное 0..65535", line)
            return _Word(enc_imm(IMM[mnemonic], rd, rs, imm_v)), 4
        if not -32768 <= imm_v <= 32767:
            raise AsmError("смещение не влезает в 16 бит", line)
        return _Word(enc_imm(IMM[mnemonic], rd, rs, imm_v & 0xFFFF)), 4

    if mnemonic == "LUI":
        if len(ops) != 2:
            raise AsmError("LUI rd, imm", line)
        rd = _reg(ops[0], line)
        imm_v = _value(ops[1], equ, line)
        if not isinstance(imm_v, int) or not 0 <= (imm_v & 0xFFFF) <= 0xFFFF:
            raise AsmError("LUI ждёт 16-битное число", line)
        if imm_v < 0 or imm_v > 0xFFFF:
            raise AsmError("LUI ждёт 0..65535", line)
        return _Word(enc_lui(rd, imm_v)), 4

    if mnemonic in BCC or mnemonic == "BL":
        if len(ops) != 1:
            raise AsmError(f"{mnemonic} метка", line)
        label = ops[0]
        if mnemonic == "BL":
            return _Branch("BL", label), 4
        return _Branch(BCC[mnemonic], label), 4

    if mnemonic == "JR":
        if len(ops) != 1:
            raise AsmError("JR rs", line)
        return _Word(enc_jr(0, _reg(ops[0], line), 0)), 4
    if mnemonic == "JALR":
        if len(ops) != 2:
            raise AsmError("JALR rd, rs", line)
        return _Word(enc_jr(_reg(ops[0], line), _reg(ops[1], line), 1)), 4

    if mnemonic in ("LDM", "STM"):
        if len(ops) != 2:
            raise AsmError(f"{mnemonic} rs!, {{regs}}", line)
        base_tok = ops[0]
        wb = base_tok.endswith("!")
        if wb:
            base_tok = base_tok[:-1]
        base = _reg(base_tok, line)
        group = ops[1].strip()
        if not (group.startswith("{") and group.endswith("}")):
            raise AsmError("список регистров в фигурных скобках", line)
        mask = 0
        for name in group[1:-1].split(","):
            name = name.strip()
            if not name:
                continue
            mask |= 1 << _reg(name, line)
        op = 0x10 if mnemonic == "LDM" else 0x11
        return _Word(enc_ldm(op, base, 1 if wb else 0, mask)), 4

    raise AsmError(f"неизвестная команда {mnemonic}", line)


class _Pair(_Item):
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

    def size(self) -> int:
        return 8

    def encode(self, pc: int, labels: dict[str, int]) -> list[int]:
        return [self.a, self.b]
