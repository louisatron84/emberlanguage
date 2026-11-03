"""Checks types, names and mutability, and works out the type of every expression.

The tree itself stays untouched; the result is a side table from each expression node to its type
("int", "float", "bool", "str", or "void" for calls that give nothing back). The C generator reads
that table instead of guessing.
"""

from dataclasses import dataclass, field
from difflib import get_close_matches

from ember import ast
from ember.errors import EmberError

TYPES = ("int", "float", "bool", "str")
NUMERIC = ("int", "float")
INT_MAX = 2**63 - 1

ARTICLE = {"int": "an `int`", "float": "a `float`", "bool": "a `bool`", "str": "a `str`", "void": "nothing"}
VERBS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide", "%": "take the remainder of"}


@dataclass(frozen=True)
class Signature:
    params: tuple[str, ...]
    returns: str  # "void" when the function gives nothing back


# `print` is special (it takes one value of any type), so it is handled in `_call`.
BUILTINS = {
    "print": None,
    "read_line": Signature((), "str"),
    "to_float": Signature(("str",), "float"),
    "len": Signature(("str",), "int"),
}


@dataclass
class Checked:
    program: ast.Program
    functions: dict[str, Signature]
    types: dict[int, str] = field(default_factory=dict)

    def type_of(self, node) -> str:
        return self.types[id(node)]


def check(program: ast.Program) -> Checked:
    return _Checker(program).run()


def fits(target: str, value: str) -> bool:
    """Can a value of type `value` go where `target` is expected? A whole number fits a float."""
    return target == value or (target == "float" and value == "int")


def _fail(message: str, span: ast.Span, hint: str | None = None):
    raise EmberError(message, span.line, span.col, span.length, hint)


def _suggest(name: str, candidates) -> str | None:
    match = get_close_matches(name, list(candidates), n=1, cutoff=0.6)
    return f"did you mean `{match[0]}`?" if match else None


@dataclass
class _Var:
    type: str
    kind: str  # "let", "mut", "param" or "loop"


