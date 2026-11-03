# A calculator written in Ember.
#
# Type a sum like 2 + 3 * 4 and it prints 14. Brackets, decimals and minus signs work.
# An empty line quits.
#
# Each piece of the grammar has two functions:
#   ..._end   finds where that piece stops, or -1 if the text doesn't make sense
#   ..._value works out what it's worth (only called once the text is known to be good)
#
#   expr   = term   (("+" | "-") term)*
#   term   = factor (("*" | "/") factor)*
#   factor = "-" factor | "(" expr ")" | number

fn is_digit(c: str) -> bool:
    return c >= "0" and c <= "9"

fn skip_spaces(s: str, i: int) -> int:
    mut j = i
    while j < len(s) and s[j] == " ":
        j = j + 1
    return j

fn in_number(s: str, j: int) -> bool:
    return j < len(s) and (is_digit(s[j]) or s[j] == ".")

# ---- numbers ----

fn number_end(s: str, i: int) -> int:
    let start = skip_spaces(s, i)
    mut j = start
    mut dots = 0
    while in_number(s, j):
        if s[j] == ".":
            dots = dots + 1
        j = j + 1
    if j == start or dots > 1 or (dots == 1 and j == start + 1):
        return -1
    return j

fn number_value(s: str, i: int) -> float:
    mut j = skip_spaces(s, i)
    mut digits = ""
    while in_number(s, j):
        digits = digits + s[j]
        j = j + 1
    return to_float(digits)

# ---- factor: a number, a bracketed sum, or a minus sign in front of either ----

fn factor_end(s: str, i: int) -> int:
    let j = skip_spaces(s, i)
    if j < len(s) and s[j] == "-":
        return factor_end(s, j + 1)
    if j < len(s) and s[j] == "(":
        let inner = expr_end(s, j + 1)
        if inner == -1:
            return -1
        let close = skip_spaces(s, inner)
        if close < len(s) and s[close] == ")":
            return close + 1
        return -1
    return number_end(s, j)

fn factor_value(s: str, i: int) -> float:
    let j = skip_spaces(s, i)
    if s[j] == "-":
        return -factor_value(s, j + 1)
    if s[j] == "(":
        return expr_value(s, j + 1)
    return number_value(s, j)

# ---- term: factors joined by * and / ----

fn is_term_op(s: str, k: int) -> bool:
    return k < len(s) and (s[k] == "*" or s[k] == "/")

fn term_end(s: str, i: int) -> int:
    mut j = factor_end(s, i)
    while j != -1 and is_term_op(s, skip_spaces(s, j)):
        j = factor_end(s, skip_spaces(s, j) + 1)
    return j

fn term_value(s: str, i: int) -> float:
    mut value = factor_value(s, i)
    mut k = skip_spaces(s, factor_end(s, i))
    while is_term_op(s, k):
        let right = factor_value(s, k + 1)
        if s[k] == "*":
            value = value * right
        else:
            value = value / right
        k = skip_spaces(s, factor_end(s, k + 1))
    return value

# ---- expr: terms joined by + and - ----

fn is_expr_op(s: str, k: int) -> bool:
    return k < len(s) and (s[k] == "+" or s[k] == "-")

fn expr_end(s: str, i: int) -> int:
    mut j = term_end(s, i)
    while j != -1 and is_expr_op(s, skip_spaces(s, j)):
        j = term_end(s, skip_spaces(s, j) + 1)
    return j

fn expr_value(s: str, i: int) -> float:
    mut value = term_value(s, i)
    mut k = skip_spaces(s, term_end(s, i))
    while is_expr_op(s, k):
        let right = term_value(s, k + 1)
        if s[k] == "+":
            value = value + right
        else:
            value = value - right
        k = skip_spaces(s, term_end(s, k + 1))
    return value

# ---- the loop ----

fn main():
    print("Ember calculator. Type a sum like 2 + 3 * 4, or an empty line to quit.")
    mut line = read_line()
    while len(line) > 0:
        let end = expr_end(line, 0)
        if end == -1 or skip_spaces(line, end) != len(line):
            print("sorry, I couldn't understand that")
        else:
            print(expr_value(line, 0))
        line = read_line()
