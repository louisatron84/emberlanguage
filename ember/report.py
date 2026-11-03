"""Renders an EmberError the way a person wants to read it:

    error: can't add a number and text
     --> calc.em:2:17
      |
    2 |     let x = 5 + "hi"
      |                 ^^^^
      = help: turn one side into the other's type first
"""

from ember.errors import EmberError


def render(error: EmberError, source: str, filename: str) -> str:
    lines = source.split("\n")
    text = lines[error.line - 1].rstrip("\r") if 1 <= error.line <= len(lines) else ""
    text = text.replace("\t", " ")  # one column per character keeps the caret lined up

    number = str(error.line)
    pad = " " * len(number)
    start = max(error.col, 1)
    room = max(len(text) - start + 1, 1)
    carets = "^" * max(1, min(error.length, room))

    out = [
        f"error: {error.message}",
        f"{pad}--> {filename}:{error.line}:{error.col}",
        f"{pad} |",
        f"{number} | {text}",
        f"{pad} | {' ' * (start - 1)}{carets}",
    ]
    if error.hint:
        out.append(f"{pad} = help: {error.hint}")
    return "\n".join(out)