class _Checker:
    def __init__(self, program: ast.Program):
        self.result = Checked(program, {})
        self.scopes: list[dict[str, _Var]] = []
        self.fn: ast.FnDef | None = None

    # ---- program and functions -----------------------------------------------------------------

    def run(self) -> Checked:
        program = self.result.program
        for fn in program.functions:
            self._declare_function(fn)
        main = next((fn for fn in program.functions if fn.name == "main"), None)
        if main is None:
            _fail("your program needs a `fn main():` to start from", ast.Span(1, 1),
                  hint="add `fn main():` with the code that should run first")
        if main.params or main.return_type is not None:
            _fail("`main` can't take parameters or return a value", main.span, hint="write it as `fn main():`")
        for fn in program.functions:
            self._function(fn)
        return self.result

    def _type(self, ref: ast.TypeRef) -> str:
        if ref.name not in TYPES:
            hint = _suggest(ref.name, TYPES) or "the types are int, float, bool and str"
            _fail(f"I don't know a type called `{ref.name}`", ref.span, hint)
        return ref.name

    def _declare_function(self, fn: ast.FnDef) -> None:
        if fn.name in BUILTINS:
            _fail(f"`{fn.name}` is built in to Ember, so you can't define your own", fn.span,
                  hint="give your function a different name")
        if fn.name in self.result.functions:
            _fail(f"there's already a function called `{fn.name}`", fn.span, hint="give one of them a different name")
        seen = set()
        for param in fn.params:
            if param.name in seen:
                _fail(f"`{fn.name}` already has a parameter called `{param.name}`", param.span)
            seen.add(param.name)
        params = tuple(self._type(p.type) for p in fn.params)
        returns = self._type(fn.return_type) if fn.return_type else "void"
        self.result.functions[fn.name] = Signature(params, returns)

    def _function(self, fn: ast.FnDef) -> None:
        self.fn = fn
        signature = self.result.functions[fn.name]
        self.scopes = [{p.name: _Var(t, "param") for p, t in zip(fn.params, signature.params)}]
        self._block(fn.body)
        if signature.returns != "void" and not _always_returns(fn.body):
            _fail(f"`{fn.name}` doesn't return a value on every path", fn.span,
                  hint=f"make sure every way through `{fn.name}` ends in a `return`")

    # ---- statements ----------------------------------------------------------------------------

    def _block(self, statements, extra: dict[str, _Var] | None = None) -> None:
        self.scopes.append(dict(extra or {}))
        for statement in statements:
            self._statement(statement)
        self.scopes.pop()

    def _lookup(self, name: str) -> _Var | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def _visible_names(self):
        return {name for scope in self.scopes for name in scope}

    def _new_name(self, name: str, span: ast.Span) -> None:
        if self._lookup(name) is not None:
            _fail(f"`{name}` already exists here", span,
                  hint=f"pick a different name, or change the existing one with `{name} = ...` if it's `mut`")

    def _statement(self, stmt: ast.Stmt) -> None:
        match stmt:
            case ast.Declare(name, mutable, value, span):
                value_type = self._value(value)
                self._new_name(name, span)
                self.scopes[-1][name] = _Var(value_type, "mut" if mutable else "let")
            case ast.Assign(name, value, span):
                self._assign(stmt, name, value, span)
            case ast.ExprStmt(expr):
                self._expr(expr)
            case ast.Return(value, span):
                self._return(value, span)
            case ast.If(branches, else_body):
                for i, (condition, body) in enumerate(branches):
                    self._condition(condition, "an `if`" if i == 0 else "an `elif`")
                    self._block(body)
                if else_body is not None:
                    self._block(else_body)
            case ast.While(condition, body):
                self._condition(condition, "a `while`")
                self._block(body)
            case ast.For(var, start, end, body, span):
                for bound in (start, end):
                    bound_type = self._value(bound)
                    if bound_type != "int":
                        _fail(f"a range needs whole numbers (`int`), but this is {ARTICLE[bound_type]}", bound.span)
                self._new_name(var, span)
                self._block(body, {var: _Var("int", "loop")})

    def _assign(self, stmt: ast.Assign, name: str, value: ast.Expr, span: ast.Span) -> None:
        var = self._lookup(name)
        if var is None:
            _fail(f"I can't find a variable called `{name}`", span,
                  _suggest(name, self._visible_names()) or f"create it first with `mut {name} = ...`")
        if var.kind != "mut":
            hints = {
                "let": f"declare it with `mut {name} = ...` instead of `let` if it needs to change",
                "param": f"parameters can't change; copy it first with `mut my_{name} = {name}`",
                "loop": "the loop counter can't change; use a `while` loop if you need to control it",
            }
            _fail(f"`{name}` isn't `mut`, so you can't change it here", span, hints[var.kind])
        value_type = self._value(value)
        if not fits(var.type, value_type):
            hint = f"start it as a float, like `mut {name} = 0.0`" if var.type == "int" and value_type == "float" else None
            _fail(f"`{name}` holds {ARTICLE[var.type]}, so it can't be given {ARTICLE[value_type]}", value.span, hint)
        self.result.types[id(stmt)] = var.type

    def _return(self, value: ast.Expr | None, span: ast.Span) -> None:
        returns = self.result.functions[self.fn.name].returns
        if value is None:
            if returns != "void":
                _fail(f"`{self.fn.name}` must return {ARTICLE[returns]}", span)
            return
        value_type = self._value(value)
        if returns == "void":
            _fail(f"`{self.fn.name}` doesn't return anything, so this `return` can't have a value", value.span,
                  hint=f"add `-> {value_type}` to the end of the `fn {self.fn.name}(...)` line")
        if not fits(returns, value_type):
            _fail(f"`{self.fn.name}` should return {ARTICLE[returns]}, but this is {ARTICLE[value_type]}", value.span)

    def _condition(self, condition: ast.Expr, owner: str) -> None:
        condition_type = self._value(condition)
        if condition_type != "bool":
            hint = "compare it to something, like `x != 0`" if condition_type in NUMERIC else None
            _fail(f"the condition of {owner} must be true or false (a `bool`), but this is {ARTICLE[condition_type]}",
                  condition.span, hint)

    # ---- expressions ---------------------------------------------------------------------------

    def _value(self, expr: ast.Expr) -> str:
        """Check an expression that must produce something."""
        expr_type = self._expr(expr)
        if expr_type == "void":
            _fail(f"`{expr.name}(...)` doesn't give back a value, so it can't be used here", expr.span)
        return expr_type

    def _expr(self, expr: ast.Expr) -> str:
        expr_type = self._infer(expr)
        self.result.types[id(expr)] = expr_type
        return expr_type

    def _infer(self, expr: ast.Expr) -> str:
        match expr:
            case ast.IntLit(value, span):
                if value > INT_MAX:
                    _fail("this number is too big for an `int`", span, hint=f"the biggest `int` is {INT_MAX}")
                return "int"
            case ast.FloatLit():
                return "float"
            case ast.StrLit():
                return "str"
            case ast.BoolLit():
                return "bool"
            case ast.Name(name, span):
                var = self._lookup(name)
                if var is None:
                    if name in self.result.functions or name in BUILTINS:
                        _fail(f"`{name}` is a function, not a variable", span, hint=f"call it like `{name}(...)`")
                    _fail(f"I can't find a variable called `{name}`", span, _suggest(name, self._visible_names()))
                return var.type
            case ast.Unary(op, operand, span):
                operand_type = self._value(operand)
                if op == "not" and operand_type != "bool":
                    _fail(f"`not` needs true or false (a `bool`), but this is {ARTICLE[operand_type]}", span)
                if op == "-" and operand_type not in NUMERIC:
                    _fail(f"`-` needs a number, but this is {ARTICLE[operand_type]}", span)
                return operand_type
            case ast.Binary(op, left, right, span):
                return self._binary(op, self._value(left), self._value(right), span)
            case ast.Call():
                return self._call(expr)
            case ast.Index(target, index, span):
                target_type = self._value(target)
                if target_type != "str":
                    _fail(f"only text (a `str`) can be indexed with `[...]`, but this is {ARTICLE[target_type]}", span)
                index_type = self._value(index)
                if index_type != "int":
                    _fail(f"a position in text must be an `int`, but this is {ARTICLE[index_type]}", index.span)
                return "str"
        raise TypeError(f"unknown expression {expr!r}")

    def _binary(self, op: str, left: str, right: str, span: ast.Span) -> str:
        both_numbers = left in NUMERIC and right in NUMERIC
        if op in ("and", "or"):
            for side, side_type in (("left", left), ("right", right)):
                if side_type != "bool":
                    _fail(f"`{op}` needs true or false on both sides, but the {side} side is {ARTICLE[side_type]}", span)
            return "bool"
        if op in ("==", "!="):
            if left != right and not both_numbers:
                _fail(f"can't compare {ARTICLE[left]} with {ARTICLE[right]}", span)
            return "bool"
        if op in ("<", "<=", ">", ">="):
            if not (both_numbers or left == right == "str"):
                _fail(f"can't put {ARTICLE[left]} and {ARTICLE[right]} in order with `{op}`", span,
                      hint="`<` and friends work on two numbers or two pieces of text")
            return "bool"
        if op == "+" and left == right == "str":
            return "str"
        if not both_numbers:
            hint = "`+` works on two numbers, or on two pieces of text" if op == "+" else None
            _fail(f"can't {VERBS[op]} {ARTICLE[left]} and {ARTICLE[right]}", span, hint)
        if op == "/":
            return "float"
        return "int" if left == right == "int" else "float"

    def _call(self, call: ast.Call) -> str:
        if call.name == "print":
            if len(call.args) != 1:
                _fail(f"`print` takes exactly one value, but was given {len(call.args)}", call.span,
                      hint="print each value with its own `print(...)`")
            self._value(call.args[0])
            return "void"
        signature = BUILTINS.get(call.name) or self.result.functions.get(call.name)
        if signature is None:
            if self._lookup(call.name) is not None:
                _fail(f"`{call.name}` is a variable, not a function", call.span)
            known = [*BUILTINS, *self.result.functions]
            _fail(f"I can't find a function called `{call.name}`", call.span, _suggest(call.name, known))
        if len(call.args) != len(signature.params):
            wanted = len(signature.params)
            _fail(f"`{call.name}` takes {wanted} argument{'s' * (wanted != 1)}, but was given {len(call.args)}",
                  call.span)
        for number, (arg, param_type) in enumerate(zip(call.args, signature.params), start=1):
            arg_type = self._value(arg)
            if not fits(param_type, arg_type):
                _fail(f"argument {number} of `{call.name}` should be {ARTICLE[param_type]}, but this is {ARTICLE[arg_type]}",
                      arg.span)
        return signature.returns


def _always_returns(statements) -> bool:
    for statement in statements:
        if isinstance(statement, ast.Return):
            return True
        if isinstance(statement, ast.If) and statement.else_body is not None:
            bodies = [body for _, body in statement.branches] + [statement.else_body]
            if all(_always_returns(body) for body in bodies):
                return True
    return False
