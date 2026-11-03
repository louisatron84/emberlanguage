"""The syntax tree the parser produces.

Every node is frozen and carries a `span` (line, column, length) so any later stage can point an
error at exactly the right spot. `dump` renders a tree as compact text for tests and debugging.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    line: int
    col: int
    length: int = 1

    def to(self, other: "Span") -> "Span":
        """A span from the start of this one to the end of `other` (when they share a line)."""
        if other.line == self.line and other.col + other.length > self.col:
            return Span(self.line, self.col, other.col + other.length - self.col)
        return self


# ---- expressions -------------------------------------------------------------------------------

@dataclass(frozen=True)
class IntLit:
    value: int
    span: Span


@dataclass(frozen=True)
class FloatLit:
    value: float
    span: Span


@dataclass(frozen=True)
class StrLit:
    value: str
    span: Span


@dataclass(frozen=True)
class BoolLit:
    value: bool
    span: Span


@dataclass(frozen=True)
class Name:
    name: str
    span: Span


@dataclass(frozen=True)
class Unary:
    op: str  # "-" or "not"
    operand: "Expr"
    span: Span


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    span: Span


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple["Expr", ...]
    span: Span


@dataclass(frozen=True)
class Index:
    target: "Expr"
    index: "Expr"
    span: Span


Expr = IntLit | FloatLit | StrLit | BoolLit | Name | Unary | Binary | Call | Index


# ---- statements --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Declare:
    name: str
    mutable: bool  # `mut` is True, `let` is False
    value: Expr
    span: Span


@dataclass(frozen=True)
class Assign:
    name: str
    value: Expr
    span: Span


@dataclass(frozen=True)
class ExprStmt:
    expr: Expr
    span: Span


@dataclass(frozen=True)
class Return:
    value: Expr | None
    span: Span


@dataclass(frozen=True)
class If:
    branches: tuple[tuple[Expr, tuple["Stmt", ...]], ...]  # the `if` and every `elif`
    else_body: tuple["Stmt", ...] | None
    span: Span


@dataclass(frozen=True)
class While:
    condition: Expr
    body: tuple["Stmt", ...]
    span: Span


@dataclass(frozen=True)
class For:
    var: str
    start: Expr
    end: Expr
    body: tuple["Stmt", ...]
    span: Span


Stmt = Declare | Assign | ExprStmt | Return | If | While | For


# ---- top level ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeRef:
    name: str
    span: Span


@dataclass(frozen=True)
class Param:
    name: str
    type: TypeRef
    span: Span


@dataclass(frozen=True)
class FnDef:
    name: str
    params: tuple[Param, ...]
    return_type: TypeRef | None
    body: tuple[Stmt, ...]
    span: Span


@dataclass(frozen=True)
class Program:
    functions: tuple[FnDef, ...]


# ---- debugging / tests -------------------------------------------------------------------------

def dump(node) -> str:
    match node:
        case IntLit(value) | FloatLit(value):
            return str(value)
        case StrLit(value):
            return f'"{value}"'
        case BoolLit(value):
            return "true" if value else "false"
        case Name(name):
            return name
        case Unary(op, operand):
            return f"({op} {dump(operand)})"
        case Binary(op, left, right):
            return f"({op} {dump(left)} {dump(right)})"
        case Call(name, args):
            return "(call " + " ".join([name, *map(dump, args)]) + ")"
        case Index(target, index):
            return f"(index {dump(target)} {dump(index)})"
        case Declare(name, mutable, value):
            return f"({'mut' if mutable else 'let'} {name} {dump(value)})"
        case Assign(name, value):
            return f"(set {name} {dump(value)})"
        case ExprStmt(expr):
            return f"(expr {dump(expr)})"
        case Return(None):
            return "(return)"
        case Return(value):
            return f"(return {dump(value)})"
        case If(branches, else_body):
            parts = []
            for i, (condition, body) in enumerate(branches):
                parts += ["" if i == 0 else "elif", dump(condition), _block(body)]
            if else_body is not None:
                parts += ["else", _block(else_body)]
            return "(if " + " ".join(p for p in parts if p) + ")"
        case While(condition, body):
            return f"(while {dump(condition)} {_block(body)})"
        case For(var, start, end, body):
            return f"(for {var} {dump(start)} {dump(end)} {_block(body)})"
        case Param(name, type_):
            return f"{name}:{type_.name}"
        case FnDef(name, params, return_type, body):
            signature = "(" + " ".join(map(dump, params)) + ")"
            if return_type is not None:
                signature += f" -> {return_type.name}"
            return f"(fn {name} {signature} {_block(body)})"
        case Program(functions):
            return "\n".join(map(dump, functions))
    raise TypeError(f"can't dump {node!r}")


def _block(statements) -> str:
    return "{" + " ".join(map(dump, statements)) + "}"
