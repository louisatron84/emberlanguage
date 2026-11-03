"""The one error type every compiler stage raises.

It carries a position (line, column, length) so the error reporter can later underline the exact
spot in the source. Rendering lives in the reporter, not here.
"""

from dataclasses import dataclass


@dataclass
class EmberError(Exception):
    message: str
    line: int
    col: int
    length: int = 1
    hint: str | None = None

    def __str__(self) -> str:
        return f"{self.line}:{self.col}: {self.message}"
