import pytest

from ember.ast import dump
from ember.errors import EmberError
from ember.lexer import lex
from ember.parser import parse


def expr(source: str) -> str:
    """Parse one expression by wrapping it in a function that returns it."""
    program = parse(lex(f"fn f():\n    return {source}\n"))
    return dump(program.functions[0].body[0]).removeprefix("(return ").removesuffix(")")


def body(source: str) -> str:
    indented = "".join(f"    {line}\n" for line in source.strip("\n").split("\n"))
    program = parse(lex("fn f():\n" + indented))
    return dump(program)


def error_for(source: str) -> EmberError:
    with pytest.raises(EmberError) as info:
        parse(lex(source))
    return info.value


# ---- expressions -------------------------------------------------------------------------------

def test_literals():
    assert expr("42") == "42"
    assert expr("2.5") == "2.5"
    assert expr('"hi"') == '"hi"'
    assert expr("true") == "true"
    assert expr("false") == "false"
    assert expr("total") == "total"


def test_multiplication_binds_tighter_than_addition():
    assert expr("2 + 3 * 4") == "(+ 2 (* 3 4))"
    assert expr("2 * 3 + 4") == "(+ (* 2 3) 4)"


def test_same_precedence_is_left_associative():
    assert expr("10 - 4 - 3") == "(- (- 10 4) 3)"
    assert expr("8 / 4 / 2") == "(/ (/ 8 4) 2)"
    assert expr("7 % 4 * 2") == "(* (% 7 4) 2)"


def test_parentheses_override_precedence():
    assert expr("(2 + 3) * 4") == "(* (+ 2 3) 4)"


def test_unary_minus_and_not():
    assert expr("-5") == "(- 5)"
    assert expr("-2 * 3") == "(* (- 2) 3)"
    assert expr("- -2") == "(- (- 2))"
    assert expr("not done") == "(not done)"


def test_comparison_is_below_arithmetic():
    assert expr("a + 1 < b * 2") == "(< (+ a 1) (* b 2))"
    assert expr("a == b") == "(== a b)"
    assert expr("a != b") == "(!= a b)"
    assert expr("a <= b") == "(<= a b)"
    assert expr("a >= b") == "(>= a b)"


def test_logic_precedence_is_not_then_and_then_or():
    assert expr("a or b and c") == "(or a (and b c))"
    assert expr("not a and b") == "(and (not a) b)"
    assert expr("not a == b") == "(not (== a b))"


def test_calls_and_indexing():
    assert expr("f()") == "(call f)"
    assert expr("add(1, 2 + 3)") == "(call add 1 (+ 2 3))"
    assert expr("s[0]") == "(index s 0)"
    assert expr("s[i + 1]") == "(index s (+ i 1))"
    assert expr("f(x)[0]") == "(index (call f x) 0)"


def test_comparisons_cannot_be_chained():
    error = error_for("fn f():\n    return 1 < 2 < 3\n")
    assert error.line == 2
    assert "chain" in error.message.lower()
    assert error.hint


# ---- statements --------------------------------------------------------------------------------

def test_let_and_mut_declarations():
    assert body("let x = 5") == "(fn f () {(let x 5)})"
    assert body("mut total = 0") == "(fn f () {(mut total 0)})"


def test_assignment_and_expression_statements():
    assert body("total = total + 1") == "(fn f () {(set total (+ total 1))})"
    assert body("print(total)") == "(fn f () {(expr (call print total))})"


def test_return_with_and_without_a_value():
    assert body("return") == "(fn f () {(return)})"
    assert body("return 1") == "(fn f () {(return 1)})"


def test_while():
    assert body("while x < 10:\n    x = x + 1") == "(fn f () {(while (< x 10) {(set x (+ x 1))})})"


def test_if_elif_else():
    source = "if a:\n    x = 1\nelif b:\n    x = 2\nelse:\n    x = 3"
    assert body(source) == "(fn f () {(if a {(set x 1)} elif b {(set x 2)} else {(set x 3)})})"


def test_if_without_else():
    assert body("if a:\n    x = 1") == "(fn f () {(if a {(set x 1)})})"


def test_for_over_a_range():
    assert body("for i in 0..10:\n    print(i)") == "(fn f () {(for i 0 10 {(expr (call print i))})})"
    assert body("for i in a + 1..n * 2:\n    print(i)") == (
        "(fn f () {(for i (+ a 1) (* n 2) {(expr (call print i))})})"
    )


def test_nested_blocks():
    source = "while a:\n    if b:\n        c = 1\n    d = 2"
    assert body(source) == "(fn f () {(while a {(if b {(set c 1)}) (set d 2)})})"


# ---- functions and programs --------------------------------------------------------------------

def test_function_with_parameters_and_return_type():
    program = parse(lex("fn add(a: int, b: int) -> int:\n    return a + b\n"))
    assert dump(program) == "(fn add (a:int b:int) -> int {(return (+ a b))})"


def test_several_functions():
    program = parse(lex("fn a():\n    return\n\nfn b():\n    return\n"))
    assert [f.name for f in program.functions] == ["a", "b"]


def test_the_readme_example_parses():
    source = (
        "# adds up numbers until we pass 10\n"
        "fn add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n"
        "fn main():\n"
        "    let step = 3\n"
        "    mut total = 0\n"
        "    while total < 10:\n"
        "        total = add(total, step)\n"
        "    print(total)\n"
    )
    assert len(parse(lex(source)).functions) == 2


def test_spans_cover_the_whole_expression():
    program = parse(lex("fn f():\n    return 1 + 22\n"))
    ret = program.functions[0].body[0]
    assert (ret.value.span.line, ret.value.span.col, ret.value.span.length) == (2, 12, 6)


# ---- errors ------------------------------------------------------------------------------------

def test_only_functions_may_appear_at_the_top_level():
    error = error_for("let x = 5\n")
    assert (error.line, error.col) == (1, 1)
    assert "top level" in error.message


def test_missing_colon_after_function_header():
    error = error_for("fn main()\n    return\n")
    assert error.line == 1
    assert "`:`" in error.message


def test_parameter_without_a_type_asks_for_one():
    error = error_for("fn add(a, b: int):\n    return\n")
    assert (error.line, error.col) == (1, 9)
    assert "type" in error.message.lower()


def test_missing_closing_parenthesis_in_a_call():
    error = error_for("fn f():\n    print(1 2)\n")
    assert error.line == 2
    assert "2" in error.message


def test_one_line_bodies_are_not_supported_and_say_so():
    error = error_for("fn f():\n    if a: return\n")
    assert error.line == 2
    assert error.hint and "next line" in error.hint


def test_empty_function_body_is_an_error():
    error = error_for("fn f():\nfn g():\n    return\n")
    assert error.line == 2
    assert "indent" in error.message.lower()


def test_assignment_target_must_be_a_name():
    error = error_for("fn f():\n    1 = 2\n")
    assert error.line == 2
