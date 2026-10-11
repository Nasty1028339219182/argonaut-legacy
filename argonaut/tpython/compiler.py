"""Compile TPython to THOTH assembly.

Integers are signed 32-bit and wrap. Strings and lists are heap/ROM objects.
Known integer addition uses ADD (1 cycle). Anything that might be a string
goes through fn_concat, which still adds two integers.
"""

from __future__ import annotations

from argonaut.hw import GLOBALS_BASE, STR_MAGIC
from argonaut.tpython.astnodes import (
    Assign,
    Bin,
    Break,
    Call,
    Continue,
    ExprStmt,
    For,
    Func,
    Global,
    If,
    Index,
    ListLit,
    Name,
    Num,
    Pass,
    Return,
    Str,
    Unary,
    While,
)
from argonaut.tpython.errors import TPyError
from argonaut.tpython.parser import parse

INT, STR_, LIST, ANY = "int", "str", "list", "any"

SIGS = {
    "cls": (0, 1, [0]),
    "pset": (3, 3, []),
    "pget": (2, 2, []),
    "pal": (4, 4, []),
    "rect": (5, 5, []),
    "rectfill": (5, 5, []),
    "spr": (3, 5, [1, 1]),
    "map": (6, 6, []),
    "text": (4, 4, []),
    "btn": (1, 1, []),
    "btnp": (1, 1, []),
    "camera": (0, 2, [0, 0]),
    "sfx": (1, 1, []),
    "music": (1, 1, []),
    "frame": (0, 0, []),
    "cycles": (0, 0, []),
    "peek": (1, 1, []),
    "poke": (2, 2, []),
    "print": (1, 1, []),
    "log": (1, 1, []),
    "rnd": (1, 1, []),
    "abs": (1, 1, []),
    "min": (2, 2, []),
    "max": (2, 2, []),
    "len": (1, 1, []),
    "list": (1, 1, []),
    "line": (5, 5, []),
    "circ": (4, 4, []),
    "circfill": (4, 4, []),
    "clip": (0, 4, [0, 0, 320, 240]),
    "fget": (1, 2, [-1]),
    "fset": (3, 3, []),
}

BUILTIN_FN = {
    "cls": "fn_cls",
    "pset": "fn_pset",
    "pget": "fn_pget",
    "pal": "fn_pal",
    "rect": "fn_rect",
    "rectfill": "fn_rectfill",
    "spr": "fn_spr",
    "map": "fn_map",
    "text": "fn_text",
    "btn": "fn_btn",
    "btnp": "fn_btnp",
    "camera": "fn_camera",
    "sfx": "fn_sfx",
    "music": "fn_music",
    "frame": "fn_frame",
    "cycles": "fn_cycles",
    "peek": "fn_peek",
    "poke": "fn_poke",
    "print": "fn_log",
    "log": "fn_log",
    "rnd": "fn_rnd",
    "abs": "fn_abs",
    "min": "fn_min",
    "max": "fn_max",
    "len": "fn_len",
    "list": "fn_list_new",
    "line": "fn_line",
    "circ": "fn_circ",
    "circfill": "fn_circfill",
    "clip": "fn_clip",
    "fget": "fn_fget",
    "fset": "fn_fset",
}


