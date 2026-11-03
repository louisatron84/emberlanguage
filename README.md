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
- Types: `int` and `float` (both 64-bit), and strings.
- `let` makes a fixed value, `mut` makes one you can reassign.
- `if` / `elif` / `else`, `while`, `for i in 0..10`, `and` / `or` / `not`, `true` / `false`.
- Built-ins: `print`, `read_line`, character access on strings, `to_float`.
- Memory is never freed in version 1 (short programs; the OS reclaims it on exit).
- Errors show the line, underline the problem, explain it in plain English and suggest a fix.

## Using it

```
ember build calc.em   # produces calc.exe
ember run calc.em     # builds and runs
```

Needs Python 3.11+ and `gcc` on your PATH.

## Developing

```
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest
```

## Roadmap

1. Lexer, parser, error reporter, type checker, C generator, CLI. Done when `examples/calc.em` works.
2. Word counter, files, lists, dictionaries.
3. Rust-style ownership, so memory is freed safely.
