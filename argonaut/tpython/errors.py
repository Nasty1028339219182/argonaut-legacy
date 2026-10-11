"""Errors that point at a source line."""


class TPyError(Exception):
    def __init__(self, message: str, line: int = 1) -> None:
        self.line = line
        super().__init__(message)