class Compiler:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.rodata: list[str] = []
        self.globals: dict[str, int] = {}
        self.global_types: dict[str, str] = {}
        self.local_off: dict[str, int] = {}
        self.local_types: dict[str, str] = {}
        self.locals_set: set[str] = set()
        self.funcs: dict[str, Func] = {}
        self.loops: list[tuple[str, str]] = []
        self.nid = 0
        self.str_id = 0
        self.epilogue = ""

    def a(self, text: str) -> None:
        self.lines.append(text)

    def lab(self, hint: str = "L") -> str:
        self.nid += 1
        return f".{hint}_{self.nid}"

    def compile(self, source: str) -> str:
        program = parse(source)
        funcs: list[Func] = []
        top = []
        for stmt in program.stmts:
            if isinstance(stmt, Func):
                if stmt.name in self.funcs:
                    raise TPyError("dup-func", stmt.line, name=stmt.name)
                self.funcs[stmt.name] = stmt
                funcs.append(stmt)
            else:
                top.append(stmt)
        self._infer_block(top, set())
        for fn in funcs:
            self._compile_func(fn)
        for special in ("_init", "_update", "_draw"):
            if special not in self.funcs:
                self.a(f"user__{special[1:]}:")
                self.a("    JR LR")
        self._compile_init(top)
        self.lines.extend(self.rodata)
        return "\n".join(self.lines) + "\n"

    def _ensure_global(self, name: str) -> int:
        if name not in self.globals:
            self.globals[name] = GLOBALS_BASE + 4 * len(self.globals)
        return self.globals[name]

    def _infer_block(self, stmts, global_names: set[str]) -> None:
        for stmt in stmts:
            if isinstance(stmt, Assign) and isinstance(stmt.target, Name):
                if stmt.target.name not in global_names:
                    # top-level names are globals; inside functions this isn't called that way
                    self.global_types[stmt.target.name] = self._infer(stmt.value)
                    self._ensure_global(stmt.target.name)
            elif isinstance(stmt, If):
                self._infer_block(stmt.body, global_names)
                for _, body in stmt.elifs:
                    self._infer_block(body, global_names)
                if stmt.else_body:
                    self._infer_block(stmt.else_body, global_names)
            elif isinstance(stmt, (While, For)):
                self._infer_block(stmt.body, global_names)

    def _infer(self, node) -> str:
        if isinstance(node, Num):
            return INT
        if isinstance(node, Str):
            return STR_
        if isinstance(node, ListLit):
            return LIST
        if isinstance(node, Name):
            return self.global_types.get(node.name, ANY)
        if isinstance(node, Bin):
            lt, rt = self._infer(node.left), self._infer(node.right)
            if node.op == "+" and (lt == STR_ or rt == STR_):
                return STR_
            if node.op == "+" and lt == INT and rt == INT:
                return INT
            if node.op in ("==", "!=", "<", ">", "<=", ">=", "and", "or"):
                return INT
            return INT if lt == INT and rt == INT else ANY
        if isinstance(node, Unary):
            return INT
        if isinstance(node, Call):
            if node.name == "list":
                return LIST
            if node.name in ("text", "print", "log", "cls", "pset", "pal", "music", "sfx"):
                return INT
            return INT
        return ANY

    def _compile_init(self, stmts) -> None:
        locals_, temps = self._scan_locals(stmts, [], set())
        self._emit_function("generated_init", [], stmts, extra_locals=temps, force_global=True)

    def _compile_func(self, fn: Func) -> None:
        declared = self._globals_in(fn.body)
        if fn.name in ("_init", "_update", "_draw"):
            label = "user__" + fn.name[1:]
        else:
            label = "uf_" + fn.name
        self._emit_function(label, fn.params, fn.body, declared_globals=declared)

    def _globals_in(self, stmts) -> set[str]:
        found = set()

        def walk(body):
            for stmt in body:
                if isinstance(stmt, Global):
                    found.update(stmt.names)
                elif isinstance(stmt, If):
                    walk(stmt.body)
                    for _, b in stmt.elifs:
                        walk(b)
                    if stmt.else_body:
                        walk(stmt.else_body)
                elif isinstance(stmt, (While, For)):
                    walk(stmt.body)

        walk(stmts)
        return found

    def _scan_locals(self, stmts, params, declared_globals: set[str]):
        locals_ = []
        for p in params:
            if p not in locals_:
                locals_.append(p)

        def add(name, line):
            if name in declared_globals:
                return
            if name not in locals_:
                locals_.append(name)

        def walk(body):
            for stmt in body:
                if isinstance(stmt, Assign) and isinstance(stmt.target, Name):
                    add(stmt.target.name, stmt.line)
                elif isinstance(stmt, For):
                    add(stmt.name, stmt.line)
                    walk(stmt.body)
                elif isinstance(stmt, If):
                    walk(stmt.body)
                    for _, b in stmt.elifs:
                        walk(b)
                    if stmt.else_body:
                        walk(stmt.else_body)
                elif isinstance(stmt, While):
                    walk(stmt.body)
                elif isinstance(stmt, Func):
                    raise TPyError("nested-func", stmt.line)

        walk(stmts)
        temps = self._count_fors(stmts)
        return locals_, temps

    def _count_fors(self, stmts) -> int:
        n = 0
        for stmt in stmts:
            if isinstance(stmt, For):
                n += 2 + self._count_fors(stmt.body)
            elif isinstance(stmt, If):
                n += self._count_fors(stmt.body)
                for _, b in stmt.elifs:
                    n += self._count_fors(b)
                if stmt.else_body:
                    n += self._count_fors(stmt.else_body)
            elif isinstance(stmt, While):
                n += self._count_fors(stmt.body)
        return n

    def _emit_function(self, label, params, body, declared_globals=None, extra_locals=0, force_global=False):
        declared_globals = set(declared_globals or [])
        locals_, temps = self._scan_locals(body, params, declared_globals)
        if force_global:
            locals_ = []
            temps = self._count_fors(body)
        total = len(locals_) + temps
        self.local_off = {}
        off = 4
        for name in locals_:
            self.local_off[name] = off
            off += 4
        self.temp_base = off
        self.temp_used = 0
        self.temp_max = temps
        self.locals_set = set(locals_)
        self.declared_globals = declared_globals
        self.force_global = force_global
        self.local_types = {name: ANY for name in locals_}
        for i, p in enumerate(params):
            self.local_types[p] = ANY
        self.epilogue = self.lab("ret")
        self.loops = []
        self.a(f"{label}:")
        self.a("    ADDI SP, SP, -8")
        self.a("    STR LR, SP, 4")
        self.a("    STR FP, SP, 0")
        self.a("    MOV FP, SP")
        if total:
            self.a(f"    ADDI SP, SP, {-4 * total}")
        for i, name in enumerate(params):
            self.a(f"    STR R{i + 1}, FP, {-self.local_off[name]}")
        self._body(body)
        if label == "generated_init":
            self.a("    BL user__init")
        self.a("    ADDI R1, R0, 0")
        self.a(f"{self.epilogue}:")
        self.a("    MOV SP, FP")
        self.a("    LDR FP, SP, 0")
        self.a("    LDR LR, SP, 4")
        self.a("    ADDI SP, SP, 8")
        self.a("    JR LR")

    def _alloc_temp(self) -> str:
        if self.temp_used >= self.temp_max:
            raise TPyError("temps", 1)
        off = self.temp_base + self.temp_used * 4
        self.temp_used += 1
        name = f"@t{off}"
        self.local_off[name] = off
        return name

    def _body(self, stmts) -> None:
        for stmt in stmts:
            self._stmt(stmt)

    def _stmt(self, stmt) -> None:
        self.a(f"    # line {getattr(stmt, 'line', 0)}")
        if isinstance(stmt, Pass) or isinstance(stmt, Global):
            self.a("    NOP")
            return
        if isinstance(stmt, ExprStmt):
            self._expr(stmt.expr)
            self.pop("R1")
            return
        if isinstance(stmt, Assign):
            self._assign(stmt)
            return
        if isinstance(stmt, If):
            self._if(stmt)
            return
        if isinstance(stmt, While):
            self._while(stmt)
            return
        if isinstance(stmt, For):
            self._for(stmt)
            return
        if isinstance(stmt, Return):
            if stmt.value is None:
                self.a("    ADDI R1, R0, 0")
            else:
                self._expr(stmt.value)
                self.pop("R1")
            self.a(f"    B {self.epilogue}")
            return
        if isinstance(stmt, Break):
            if not self.loops:
                raise TPyError("break-outside", stmt.line)
            self.a(f"    B {self.loops[-1][1]}")
            return
        if isinstance(stmt, Continue):
            if not self.loops:
                raise TPyError("continue-outside", stmt.line)
            self.a(f"    B {self.loops[-1][0]}")
            return
        if isinstance(stmt, Func):
            raise TPyError("nested-func", stmt.line)
        raise TPyError("uncompiled", getattr(stmt, "line", 1))

    def _assign(self, stmt: Assign) -> None:
        if isinstance(stmt.target, Name):
            self._expr(stmt.value)
            self.pop("R1")
            self._store(stmt.target.name, "R1", stmt.line)
            self._set_type(stmt.target.name, self._type_of(stmt.value))
            return
        if isinstance(stmt.target, Index):
            self._expr(stmt.target.obj)
            self._expr(stmt.target.index)
            self._expr(stmt.value)
            self.pop("R3")
            self.pop("R2")
            self.pop("R1")
            self.a("    BL fn_list_set")
            return
        raise TPyError("bad-store", stmt.line)

    def _if(self, stmt: If) -> None:
        end = self.lab("endif")
        self._branch_if_false(stmt.cond, nxt := self.lab("else"))
        self._body(stmt.body)
        self.a(f"    B {end}")
        self.a(f"{nxt}:")
        for cond, body in stmt.elifs:
            nxt = self.lab("elif")
            self._branch_if_false(cond, nxt)
            self._body(body)
            self.a(f"    B {end}")
            self.a(f"{nxt}:")
        if stmt.else_body:
            self._body(stmt.else_body)
        self.a(f"{end}:")

    def _while(self, stmt: While) -> None:
        start = self.lab("while")
        end = self.lab("wend")
        self.a(f"{start}:")
        self.loops.append((start, end))
        self._branch_if_false(stmt.cond, end)
        self._body(stmt.body)
        self.a(f"    B {start}")
        self.a(f"{end}:")
        self.loops.pop()

    def _for(self, stmt: For) -> None:
        args = list(stmt.args)
        if len(args) == 1:
            start_e, stop_e, step_e = Num(0, stmt.line), args[0], Num(1, stmt.line)
        elif len(args) == 2:
            start_e, stop_e, step_e = args[0], args[1], Num(1, stmt.line)
        else:
            start_e, stop_e, step_e = args
        self._expr(start_e)
        self.pop("R1")
        self._store(stmt.name, "R1", stmt.line)
        self._set_type(stmt.name, INT)
        stop_t = self._alloc_temp()
        step_t = self._alloc_temp()
        self._expr(stop_e)
        self.pop("R1")
        self._store_local(stop_t, "R1")
        self._expr(step_e)
        self.pop("R1")
        self._store_local(step_t, "R1")
        loop = self.lab("for")
        cont = self.lab("forc")
        end = self.lab("fore")
        self.a(f"{loop}:")
        self.loops.append((cont, end))
        # if step >= 0: break when i >= stop else break when i <= stop
        self._load_local(step_t, "R1")
        self.a("    CMP R1, R0")
        neg = self.lab("forneg")
        done_cmp = self.lab("forcmp")
        self.a(f"    BLT {neg}")
        self._load(stmt.name, "R1")
        self._load_local(stop_t, "R2")
        self.a("    CMP R1, R2")
        self.a(f"    BGE {end}")
        self.a(f"    B {done_cmp}")
        self.a(f"{neg}:")
        self._load(stmt.name, "R1")
        self._load_local(stop_t, "R2")
        self.a("    CMP R1, R2")
        self.a(f"    BLE {end}")
        self.a(f"{done_cmp}:")
        # step == 0 faults softly by ending the loop
        self._load_local(step_t, "R1")
        self.a("    CMP R1, R0")
        self.a(f"    BEQ {end}")
        self._body(stmt.body)
        self.a(f"{cont}:")
        self._load(stmt.name, "R1")
        self._load_local(step_t, "R2")
        self.a("    ADD R1, R1, R2")
        self._store(stmt.name, "R1", stmt.line)
        self.a(f"    B {loop}")
        self.a(f"{end}:")
        self.loops.pop()

    def _branch_if_false(self, cond, label: str) -> None:
        self._expr(cond)
        self.pop("R1")
        self.a("    CMP R1, R0")
        self.a(f"    BEQ {label}")

    def _expr(self, node) -> None:
        if isinstance(node, Num):
            self.a(f"    LI R1, {node.value & 0xFFFFFFFF if node.value < 0 else node.value}")
            # negative values: assembler LI accepts signed ints
            if node.value < 0:
                self.lines[-1] = f"    LI R1, {node.value}"
            self.push("R1")
            return
        if isinstance(node, Str):
            lab = self._string(node.value)
            self.a(f"    LI R1, {lab}")
            self.push("R1")
            return
        if isinstance(node, Name):
            self._load(node.name, "R1")
            self.push("R1")
            return
        if isinstance(node, ListLit):
            self.a(f"    ADDI R1, R0, {len(node.elts)}")
            self.a("    BL fn_list_new")
            self.push("R1")
            for i, elt in enumerate(node.elts):
                self._expr(elt)
                self.pop("R3")
                self.pop("R1")
                self.push("R1")
                self.a(f"    ADDI R2, R0, {i}")
                self.a("    BL fn_list_set")
            return
        if isinstance(node, Index):
            self._expr(node.obj)
            self._expr(node.index)
            self.pop("R2")
            self.pop("R1")
            self.a("    BL fn_list_get")
            self.push("R1")
            return
        if isinstance(node, Call):
            self._call(node)
            return
        if isinstance(node, Unary):
            self._expr(node.value)
            self.pop("R1")
            if node.op == "-":
                self.a("    SUB R1, R0, R1")
            elif node.op == "~":
                self.a("    MVN R1, R1")
            elif node.op == "not":
                yes = self.lab("not")
                end = self.lab("notd")
                self.a("    CMP R1, R0")
                self.a(f"    BEQ {yes}")
                self.a("    ADDI R1, R0, 0")
                self.a(f"    B {end}")
                self.a(f"{yes}:")
                self.a("    ADDI R1, R0, 1")
                self.a(f"{end}:")
            self.push("R1")
            return
        if isinstance(node, Bin):
            self._bin(node)
            return
        raise TPyError("bad-expr", getattr(node, "line", 1))

    def _bin(self, node: Bin) -> None:
        if node.op == "and":
            end = self.lab("and")
            self._expr(node.left)
            self.pop("R1")
            self.push("R1")
            self.a("    CMP R1, R0")
            self.a(f"    BEQ {end}")
            self.pop("R1")
            self._expr(node.right)
            self.a(f"{end}:")
            return
        if node.op == "or":
            end = self.lab("or")
            self._expr(node.left)
            self.pop("R1")
            self.push("R1")
            self.a("    CMP R1, R0")
            self.a(f"    BNE {end}")
            self.pop("R1")
            self._expr(node.right)
            self.a(f"{end}:")
            return
        self._expr(node.left)
        self._expr(node.right)
        self.pop("R2")
        self.pop("R1")
        op = node.op
        if op == "+":
            lt, rt = self._type_of(node.left), self._type_of(node.right)
            if lt == INT and rt == INT:
                self.a("    ADD R1, R1, R2")
            else:
                self.a("    BL fn_concat")
        elif op == "-":
            self.a("    SUB R1, R1, R2")
        elif op == "*":
            self.a("    MUL R1, R1, R2")
        elif op == "//":
            self.a("    BL fn_floordiv")
        elif op == "%":
            self.a("    BL fn_mod")
        elif op == "&":
            self.a("    AND R1, R1, R2")
        elif op == "|":
            self.a("    OR R1, R1, R2")
        elif op == "^":
            self.a("    XOR R1, R1, R2")
        elif op == "<<":
            self.a("    SHL R1, R1, R2")
        elif op == ">>":
            self.a("    SAR R1, R1, R2")
        elif op in ("==", "!=", "<", ">", "<=", ">="):
            branch = {"==": "BEQ", "!=": "BNE", "<": "BLT", ">": "BGT", "<=": "BLE", ">=": "BGE"}[op]
            yes = self.lab("cmp")
            end = self.lab("cmpd")
            self.a("    CMP R1, R2")
            self.a(f"    {branch} {yes}")
            self.a("    ADDI R1, R0, 0")
            self.a(f"    B {end}")
            self.a(f"{yes}:")
            self.a("    ADDI R1, R0, 1")
            self.a(f"{end}:")
        else:
            raise TPyError("no-op", node.line, op=op)
        self.push("R1")

    def _call(self, node: Call) -> None:
        args = list(node.args)
        if node.name in self.funcs:
            fn = self.funcs[node.name]
            if len(args) != len(fn.params):
                raise TPyError(
                    "arity",
                    node.line,
                    name=node.name,
                    need=len(fn.params),
                    got=len(args),
                )
            if len(args) > 6:
                raise TPyError("max-args", node.line)
            label = "user__" + node.name[1:] if node.name in ("_init", "_update", "_draw") else "uf_" + node.name
        elif node.name in SIGS:
            lo, hi, pad = SIGS[node.name]
            if not lo <= len(args) <= hi:
                raise TPyError("bad-argc", node.line, name=node.name)
            while len(args) < hi and pad:
                # pad only the missing tail
                break
            missing = hi - len(args)
            if missing:
                if len(pad) < missing:
                    raise TPyError("not-enough-args", node.line, name=node.name)
                for value in pad[-missing:]:
                    args.append(Num(value, node.line))
            label = BUILTIN_FN[node.name]
        else:
            raise TPyError("unknown-name", node.line, name=node.name)
        if len(args) > 6:
            raise TPyError("max-args", node.line)
        for arg in args:
            self._expr(arg)
        regs = ["R1", "R2", "R3", "R4", "R5", "R6"]
        for i in range(len(args) - 1, -1, -1):
            self.pop(regs[i])
        self.a(f"    BL {label}")
        self.push("R1")

    def _type_of(self, node) -> str:
        if isinstance(node, Num):
            return INT
        if isinstance(node, Str):
            return STR_
        if isinstance(node, ListLit):
            return LIST
        if isinstance(node, Name):
            if node.name in self.local_types and node.name in self.locals_set and not self.force_global:
                return self.local_types.get(node.name, ANY)
            return self.global_types.get(node.name, ANY)
        if isinstance(node, Bin) and node.op == "+" :
            lt, rt = self._type_of(node.left), self._type_of(node.right)
            if lt == STR_ or rt == STR_:
                return STR_
            if lt == INT and rt == INT:
                return INT
            return ANY
        if isinstance(node, Call) and node.name == "list":
            return LIST
        return INT if not isinstance(node, Call) else INT

    def _set_type(self, name: str, typ: str) -> None:
        if name in self.locals_set and not self.force_global and name not in self.declared_globals:
            self.local_types[name] = typ
        else:
            self.global_types[name] = typ

    def _store(self, name: str, reg: str, line: int) -> None:
        if name in BUILTIN_FN and name not in self.locals_set and name not in self.globals and name not in self.declared_globals:
            # assigning to a builtin name creates a global/local shadow, which is allowed
            pass
        if (name in self.locals_set) and not self.force_global and name not in self.declared_globals:
            self._store_local(name, reg)
            return
        addr = self._ensure_global(name)
        self.a(f"    LI R11, {addr}")
        self.a(f"    STR {reg}, R11, 0")

    def _load(self, name: str, reg: str) -> None:
        if name in self.funcs and name not in self.locals_set and name not in self.globals:
            raise TPyError("func-as-value", 1, name=name)
        if (name in self.locals_set) and not self.force_global and name not in self.declared_globals:
            self._load_local(name, reg)
            return
        if name not in self.globals and name not in self.local_off:
            self._ensure_global(name)
        if name in self.local_off and not self.force_global and name not in self.declared_globals:
            self._load_local(name, reg)
            return
        addr = self._ensure_global(name)
        self.a(f"    LI R11, {addr}")
        self.a(f"    LDR {reg}, R11, 0")

    def _store_local(self, name: str, reg: str) -> None:
        self.a(f"    STR {reg}, FP, {-self.local_off[name]}")

    def _load_local(self, name: str, reg: str) -> None:
        self.a(f"    LDR {reg}, FP, {-self.local_off[name]}")

    def push(self, reg: str) -> None:
        self.a("    ADDI SP, SP, -4")
        self.a(f"    STR {reg}, SP, 0")

    def pop(self, reg: str) -> None:
        self.a(f"    LDR {reg}, SP, 0")
        self.a("    ADDI SP, SP, 4")

    def _string(self, text: str) -> str:
        self.str_id += 1
        lab = f"str_{self.str_id}"
        data = ",".join(str(b) for b in text.encode("utf-8"))
        self.rodata.append("    .align 4")
        self.rodata.append(f"{lab}:")
        self.rodata.append(f"    .dw {STR_MAGIC}")
        self.rodata.append(f"    .dw {len(text.encode('utf-8'))}")
        if data:
            self.rodata.append(f"    .db {data}")
        self.rodata.append("    .db 0")
        self.rodata.append("    .align 4")
        return lab


def compile_source(source: str) -> str:
    return Compiler().compile(source)
