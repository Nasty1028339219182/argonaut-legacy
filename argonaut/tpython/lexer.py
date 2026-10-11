"""Indentation-aware lexer for TPython."""

from __future__ import annotations

from dataclasses import dataclass

from argonaut.tpython.errors import TPyError

KEYWORDS = {
    "def",
    "return",
    "if",
    "elif",
    "else",
    "while",
    "for",
    "in",
    "range",
    "global",
    "pass",
    "and",
    "or",
    "not",
    "break",
    "continue",
}


@dataclass
class Tok:
    kind: str
    line: int
    text: str = ""
    value: int | str | None = None


def _strip_comment(line: str) -> str:
    out = []
    i = 0
    quote = ""
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def lex(source: str) -> list[Tok]:
    source = source.replace("\t", "    ").replace("\r\n", "\n").replace("\r", "\n")
    if source and not source.endswith("\n"):
        source += "\n"
    indents = [0]
    tokens: list[Tok] = []
    for lineno, raw in enumerate(source.split("\n"), 1):
        code = _strip_comment(raw)
        if code.strip() == "":
            continue
        indent = len(code) - len(code.lstrip(" "))
        if code[:indent].strip(" ") != "":
            raise TPyError("отступ только пробелами", lineno)
        if indent > indents[-1]:
            indents.append(indent)
            tokens.append(Tok("INDENT", lineno))
        else:
            while indent < indents[-1]:
                indents.pop()
                tokens.append(Tok("DEDENT", lineno))
            if indent != indents[-1]:
                raise TPyError("сбитый отступ", lineno)
        _lex_line(code[indent:], lineno, tokens)
        tokens.append(Tok("NEWLINE", lineno))
    while len(indents) > 1:
        indents.pop()
        tokens.append(Tok("DEDENT", 0))
    tokens.append(Tok("EOF", 0))
    return tokens


def _lex_line(text: str, line: int, out: list[Tok]) -> None:
    i = 0
    n = len(text)
    two = {
        "==": "EQEQ",
        "!=": "NE",
        "<=": "LE",
        ">=": "GE",
        "//": "FLOORDIV",
        "<<": "LSHIFT",
        ">>": "RSHIFT",
    }
    while i < n:
        ch = text[i]
        if ch == " ":
            i += 1
            continue
        if ch == "/" and (i + 1 >= n or text[i + 1] != "/"):
            raise TPyError("в TPython нет дробей: используйте //", line)
        if i + 1 < n and text[i : i + 2] in two:
            kind = two[text[i : i + 2]]
            out.append(Tok(kind, line, text[i : i + 2]))
            i += 2
            continue
        if ch.isdigit():
            if text[i : i + 2].lower() == "0x":
                j = i + 2
                while j < n and text[j] in "0123456789abcdefABCDEF":
                    j += 1
                if j == i + 2:
                    raise TPyError("пустое шестнадцатеричное число", line)
                out.append(Tok("NUMBER", line, text[i:j], int(text[i:j], 16)))
                i = j
                continue
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] == ".":
                raise TPyError("в TPython нет дробей: используйте целые", line)
            out.append(Tok("NUMBER", line, text[i:j], int(text[i:j], 10)))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            if word in KEYWORDS:
                out.append(Tok(word.upper(), line, word))
            else:
                out.append(Tok("NAME", line, word))
            i = j
            continue
        if ch in ("'", '"'):
            j = i + 1
            buf = []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    esc = text[j + 1]
                    mapping = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", '"': '"', "0": "\0", "r": "\r"}
                    if esc not in mapping:
                        raise TPyError(f"неизвестное \\{esc}", line)
                    buf.append(mapping[esc])
                    j += 2
                    continue
                if text[j] == ch:
                    break
                buf.append(text[j])
                j += 1
            else:
                raise TPyError("строка не закрыта", line)
            out.append(Tok("STRING", line, "".join(buf), "".join(buf)))
            i = j + 1
            continue
        singles = {
            "+": "PLUS",
            "-": "MINUS",
            "*": "STAR",
            "%": "PERCENT",
            "(": "LPAREN",
            ")": "RPAREN",
            "[": "LBRACK",
            "]": "RBRACK",
            ":": "COLON",
            ",": "COMMA",
            "=": "EQ",
            "<": "LT",
            ">": "GT",
            "&": "AMP",
            "|": "PIPE",
            "^": "CARET",
            "~": "TILDE",
        }
        if ch in singles:
            out.append(Tok(singles[ch], line, ch))
            i += 1
            continue
        raise TPyError(f"непонятный символ {ch!r}", line)
