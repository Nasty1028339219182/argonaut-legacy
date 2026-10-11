"""Recursive-descent parser. Blocks are indentation, not braces."""

from __future__ import annotations

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
    Program,
    Return,
    Str,
    Unary,
    While,
)
from argonaut.tpython.errors import TPyError
from argonaut.tpython.lexer import Tok, lex


class Parser:
    def __init__(self, tokens: list[Tok]) -> None:
        self.toks = tokens
        self.i = 0

    def peek(self) -> Tok:
        return self.toks[self.i]

    def check(self, kind: str) -> bool:
        return self.peek().kind == kind

    def accept(self, kind: str) -> Tok | None:
        if self.check(kind):
            tok = self.peek()
            self.i += 1
            return tok
        return None

    def expect(self, kind: str) -> Tok:
        tok = self.accept(kind)
        if tok is None:
            got = self.peek()
            raise TPyError(f"ожидалось {kind}, а тут {got.kind}", got.line or 1)
        return tok

    def parse(self) -> Program:
        stmts = []
        while not self.check("EOF"):
            if self.accept("NEWLINE"):
                continue
            if self.check("DEDENT"):
                raise TPyError("лишний отступ", self.peek().line or 1)
            stmts.append(self.statement())
        return Program(stmts)

    def block(self) -> list:
        self.expect("NEWLINE")
        if not self.accept("INDENT"):
            raise TPyError("нужен отступ; пустой блок пишите как pass", self.peek().line or 1)
        stmts = []
        while not self.check("DEDENT") and not self.check("EOF"):
            if self.accept("NEWLINE"):
                continue
            stmts.append(self.statement())
        self.expect("DEDENT")
        return stmts

    def statement(self):
        if self.accept("IF"):
            return self.if_stmt()
        if self.accept("WHILE"):
            return self.while_stmt()
        if self.accept("FOR"):
            return self.for_stmt()
        if self.accept("DEF"):
            return self.def_stmt()
        if self.accept("RETURN"):
            return self.return_stmt()
        if self.accept("GLOBAL"):
            return self.global_stmt()
        if tok := self.accept("PASS"):
            self.expect("NEWLINE")
            return Pass(tok.line)
        if tok := self.accept("BREAK"):
            self.expect("NEWLINE")
            return Break(tok.line)
        if tok := self.accept("CONTINUE"):
            self.expect("NEWLINE")
            return Continue(tok.line)
        expr = self.expr()
        if self.accept("EQ"):
            if not isinstance(expr, (Name, Index)):
                raise TPyError("слева от = нужно имя или элемент списка", expr.line)
            value = self.expr()
            self.expect("NEWLINE")
            return Assign(expr, value, expr.line)
        self.expect("NEWLINE")
        return ExprStmt(expr, expr.line)

    def if_stmt(self) -> If:
        line = self.toks[self.i - 1].line
        cond = self.expr()
        self.expect("COLON")
        body = self.block()
        elifs = []
        while self.accept("ELIF"):
            econd = self.expr()
            self.expect("COLON")
            ebody = self.block()
            elifs.append((econd, ebody))
        else_body = None
        if self.accept("ELSE"):
            self.expect("COLON")
            else_body = self.block()
        return If(cond, body, elifs, else_body, line)

    def while_stmt(self) -> While:
        line = self.toks[self.i - 1].line
        cond = self.expr()
        self.expect("COLON")
        body = self.block()
        return While(cond, body, line)

    def for_stmt(self) -> For:
        line = self.toks[self.i - 1].line
        name = self.expect("NAME")
        self.expect("IN")
        self.expect("RANGE")
        self.expect("LPAREN")
        args = [self.expr()]
        while self.accept("COMMA"):
            if self.check("RPAREN"):
                break
            args.append(self.expr())
        if len(args) > 3:
            raise TPyError("у range максимум три аргумента", line)
        self.expect("RPAREN")
        self.expect("COLON")
        body = self.block()
        return For(name.text, args, body, line)

    def def_stmt(self) -> Func:
        line = self.toks[self.i - 1].line
        name = self.expect("NAME")
        self.expect("LPAREN")
        params = []
        if not self.check("RPAREN"):
            params.append(self.expect("NAME").text)
            while self.accept("COMMA"):
                if self.check("RPAREN"):
                    break
                params.append(self.expect("NAME").text)
        self.expect("RPAREN")
        if len(params) > 6:
            raise TPyError("не больше 6 аргументов", line)
        self.expect("COLON")
        body = self.block()
        return Func(name.text, params, body, line)

    def return_stmt(self) -> Return:
        line = self.toks[self.i - 1].line
        if self.accept("NEWLINE"):
            return Return(None, line)
        value = self.expr()
        self.expect("NEWLINE")
        return Return(value, line)

    def global_stmt(self) -> Global:
        line = self.toks[self.i - 1].line
        names = [self.expect("NAME").text]
        while self.accept("COMMA"):
            names.append(self.expect("NAME").text)
        self.expect("NEWLINE")
        return Global(names, line)

    def expr(self):
        return self.or_expr()

    def or_expr(self):
        left = self.and_expr()
        while self.accept("OR"):
            line = self.toks[self.i - 1].line
            right = self.and_expr()
            left = Bin("or", left, right, line)
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.accept("AND"):
            line = self.toks[self.i - 1].line
            right = self.not_expr()
            left = Bin("and", left, right, line)
        return left

    def not_expr(self):
        if tok := self.accept("NOT"):
            return Unary("not", self.not_expr(), tok.line)
        return self.cmp_expr()

    def cmp_expr(self):
        left = self.bor_expr()
        kinds = ("EQEQ", "NE", "LT", "GT", "LE", "GE")
        for kind in kinds:
            if tok := self.accept(kind):
                right = self.bor_expr()
                return Bin(tok.text, left, right, tok.line)
        return left

    def bor_expr(self):
        left = self.bxor_expr()
        while tok := self.accept("PIPE"):
            right = self.bxor_expr()
            left = Bin("|", left, right, tok.line)
        return left

    def bxor_expr(self):
        left = self.band_expr()
        while tok := self.accept("CARET"):
            right = self.band_expr()
            left = Bin("^", left, right, tok.line)
        return left

    def band_expr(self):
        left = self.shift_expr()
        while tok := self.accept("AMP"):
            right = self.shift_expr()
            left = Bin("&", left, right, tok.line)
        return left

    def shift_expr(self):
        left = self.add_expr()
        while True:
            if tok := self.accept("LSHIFT"):
                right = self.add_expr()
                left = Bin("<<", left, right, tok.line)
            elif tok := self.accept("RSHIFT"):
                right = self.add_expr()
                left = Bin(">>", left, right, tok.line)
            else:
                break
        return left

    def add_expr(self):
        left = self.mul_expr()
        while True:
            if tok := self.accept("PLUS"):
                right = self.mul_expr()
                left = Bin("+", left, right, tok.line)
            elif tok := self.accept("MINUS"):
                right = self.mul_expr()
                left = Bin("-", left, right, tok.line)
            else:
                break
        return left

    def mul_expr(self):
        left = self.unary()
        while True:
            if tok := self.accept("STAR"):
                right = self.unary()
                left = Bin("*", left, right, tok.line)
            elif tok := self.accept("FLOORDIV"):
                right = self.unary()
                left = Bin("//", left, right, tok.line)
            elif tok := self.accept("PERCENT"):
                right = self.unary()
                left = Bin("%", left, right, tok.line)
            else:
                break
        return left

    def unary(self):
        if tok := self.accept("MINUS"):
            return Unary("-", self.unary(), tok.line)
        if tok := self.accept("PLUS"):
            return Unary("+", self.unary(), tok.line)
        if tok := self.accept("TILDE"):
            return Unary("~", self.unary(), tok.line)
        return self.primary()

    def primary(self):
        if tok := self.accept("NUMBER"):
            return Num(int(tok.value), tok.line)
        if tok := self.accept("STRING"):
            return Str(str(tok.value), tok.line)
        if tok := self.accept("NAME"):
            node: object = Name(tok.text, tok.line)
            while True:
                if self.accept("LPAREN"):
                    if not isinstance(node, Name):
                        raise TPyError("вызов только по имени функции", tok.line)
                    args = self.arg_list()
                    self.expect("RPAREN")
                    node = Call(node.name, args, tok.line)
                elif self.accept("LBRACK"):
                    idx = self.expr()
                    self.expect("RBRACK")
                    node = Index(node, idx, tok.line)
                else:
                    break
            return node
        if self.accept("LPAREN"):
            expr = self.expr()
            self.expect("RPAREN")
            return expr
        if tok := self.accept("LBRACK"):
            elts = []
            if not self.check("RBRACK"):
                elts.append(self.expr())
                while self.accept("COMMA"):
                    if self.check("RBRACK"):
                        break
                    elts.append(self.expr())
            self.expect("RBRACK")
            return ListLit(elts, tok.line)
        tok = self.peek()
        raise TPyError(f"ожидалось выражение, а тут {tok.kind}", tok.line or 1)

    def arg_list(self) -> list:
        if self.check("RPAREN"):
            return []
        args = [self.expr()]
        while self.accept("COMMA"):
            if self.check("RPAREN"):
                break
            args.append(self.expr())
        return args


def parse(source: str) -> Program:
    return Parser(lex(source)).parse()
