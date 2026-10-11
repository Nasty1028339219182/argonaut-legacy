"""Errors that point at a source line.

The message is an English key. The editor translates it when it is shown.
"""


class TPyError(Exception):
    def __init__(self, message: str, line: int = 1, **fmt) -> None:
        self.line = int(line or 1)
        self.key = message
        self.fmt = fmt
        super().__init__(message)
