"""Compile real .em programs with gcc, run them, and check what they print."""

import subprocess
from pathlib import Path

import pytest

from ember.cli import EXE_SUFFIX, build, find_gcc, main
from ember.codegen import c_string

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(find_gcc() is None, reason="gcc is not installed")


def run(tmp_path: Path, source: str, stdin: bytes = b"") -> subprocess.CompletedProcess:
    program = tmp_path / "prog.em"
    program.write_text(source, encoding="utf-8")
    exe = tmp_path / ("prog" + EXE_SUFFIX)
    build(program, exe)
    return subprocess.run([str(exe)], input=stdin, capture_output=True)


def output(tmp_path: Path, body: str, stdin: bytes = b"", extra: str = "") -> list[str]:
    source = extra + "fn main():\n" + "".join(f"    {line}\n" for line in body.strip("\n").split("\n"))
    result = run(tmp_path, source, stdin)
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout.decode().splitlines()


def crash(tmp_path: Path, body: str, stdin: bytes = b"") -> str:
    source = "fn main():\n" + "".join(f"    {line}\n" for line in body.strip("\n").split("\n"))
    result = run(tmp_path, source, stdin)
    assert result.returncode == 1
    return result.stderr.decode()


# ---- the acceptance program --------------------------------------------------------------------

@pytest.fixture(scope="module")
def calculator(tmp_path_factory) -> Path:
    exe = tmp_path_factory.mktemp("calc") / ("calc" + EXE_SUFFIX)
    build(ROOT / "examples" / "calc.em", exe)
    return exe


@pytest.mark.parametrize("sum_, answer", [
    ("2 + 3 * 4", "14"),
    ("(2 + 3) * 4", "20"),
    ("10 / 4", "2.5"),
    ("-3 - -2", "-1"),
    ("0.1 + 0.2", "0.3"),
    ("  8 / 2 / 2  ", "2"),
    ("((1.5))", "1.5"),
    ("2 +", "sorry, I couldn't understand that"),
    ("hello", "sorry, I couldn't understand that"),
    ("1.2.3", "sorry, I couldn't understand that"),
    ("(1 + 2", "sorry, I couldn't understand that"),
])
def test_calculator(calculator, sum_, answer):
    result = subprocess.run([str(calculator)], input=f"{sum_}\n".encode(), capture_output=True)
    assert result.stdout.decode().splitlines()[1:] == [answer]


def test_calculator_handles_several_lines_and_a_byte_order_mark(calculator):
    result = subprocess.run([str(calculator)], input=b"\xef\xbb\xbf1 + 1\n2 * 3\n\n9\n", capture_output=True)
    assert result.stdout.decode().splitlines()[1:] == ["2", "6"]


def test_calculator_division_by_zero_names_the_line(calculator):
    result = subprocess.run([str(calculator)], input=b"1 / 0\n", capture_output=True)
    assert result.returncode == 1
    assert "division by zero" in result.stderr.decode()
    assert "calc.em:" in result.stderr.decode()


# ---- language behaviour ------------------------------------------------------------------------

def test_readme_example(tmp_path):
    result = run(tmp_path, (ROOT / "examples" / "add.em").read_text())
    assert result.stdout.decode().split() == ["12"]


def test_numbers_print_cleanly(tmp_path):
    body = "print(14.0)\nprint(0.1 + 0.2)\nprint(7 / 2)\nprint(2 + 3 * 4)\nprint(-7 % 3)\nprint(1 + 0.5)"
    assert output(tmp_path, body) == ["14", "0.3", "3.5", "14", "2", "1.5"]


def test_text(tmp_path):
    body = (
        'let s = "héllo"\nprint(s + " world")\nprint(s[0])\nprint(len("abc"))\n'
        'print("a" < "b")\nprint("ab" == "ab")\nprint("tab\\tquote\\" q?")'
    )
    assert output(tmp_path, body) == ["héllo world", "h", "3", "true", "true", 'tab\tquote" q?']


def test_loops_and_branches(tmp_path):
    body = (
        "mut total = 0\nfor i in 0..5:\n    total = total + i\nprint(total)\n"
        "mut n = 0\nwhile n < 3:\n    n = n + 1\nif n == 2:\n    print(2)\nelif n == 3:\n    print(3)\nelse:\n    print(0)"
    )
    assert output(tmp_path, body) == ["10", "3"]


def test_recursion_and_float_parameters(tmp_path):
    extra = (
        "fn fact(n: int) -> int:\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n\n"
        "fn half(x: float) -> float:\n    return x / 2\n\n"
    )
    assert output(tmp_path, "print(fact(20))\nprint(half(3))", extra=extra) == ["2432902008176640000", "1.5"]


def test_reading_input(tmp_path):
    assert output(tmp_path, "print(to_float(read_line()) * 2)\nprint(read_line())", stdin=b"2.5\r\nnext\n") == ["5", "next"]


def test_names_that_are_c_keywords_are_fine(tmp_path):
    assert output(tmp_path, "let int64_t = 1\nlet double = 2\nprint(int64_t + double)") == ["3"]


# ---- runtime errors ----------------------------------------------------------------------------

def test_integer_overflow_is_an_error(tmp_path):
    stderr = crash(tmp_path, "mut x = 9223372036854775807\nx = x + 1")
    assert "too big for an int" in stderr
    assert "prog.em:3" in stderr


def test_index_outside_text_is_an_error(tmp_path):
    assert "position 5 is outside this text, which has 3 characters" in crash(tmp_path, 'print("abc"[5])')


def test_text_that_is_not_a_number(tmp_path):
    assert 'can\'t turn "abc" into a number' in crash(tmp_path, 'print(to_float("abc"))')


def test_remainder_by_zero(tmp_path):
    assert "division by zero" in crash(tmp_path, "let z = 0\nprint(5 % z)")


# ---- the command line --------------------------------------------------------------------------

def test_compile_errors_are_rendered(tmp_path, capsys):
    program = tmp_path / "bad.em"
    program.write_text("fn main():\n    let total = 0\n    total = 1\n", encoding="utf-8")
    assert main(["build", str(program)]) == 1
    err = capsys.readouterr().err
    assert "error: `total` isn't `mut`" in err
    assert " --> bad.em:3:5" in err
    assert "= help:" in err


def test_missing_file(tmp_path, capsys):
    assert main(["build", str(tmp_path / "nope.em")]) == 1
    assert "can't find the file" in capsys.readouterr().err


def test_build_creates_the_output_folder_and_can_emit_c(tmp_path):
    program = tmp_path / "prog.em"
    program.write_text("fn main():\n    print(1)\n", encoding="utf-8")
    exe = tmp_path / "out" / "deeper" / ("prog" + EXE_SUFFIX)
    assert main(["build", str(program), "-o", str(exe), "--emit-c"]) == 0
    assert exe.exists()
    assert "#line" in (tmp_path / "prog.c").read_text()


# ---- C string escaping -------------------------------------------------------------------------

def test_c_string_escapes_quotes_newlines_trigraphs_and_utf8():
    assert c_string('a"b\\c\n??=') == ('a\\"b\\\\c\\n\\?\\?=', 9)
    assert c_string("é") == ("\\303\\251", 2)
