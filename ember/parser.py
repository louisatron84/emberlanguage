"""Turns the lexer's tokens into a syntax tree (see ember/ast.py).

A recursive-descent parser: one method per grammar rule, and the expression rules are stacked from
loosest to tightest binding, so precedence falls out of the call order:

    or  <  and  <  not  <  comparison  <  + -  <  * / %  <  unary -  <  call / index
"""

from ember import ast
from ember.errors import EmberError
from ember.lexer import Token

COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


def parse(tokens: list[Token]) -> ast.Program:
    return _Parser(tokens).program()


def describe(token: Token) -> str:
    """How to name a token in an error message."""
    match token.kind:
        case "NEWLINE":
            return "the end of the line"
        case "INDENT":
            return "an indented line"
        case "DEDENT":
            return "the end of the block"
        case "EOF":
            return "the end of the file"
        case "INT" | "FLOAT":
            return f"the number `{token.value}`"
        case "STRING":
            return f'the text "{token.value}"'
        case _:
            return f"`{token.value}`"


def _span(token: Token) -> ast.Span:
    return ast.Span(token.line, token.col, token.length)


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # ---- helpers -------------------------------------------------------------------------------

    @property
    def tok(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        token = self.tok
        if token.kind != "EOF":
            self.pos += 1
        return token

    def accept(self, kind: str) -> Token | None:
        return self.advance() if self.tok.kind == kind else None

    def expect(self, kind: str, what: str) -> Token:
        if self.tok.kind != kind:
            self.fail(f"I expected {what} here, but found {describe(self.tok)}")
        return self.advance()

    def fail(self, message: str, token: Token | None = None, hint: str | None = None):
        token = token or self.tok
        raise EmberError(message, token.line, token.col, max(token.length, 1), hint)

    # ---- top level -----------------------------------------------------------------------------

    def program(self) -> ast.Program:
        functions = []
        while self.tok.kind != "EOF":
            if self.tok.kind != "FN":
                self.fail(
                    f"only functions can go at the top level of a file, but this starts with {describe(self.tok)}",
                    hint="put it inside a function, for example inside `fn main():`",
                )
            functions.append(self.function())
        return ast.Program(tuple(functions))

    def function(self) -> ast.FnDef:
        self.expect("FN", "`fn`")
        name = self.expect("IDENT", "a function name")
        self.expect("(", "`(`")
        params = []
        if self.tok.kind != ")":
            while True:
                params.append(self.parameter())
                if not self.accept(","):
                    break
        self.expect(")", "`)`")
        return_type = None
        if self.accept("->"):
            type_name = self.expect("IDENT", "a type name")
            return_type = ast.TypeRef(type_name.value, _span(type_name))
        body = self.block("a function")
        return ast.FnDef(name.value, tuple(params), return_type, body, _span(name))

    def parameter(self) -> ast.Param:
        name = self.expect("IDENT", "a parameter name")
        if self.tok.kind != ":":
            self.fail(
                f"parameter `{name.value}` needs a type",
                hint=f"write it like `{name.value}: int`",
            )
        self.advance()
        type_name = self.expect("IDENT", "a type name")
        return ast.Param(name.value, ast.TypeRef(type_name.value, _span(type_name)), _span(name))

    def block(self, owner: str) -> tuple[ast.Stmt, ...]:
        self.expect(":", "a `:`")
        if self.tok.kind != "NEWLINE":
            self.fail(
                f"the body of {owner} has to start on a new line",
                hint="start the body on the next line, indented under the header",
            )
        self.advance()
        self.expect("INDENT", "an indented block")
        statements = []
        while self.tok.kind not in ("DEDENT", "EOF"):
            statements.append(self.statement())
        self.expect("DEDENT", "the end of the block")
        return tuple(statements)

    # ---- statements ----------------------------------------------------------------------------

    def statement(self) -> ast.Stmt:
        match self.tok.kind:
            case "LET" | "MUT":
                return self.declaration()
            case "RETURN":
                return self.return_statement()
            case "IF":
                return self.if_statement()
            case "WHILE":
                keyword = self.advance()
                condition = self.expression()
                return ast.While(condition, self.block("a `while` loop"), _span(keyword))
            case "FOR":
                return self.for_statement()
            case "INDENT":
                self.fail(
                    "this line is indented more than the line above it",
                    hint="only lines after a `:` header can be indented",
                )
            case _:
                return self.simple_statement()

    def end_of_line(self) -> None:
        self.expect("NEWLINE", "the end of the line")

    def declaration(self) -> ast.Declare:
        keyword = self.advance()
        name = self.expect("IDENT", "a variable name")
        self.expect("=", f"`=` to give `{name.value}` a value")
        value = self.expression()
        self.end_of_line()
        return ast.Declare(name.value, keyword.kind == "MUT", value, _span(keyword).to(value.span))

    def return_statement(self) -> ast.Return:
        keyword = self.advance()
        value = None if self.tok.kind == "NEWLINE" else self.expression()
        self.end_of_line()
        return ast.Return(value, _span(keyword))

    def if_statement(self) -> ast.If:
        keyword = self.advance()
        branches = [(self.expression(), self.block("an `if`"))]
        while self.accept("ELIF"):
            branches.append((self.expression(), self.block("an `elif`")))
        else_body = self.block("an `else`") if self.accept("ELSE") else None
        return ast.If(tuple(branches), else_body, _span(keyword))

    def for_statement(self) -> ast.For:
        keyword = self.advance()
        var = self.expect("IDENT", "a loop variable name")
        self.expect("IN", "`in`")
        start = self.expression()
        self.expect("..", "`..` between the start and end of the range")
        end = self.expression()
        return ast.For(var.value, start, end, self.block("a `for` loop"), _span(keyword))

    def simple_statement(self) -> ast.Stmt:
        expr = self.expression()
        if self.tok.kind == "=":
            if not isinstance(expr, ast.Name):
                self.fail(
                    "you can only assign to a variable name",
                    Token("=", "=", expr.span.line, expr.span.col, expr.span.length),
                    hint="the left side of `=` should be a name like `total`",
                )
            self.advance()
            value = self.expression()
            self.end_of_line()
            return ast.Assign(expr.name, value, expr.span.to(value.span))
        self.end_of_line()
        return ast.ExprStmt(expr, expr.span)

    # ---- expressions (loosest to tightest) -----------------------------------------------------

    def expression(self) -> ast.Expr:
        return self.or_expression()

    def or_expression(self) -> ast.Expr:
        left = self.and_expression()
        while self.accept("OR"):
            right = self.and_expression()
            left = ast.Binary("or", left, right, left.span.to(right.span))
        return left

    def and_expression(self) -> ast.Expr:
        left = self.not_expression()
        while self.accept("AND"):
            right = self.not_expression()
            left = ast.Binary("and", left, right, left.span.to(right.span))
        return left

    def not_expression(self) -> ast.Expr:
        if self.tok.kind == "NOT":
            keyword = self.advance()
            operand = self.not_expression()
            return ast.Unary("not", operand, _span(keyword).to(operand.span))
        return self.comparison()

    def comparison(self) -> ast.Expr:
        left = self.additive()
        if self.tok.kind in COMPARISONS:
            op = self.advance()
            right = self.additive()
            if self.tok.kind in COMPARISONS:
                self.fail(
                    "comparisons can't be chained",
                    hint="join two comparisons with `and`, like `1 < x and x < 3`",
                )
            return ast.Binary(op.kind, left, right, left.span.to(right.span))
        return left

    def additive(self) -> ast.Expr:
        left = self.term()
        while self.tok.kind in ("+", "-"):
            op = self.advance()
            right = self.term()
            left = ast.Binary(op.kind, left, right, left.span.to(right.span))
        return left

    def term(self) -> ast.Expr:
        left = self.unary()
        while self.tok.kind in ("*", "/", "%"):
            op = self.advance()
            right = self.unary()
            left = ast.Binary(op.kind, left, right, left.span.to(right.span))
        return left

    def unary(self) -> ast.Expr:
        if self.tok.kind == "-":
            op = self.advance()
            operand = self.unary()
            return ast.Unary("-", operand, _span(op).to(operand.span))
        return self.postfix()

    def postfix(self) -> ast.Expr:
        node = self.primary()
        while True:
            if self.tok.kind == "(":
                if not isinstance(node, ast.Name):
                    self.fail("only a function's name can be called", hint="call it like `name(args)`")
                node = self.call(node)
            elif self.tok.kind == "[":
                self.advance()
                index = self.expression()
                close = self.expect("]", "`]`")
                node = ast.Index(node, index, node.span.to(_span(close)))
            else:
                return node

    def call(self, name: ast.Name) -> ast.Call:
        self.advance()  # the (
        args = []
        if self.tok.kind != ")":
            while True:
                args.append(self.expression())
                if self.accept(","):
                    continue
                if self.tok.kind != ")":
                    self.fail(f"I expected `,` or `)` here, but found {describe(self.tok)}")
                break
        close = self.advance()
        return ast.Call(name.name, tuple(args), name.span.to(_span(close)))

    def primary(self) -> ast.Expr:
        token = self.tok
        match token.kind:
            case "INT":
                self.advance()
                return ast.IntLit(int(token.value), _span(token))
            case "FLOAT":
                self.advance()
                return ast.FloatLit(float(token.value), _span(token))
            case "STRING":
                self.advance()
                return ast.StrLit(token.value, _span(token))
            case "TRUE" | "FALSE":
                self.advance()
                return ast.BoolLit(token.kind == "TRUE", _span(token))
            case "IDENT":
                self.advance()
                return ast.Name(token.value, _span(token))
            case "(":
                self.advance()
                inner = self.expression()
                self.expect(")", "`)`")
                return inner
        self.fail(f"I expected a value here, but found {describe(token)}")
