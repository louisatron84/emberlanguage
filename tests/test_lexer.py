import pytest

from ember.errors import EmberError
from ember.lexer import lex


def kinds(source: str) -> list[str]:
    return [t.kind for t in lex(source)]


def test_empty_source_is_just_eof():
    assert kinds("") == ["EOF"]


def test_numbers_and_operators():
    assert kinds("1 + 2.5 * 3") == ["INT", "+", "FLOAT", "*", "INT", "NEWLINE", "EOF"]


def test_number_values_keep_their_text():
    tokens = lex("42 3.14")
    assert [t.value for t in tokens[:2]] == ["42", "3.14"]


def test_range_is_not_a_float():
    assert kinds("0..10") == ["INT", "..", "INT", "NEWLINE", "EOF"]


def test_keywords_and_identifiers():
    assert kinds("let total = 5") == ["LET", "IDENT", "=", "INT", "NEWLINE", "EOF"]
    assert kinds("fn mut return") == ["FN", "MUT", "RETURN", "NEWLINE", "EOF"]
    assert kinds("elif else while for in and or not true false if") == [
        "ELIF", "ELSE", "WHILE", "FOR", "IN", "AND", "OR", "NOT", "TRUE", "FALSE", "IF",
        "NEWLINE", "EOF",
    ]


def test_identifier_that_starts_like_a_keyword():
    tokens = lex("letter")
    assert tokens[0].kind == "IDENT" and tokens[0].value == "letter"


def test_two_character_operators():
    assert kinds("== != <= >= -> ..") == ["==", "!=", "<=", ">=", "->", "..", "NEWLINE", "EOF"]


def test_one_character_operators_and_punctuation():
    assert kinds("a < b > c % d / e - f = g ( ) , :") == [
        "IDENT", "<", "IDENT", ">", "IDENT", "%", "IDENT", "/", "IDENT", "-", "IDENT", "=",
        "IDENT", "(", ")", ",", ":", "NEWLINE", "EOF",
    ]


def test_square_brackets_for_indexing():
    assert kinds("s[0]") == ["IDENT", "[", "INT", "]", "NEWLINE", "EOF"]


def test_newlines_inside_brackets_are_ignored():
    assert kinds("s[\n0]") == ["IDENT", "[", "INT", "]", "NEWLINE", "EOF"]


def test_mismatched_closing_bracket_is_an_error():
    with pytest.raises(EmberError) as info:
        lex("f(1]")
    assert (info.value.line, info.value.col) == (1, 4)
    assert "doesn't match" in info.value.message


def test_comments_are_skipped():
    assert kinds("1 # one\n# only a comment\n2") == ["INT", "NEWLINE", "INT", "NEWLINE", "EOF"]


def test_blank_lines_are_skipped():
    assert kinds("1\n\n\n2\n") == ["INT", "NEWLINE", "INT", "NEWLINE", "EOF"]


def test_string_literal_is_decoded():
    tokens = lex(r'"a\tb\n\"q\" \\"')
    assert tokens[0].kind == "STRING"
    assert tokens[0].value == 'a\tb\n"q" \\'


def test_indent_and_dedent():
    source = "fn main():\n    let x = 1\n    let y = 2\nlet z = 3\n"
    assert kinds(source) == [
        "FN", "IDENT", "(", ")", ":", "NEWLINE",
        "INDENT", "LET", "IDENT", "=", "INT", "NEWLINE", "LET", "IDENT", "=", "INT", "NEWLINE",
        "DEDENT", "LET", "IDENT", "=", "INT", "NEWLINE",
        "EOF",
    ]


def test_nested_blocks_dedent_together_at_end_of_file():
    source = "while a:\n    while b:\n        c\n"
    assert kinds(source)[-4:] == ["NEWLINE", "DEDENT", "DEDENT", "EOF"]


def test_blank_and_comment_lines_do_not_change_indentation():
    source = "while a:\n    b\n\n        # stray comment\n    c\n"
    assert kinds(source).count("INDENT") == 1
    assert kinds(source).count("DEDENT") == 1


def test_newlines_inside_parentheses_are_ignored():
    assert kinds("f(1,\n  2)") == ["IDENT", "(", "INT", ",", "INT", ")", "NEWLINE", "EOF"]


def test_positions_are_one_based_line_and_column():
    tokens = lex("let x = 12\n  y")
    assert (tokens[0].line, tokens[0].col) == (1, 1)
    assert (tokens[1].line, tokens[1].col) == (1, 5)
    number = tokens[3]
    assert (number.line, number.col, number.length) == (1, 9, 2)


def test_unexpected_character_is_a_clear_error():
    with pytest.raises(EmberError) as info:
        lex("let x = 5 $ 2")
    assert (info.value.line, info.value.col) == (1, 11)
    assert "$" in info.value.message


def test_unterminated_string_points_at_the_opening_quote():
    with pytest.raises(EmberError) as info:
        lex('print("hello)')
    assert (info.value.line, info.value.col) == (1, 7)
    assert "never closed" in info.value.message


def test_tabs_are_rejected_with_a_hint():
    with pytest.raises(EmberError) as info:
        lex("fn main():\n\tlet x = 1")
    assert info.value.line == 2
    assert "tab" in info.value.message.lower()
    assert info.value.hint


def test_dedent_to_a_level_that_does_not_exist_is_an_error():
    with pytest.raises(EmberError) as info:
        lex("if a:\n        b\n    c\n")
    assert info.value.line == 3
    assert "indent" in info.value.message.lower()
