import pytest

from ember.checker import check
from ember.errors import EmberError
from ember.lexer import lex
from ember.parser import parse


def checked(source: str):
    return check(parse(lex(source)))


def main(body: str, extra: str = "") -> str:
    """A program whose `main` holds `body` (each line indented one level), after `extra`."""
    return extra + "fn main():\n" + "".join(f"    {line}\n" for line in body.strip("\n").split("\n"))


def error_for(source: str) -> EmberError:
    with pytest.raises(EmberError) as info:
        checked(source)
    return info.value


def type_of_declared(source: str, index: int = 0) -> str:
    """The inferred type of the index-th statement's value in main."""
    result = checked(source)
    fn = next(f for f in result.program.functions if f.name == "main")
    return result.type_of(fn.body[index].value)


# ---- inference ---------------------------------------------------------------------------------

def test_literals_infer_their_types():
    assert type_of_declared(main("let a = 1")) == "int"
    assert type_of_declared(main("let a = 1.5")) == "float"
    assert type_of_declared(main('let a = "x"')) == "str"
    assert type_of_declared(main("let a = true")) == "bool"


def test_int_arithmetic_stays_int_and_mixing_gives_float():
    assert type_of_declared(main("let a = 1 + 2 * 3")) == "int"
    assert type_of_declared(main("let a = 1 + 2.5")) == "float"
    assert type_of_declared(main("let a = 7 % 2")) == "int"


def test_division_always_gives_a_float():
    assert type_of_declared(main("let a = 6 / 3")) == "float"


def test_comparisons_and_logic_give_bool():
    assert type_of_declared(main("let a = 1 < 2.5")) == "bool"
    assert type_of_declared(main('let a = "a" < "b"')) == "bool"
    assert type_of_declared(main("let a = not (1 == 2) or true")) == "bool"


def test_string_joining_and_indexing():
    assert type_of_declared(main('let a = "ab" + "c"')) == "str"
    assert type_of_declared(main('let s = "abc"\nlet c = s[1]'), 1) == "str"


def test_builtins_have_types():
    assert type_of_declared(main("let a = read_line()")) == "str"
    assert type_of_declared(main('let a = to_float("2.5")')) == "float"
    assert type_of_declared(main('let a = len("abc")')) == "int"


def test_variables_carry_their_type():
    assert type_of_declared(main("let a = 1.5\nlet b = a * 2"), 1) == "float"


def test_user_function_return_type():
    source = main("let a = add(1, 2)", extra="fn add(a: int, b: int) -> int:\n    return a + b\n")
    assert type_of_declared(source) == "int"


def test_whole_number_can_be_passed_where_a_float_is_wanted():
    checked(main("let a = half(3)", extra="fn half(x: float) -> float:\n    return x / 2\n"))


def test_the_readme_example_checks():
    checked(
        "fn add(a: int, b: int) -> int:\n    return a + b\n\n"
        "fn main():\n    let step = 3\n    mut total = 0\n    while total < 10:\n"
        "        total = add(total, step)\n    print(total)\n"
    )


def test_functions_can_call_ones_defined_later():
    checked("fn main():\n    print(later())\n\nfn later() -> int:\n    return 1\n")


# ---- mutability and scope ----------------------------------------------------------------------

def test_assigning_to_let_is_an_error_with_a_mut_hint():
    error = error_for(main("let total = 0\ntotal = 1"))
    assert (error.line, error.col) == (3, 5)
    assert "isn't `mut`" in error.message
    assert "mut total" in error.hint


def test_assigning_to_mut_is_fine():
    checked(main("mut total = 0\ntotal = total + 1"))


def test_parameters_and_loop_variables_cannot_be_changed():
    assert "isn't `mut`" in error_for(main("x = 1", extra="fn f(x: int):\n    x = 2\n")).message
    assert "isn't `mut`" in error_for(main("for i in 0..3:\n    i = 5")).message


def test_unknown_variable_suggests_a_close_name():
    error = error_for(main("mut total = 0\nprint(totl)"))
    assert (error.line, error.col) == (3, 11)
    assert "`totl`" in error.message
    assert error.hint == "did you mean `total`?"


def test_variable_from_an_inner_block_is_gone_afterwards():
    error = error_for(main("if true:\n    let x = 1\nprint(x)"))
    assert error.line == 4
    assert "`x`" in error.message


def test_declaring_a_name_twice_is_an_error():
    error = error_for(main("let x = 1\nlet x = 2"))
    assert error.line == 3
    assert "already" in error.message


