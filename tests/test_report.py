from ember.errors import EmberError
from ember.report import render


def test_underlines_the_exact_span_and_shows_the_hint():
    source = 'fn main():\n    let x = 5 + "hi"\n'
    error = EmberError("can't add a number and text", 2, 17, 4, hint="turn one side into the other's type first")
    assert render(error, source, "calc.em") == (
        "error: can't add a number and text\n"
        " --> calc.em:2:17\n"
        "  |\n"
        '2 |     let x = 5 + "hi"\n'
        "  |                 ^^^^\n"
        "  = help: turn one side into the other's type first"
    )


def test_no_help_line_without_a_hint():
    error = EmberError("I don't know what `$` means here", 1, 3)
    assert render(error, "1 $ 2", "a.em").splitlines() == [
        "error: I don't know what `$` means here",
        " --> a.em:1:3",
        "  |",
        "1 | 1 $ 2",
        "  |   ^",
    ]


def test_gutter_widens_for_long_line_numbers():
    source = "\n" * 11 + "oops"
    lines = render(EmberError("bad", 12, 1, 4), source, "a.em").splitlines()
    assert lines[1:5] == ["  --> a.em:12:1", "   |", "12 | oops", "   | ^^^^"]


def test_underline_is_clamped_to_the_end_of_the_line():
    lines = render(EmberError("bad", 1, 3, 50), "abcd", "a.em").splitlines()
    assert lines[-1] == "  |   ^^"


def test_error_just_past_the_end_of_the_line_still_gets_a_caret():
    lines = render(EmberError("I expected a `:` here", 1, 10), "fn main()", "a.em").splitlines()
    assert lines[-1] == "  |          ^"


def test_line_outside_the_source_shows_an_empty_line():
    lines = render(EmberError("bad", 5, 1), "one line", "a.em").splitlines()
    assert lines[3] == "5 | "
