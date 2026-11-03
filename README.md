# Ember

A fast, Python-feeling language that compiles to C. The compiler is written in Python and hands the
generated C to `gcc`, so programs run as native code.

```
# adds up numbers until we pass 10
fn add(a: int, b: int) -> int:
    return a + b

fn main():
    let step = 3
    mut total = 0
    while total < 10:
        total = add(total, step)
    print(total)
```

## Language sketch (version 1)

- Python-style indentation; `#` starts a comment; the program starts at `fn main()`.
- Static types with inference: function parameters and return types are written, locals are inferred.
- Types: `int` and `float` (both 64-bit), `bool` and `str`. A whole number fits wherever a float is wanted.
- `let` makes a fixed value, `mut` makes one you can reassign.
- `if` / `elif` / `else`, `while`, `for i in 0..10` (0 to 9, like Python's `range`), `and` / `or` / `not`, `true` / `false`.
- `/` always gives a float. Floats print without a trailing `.0`, so `14.0` prints as `14`.
- Built-ins: `print`, `read_line`, `to_float`, `len`, and `s[i]` for one character of a string.
- Whole-number overflow, division by zero and out-of-range indexes stop the program with the line number.
- Memory is never freed in version 1 (short programs; the OS reclaims it on exit).
- Errors show the line, underline the problem, explain it in plain English and suggest a fix.

## Using it

```
ember build calc.em            # produces calc.exe
ember build calc.em --emit-c   # also saves the generated calc.c, to see what Ember made
ember run calc.em              # builds and runs
```

Try the calculator: `ember run examples\calc.em`, then type `2 + 3 * 4`.

Needs Python 3.11+ and `gcc` on your PATH (on Windows, MSYS2's UCRT64 gcc is found automatically).

## Developing

```
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pip install -e .   # puts `ember` in .venv\Scripts
.\.venv\Scripts\python.exe -m pytest
```

How the compiler fits together: [docs/architecture.md](docs/architecture.md).

## Roadmap

1. ~~Lexer, parser, error reporter, type checker, C generator, CLI. Done when `examples/calc.em` works.~~ Done.
2. Word counter, files, lists, dictionaries.
3. Rust-style ownership, so memory is freed safely.
