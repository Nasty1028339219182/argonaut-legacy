"""TPython syntax tree. Nodes carry a source line."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Num:
    value: int
    line: int


@dataclass
class Str:
    value: str
    line: int


@dataclass
class Name:
    name: str
    line: int


@dataclass
class ListLit:
    elts: list
    line: int


@dataclass
class Index:
    obj: object
    index: object
    line: int


@dataclass
class Call:
    name: str
    args: list
    line: int


@dataclass
class Unary:
    op: str
    value: object
    line: int


@dataclass
class Bin:
    op: str
    left: object
    right: object
    line: int


@dataclass
class Assign:
    target: object
    value: object
    line: int


@dataclass
class ExprStmt:
    expr: object
    line: int


@dataclass
class If:
    cond: object
    body: list
    elifs: list
    else_body: list | None
    line: int


@dataclass
class While:
    cond: object
    body: list
    line: int


@dataclass
class For:
    name: str
    args: list
    body: list
    line: int


@dataclass
class Func:
    name: str
    params: list
    body: list
    line: int


@dataclass
class Return:
    value: object | None
    line: int


@dataclass
class Global:
    names: list
    line: int


@dataclass
class Pass:
    line: int


@dataclass
class Break:
    line: int


@dataclass
class Continue:
    line: int


@dataclass
class Program:
    stmts: list = field(default_factory=list)