def test_inner_block_cannot_reuse_an_outer_name():
    assert "already" in error_for(main("let x = 1\nwhile true:\n    let x = 2")).message


def test_sibling_blocks_can_reuse_a_name():
    checked(main("if true:\n    let x = 1\nelse:\n    let x = 2"))


def test_changing_a_variables_type_is_an_error():
    error = error_for(main("mut total = 0\ntotal = 2.5"))
    assert "int" in error.message and "float" in error.message
    assert "0.0" in error.hint


def test_whole_number_can_go_into_a_float_variable():
    checked(main("mut total = 0.0\ntotal = 3"))


# ---- operators ---------------------------------------------------------------------------------

def test_adding_text_and_a_number_is_an_error():
    error = error_for(main('let x = 5 + "hi"'))
    assert (error.line, error.col, error.length) == (2, 13, 8)
    assert "add" in error.message


def test_logic_needs_bools():
    assert "`and`" in error_for(main("let x = 1 and true")).message
    assert "`not`" in error_for(main("let x = not 1")).message


def test_minus_needs_a_number():
    assert "-" in error_for(main('let x = -"a"')).message


def test_bools_cannot_be_ordered_and_mixed_comparisons_fail():
    error_for(main("let x = true < false"))
    error_for(main('let x = 1 == "1"'))


def test_indexing_needs_text_and_a_whole_number():
    assert "index" in error_for(main("let x = 5[0]")).message
    assert "int" in error_for(main('let s = "ab"\nlet c = s[1.5]')).message


def test_number_too_big_for_an_int():
    error = error_for(main("let x = 9223372036854775808"))
    assert "too big" in error.message


# ---- conditions --------------------------------------------------------------------------------

def test_conditions_must_be_bool():
    error = error_for(main("if 1:\n    print(1)"))
    assert "`if`" in error.message
    assert "!= 0" in error.hint
    assert "`while`" in error_for(main("while 0:\n    print(1)")).message


def test_range_bounds_must_be_whole_numbers():
    assert "int" in error_for(main("for i in 0..2.5:\n    print(i)")).message


# ---- functions ---------------------------------------------------------------------------------

def test_unknown_function_suggests_a_close_name():
    error = error_for(main("prnt(1)"))
    assert "`prnt`" in error.message
    assert error.hint == "did you mean `print`?"


def test_wrong_number_of_arguments():
    error = error_for(main("let x = add(1)", extra="fn add(a: int, b: int) -> int:\n    return a + b\n"))
    assert "2" in error.message and "1" in error.message


def test_wrong_argument_type_points_at_the_argument():
    error = error_for(main('let x = add(1, "2")', extra="fn add(a: int, b: int) -> int:\n    return a + b\n"))
    assert (error.line, error.col) == (4, 20)


def test_using_a_function_that_returns_nothing_as_a_value():
    error = error_for(main("let x = print(1)"))
    assert "doesn't give back a value" in error.message


def test_print_takes_exactly_one_value():
    error_for(main("print()"))
    error_for(main("print(1, 2)"))


def test_return_type_must_match():
    error = error_for(main("print(1)", extra='fn f() -> int:\n    return "no"\n'))
    assert "int" in error.message


def test_returning_a_value_from_a_function_without_a_return_type():
    error = error_for(main("return 1"))
    assert "->" in error.hint


def test_missing_return_on_some_path_is_an_error():
    source = main("print(1)", extra="fn f(x: int) -> int:\n    if x > 0:\n        return 1\n")
    error = error_for(source)
    assert error.line == 1
    assert "every path" in error.message


def test_if_else_that_returns_on_both_sides_is_enough():
    checked(main("print(f(1))", extra="fn f(x: int) -> int:\n    if x > 0:\n        return 1\n    else:\n        return 2\n"))


def test_unknown_type_name_suggests_the_real_one():
    error = error_for(main("print(1)", extra="fn f(x: string):\n    return\n"))
    assert error.hint == "did you mean `str`?"


def test_program_needs_a_main():
    error = error_for("fn helper():\n    return\n")
    assert "main" in error.message


def test_main_takes_no_parameters_and_returns_nothing():
    error_for("fn main(x: int):\n    return\n")
    error_for("fn main() -> int:\n    return 1\n")


def test_duplicate_function_and_builtin_clash():
    assert "already" in error_for(main("print(1)", extra="fn f():\n    return\nfn f():\n    return\n")).message
    assert "built in" in error_for(main("print(1)", extra="fn len(s: str) -> int:\n    return 0\n")).message
