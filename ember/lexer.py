"""Turns Ember source text into a flat list of tokens.

Indentation becomes explicit INDENT / DEDENT tokens (the way Python does it), so the parser never
has to count spaces. Every token remembers where it came from, so later stages can point at the
exact spot in the source when something is wrong.
"""

from dataclasses import dataclass

from ember.errors import EmberError

KEYWORDS = {
    "fn": "FN", "let": "LET", "mut": "MUT", "return": "RETURN",
    "if": "IF", "elif": "ELIF", "else": "ELSE", "while": "WHILE", "for": "FOR", "in": "IN",
    "and": "AND", "or": "OR", "not": "NOT", "true": "TRUE", "false": "FALSE",
}

TWO_CHAR_OPERATORS = {"==", "!=", "<=", ">=", "->", ".."}
ONE_CHAR_OPERATORS = set("+-*/%<>=(),:[]")
OPENERS = {"(": ")", "[": "]"}

ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass(frozen=True)
class Token:
    kind: str       # "INT", "IDENT", "FN", "+", "NEWLINE", "INDENT", "EOF", ...
    value: str      # the source text (decoded for strings); empty for layout tokens
    line: int       # 1-based
    col: int        # 1-based
    length: int = 1


def lex(source: str) -> list[Token]:
    return _Lexer(source).run()


class _Lexer:
    def __init__(self, source: str):
        self.lines = source.split("\n")
        self.tokens: list[Token] = []
        self.indents = [0]
        self.open_parens: list[tuple[int, int, str]] = []  # (line, col, char) of each unclosed ( or [

    def run(self) -> list[Token]:
        for number, text in enumerate(self.lines, start=1):
            text = text.rstrip("\r")
            if not self.open_parens and not self._start_logical_line(number, text):
                continue
            emitted_before = len(self.tokens)
            self._scan_line(number, text)
            if not self.open_parens and len(self.tokens) > emitted_before:
                self.tokens.append(Token("NEWLINE", "", number, len(text) + 1, 0))

        if self.open_parens:
            line, col, opener = self.open_parens[-1]
            raise EmberError(
                f"this {opener} is never closed", line, col,
                hint=f"add a matching {OPENERS[opener]} before the end of the file",
            )

        last_line = len(self.lines)
        while len(self.indents) > 1:
            self.indents.pop()
            self.tokens.append(Token("DEDENT", "", last_line, 1, 0))
        self.tokens.append(Token("EOF", "", last_line, 1, 0))
        return self.tokens

    def _start_logical_line(self, number: int, text: str) -> bool:
        """Handle indentation. Returns False for blank and comment-only lines, which are skipped."""
        width = 0
        while width < len(text) and text[width] in " \t":
            if text[width] == "\t":
                raise EmberError(
                    "tabs can't be used for indentation", number, width + 1,
                    hint="indent with spaces instead (4 per level is the usual choice)",
                )
            width += 1
        rest = text[width:]
        if rest == "" or rest.startswith("#"):
            return False

        if width > self.indents[-1]:
            self.indents.append(width)
            self.tokens.append(Token("INDENT", "", number, 1, width))
        else:
            while width < self.indents[-1]:
                self.indents.pop()
                self.tokens.append(Token("DEDENT", "", number, 1, 0))
            if width != self.indents[-1]:
                raise EmberError(
                    "this line's indentation doesn't match any outer block", number, 1, width,
                    hint=f"the enclosing blocks are indented {self.indents[1:] or [0]} spaces; line this up with one of them",
                )
        return True

    def _scan_line(self, number: int, text: str) -> None:
        i = 0
        while i < len(text):
            c = text[i]
            col = i + 1
            if c in " \t":
                i += 1
            elif c == "#":
                return
            elif c.isdigit():
                i = self._number(number, text, i)
            elif c.isalpha() and c.isascii() or c == "_":
                start = i
                while i < len(text) and (text[i].isalnum() and text[i].isascii() or text[i] == "_"):
                    i += 1
                word = text[start:i]
                self.tokens.append(Token(KEYWORDS.get(word, "IDENT"), word, number, col, len(word)))
            elif c == '"':
                i = self._string(number, text, i)
            elif text[i:i + 2] in TWO_CHAR_OPERATORS:
                self.tokens.append(Token(text[i:i + 2], text[i:i + 2], number, col, 2))
                i += 2
            elif c in ONE_CHAR_OPERATORS:
                if c in OPENERS:
                    self.open_parens.append((number, col, c))
                elif c in OPENERS.values():
                    if not self.open_parens:
                        raise EmberError(f"this {c} has no matching opener", number, col)
                    open_line, _, opener = self.open_parens.pop()
                    if OPENERS[opener] != c:
                        raise EmberError(
                            f"this {c} doesn't match the {opener} opened on line {open_line}", number, col,
                            hint=f"close it with {OPENERS[opener]} instead",
                        )
                self.tokens.append(Token(c, c, number, col, 1))
                i += 1
            else:
                raise EmberError(f"I don't know what `{c}` means here", number, col)

    def _number(self, number: int, text: str, i: int) -> int:
        start = i
        while i < len(text) and text[i].isdigit():
            i += 1
        kind = "INT"
        # A dot only belongs to the number if a digit follows, so `0..10` stays a range.
        if i + 1 < len(text) and text[i] == "." and text[i + 1].isdigit():
            kind = "FLOAT"
            i += 1
            while i < len(text) and text[i].isdigit():
                i += 1
        self.tokens.append(Token(kind, text[start:i], number, start + 1, i - start))
        return i

    def _string(self, number: int, text: str, i: int) -> int:
        start = i
        i += 1
        chars: list[str] = []
        while i < len(text):
            c = text[i]
            if c == '"':
                self.tokens.append(Token("STRING", "".join(chars), number, start + 1, i + 1 - start))
                return i + 1
            if c == "\\":
                if i + 1 >= len(text) or text[i + 1] not in ESCAPES:
                    bad = text[i:i + 2]
                    raise EmberError(
                        f"I don't know the escape `{bad}`", number, i + 1, len(bad),
                        hint='the escapes are \\n, \\t, \\" and \\\\',
                    )
                chars.append(ESCAPES[text[i + 1]])
                i += 2
            else:
                chars.append(c)
                i += 1
        raise EmberError(
            "this string is never closed", number, start + 1,
            hint='add a closing " at the end of the string',
        )
