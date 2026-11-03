# Ember compiler architecture (version 1)

## 1. Requirements

**Functional:** compile `.em` source to a native `.exe` via C and `gcc`; `ember build` and `ember run`;
report errors in plain English with the source line underlined. Acceptance program: `examples/calc.em`.

**Non-functional:**
- Output speed matters most (native code, `gcc -O2`). Compile speed does not matter yet.
- Error message quality is a first-class feature, not polish.
- Each stage testable on its own; the whole compiler small enough to read in one sitting.

**Constraints:** compiler in Python (the only language the owner knows); Windows with `gcc` from MSYS2
(`C:\msys64\ucrt64\bin`); one person; no dependencies beyond Python and gcc.

## 2. High-level design

```
 calc.em
    |
    v
 [lexer] --tokens--> [parser] --AST--> [checker] --typed AST--> [C generator] --calc.c--> [gcc] --> calc.exe
    \                   |                  |                          |
     \__________________|__________________|__________________________/
                                  |
                          EmberError(message, line, col, length, hint)
                                  |
                          [reporter]  prints source line + underline + hint

 runtime/ember_runtime.h  --- #included by every generated .c file
```

Each stage is a pure function from one data structure to the next. Any stage may raise `EmberError`;
only the CLI catches it and calls the reporter. Stages never print.

| Stage | Module | Input -> Output | Status |
|---|---|---|---|
| Lexer | `ember/lexer.py` | text -> `list[Token]` (with INDENT/DEDENT) | done |
| Parser | `ember/parser.py` | tokens -> AST (`ember/ast.py`) | done |
| Reporter | `ember/report.py` | `EmberError` + source -> text | done |
| Checker | `ember/checker.py` | AST -> `Checked` (AST + type of every expression) | done |
| C generator | `ember/codegen.py` | `Checked` -> C text | done |
| CLI | `ember/cli.py` | args -> runs the above, then gcc | done |

Version 1 is complete: `examples/calc.em` compiles and passes its end-to-end tests.

## 3. Deep dive

**AST.** Frozen dataclasses, every node carrying a `Span(line, col, length)` so any error can point at
it. The checker never changes the tree: it returns a `Checked` object holding the tree, every
function's signature, and a side table from each expression node to its type. The C generator reads
types from that table.

**Types.** `int` (C `int64_t`), `float` (C `double`), `bool`, `str`, and `void` for functions that
return nothing. Local types are inferred from the initialiser (`let x = 5` is `int`). No generics,
no user-defined types in version 1. Function signatures are explicit, so checking is one pass over
each function body with a symbol table: no unification, no whole-program inference.

**Mutability.** Each symbol records `let` or `mut`; assigning to a `let` is a checker error with the
"isn't `mut`" hint.

**Generated C.**
- User functions are emitted as `ember_<name>`; the real C `main` calls `ember_main`. This avoids
  clashes with C keywords and library names.
- Indentation blocks become braces. `for i in a..b` becomes a plain C `for`; like Python's
  `range`, the end is excluded (`0..3` is 0, 1, 2) and both ends are worked out once.
- Strings are `struct { const char *ptr; int64_t len; }`, immutable UTF-8, so no C-string pitfalls.
  `s[i]` and `len(s)` count bytes, which only differs from characters for non-English text.
- A whole number is widened to a float wherever a float is expected; mixing them gives a float.
- `%` follows Python: the result has the divisor's sign (`-7 % 3` is 2).
- Integer `+ - *` use `__builtin_*_overflow` and crash on overflow. Division by zero crashes.
  Both go through a `ember_panic(line, msg)` function in the runtime, so runtime errors name the
  `.em` line.
- Emit `#line N "calc.em"` directives so any gcc complaint or debugger points back at Ember source.
- All allocation goes through `ember_alloc()` and nothing calls `malloc` directly. Version 1's
  `ember_alloc` never frees. This is the single seam where ownership gets added later.

**Runtime.** One header, `ember/ember_runtime.h`, with `print`, `read_line`, string indexing,
`to_float`, overflow-checked ops and `ember_panic`. It is pasted at the top of the generated C file,
so gcc only ever sees one self-contained file. `read_line` drops a UTF-8 byte-order mark at the very
start of input, because Windows PowerShell adds one when piping text in. Executables are linked with
`-static`, so they run on machines without MSYS2.

**Toolchain discovery (Windows).** Find gcc with `shutil.which("gcc")`, then fall back to
`C:\msys64\ucrt64\bin\gcc.exe`. If neither exists, say so and how to install it. If gcc rejects the
generated C, that is a compiler bug: print it as "internal error, this is a bug in Ember" with the
gcc output, never as the user's mistake.

**Error handling.** One exception type, `EmberError`. The lexer already raises it with positions and
hints. The reporter renders:

```
error: can't add a number and text
  --> calc.em:3:9
   |
 3 |   x = 5 + "hi"
   |           ^^^^ this is text, but `+` needs a number here
```

## 4. Scale and reliability

Not a service, so "scale" means source size. Programs are small; a straightforward recursive-descent
parser and one pass per stage are plenty. Reliability comes from tests: per-stage unit tests,
snapshot tests of generated C for tiny programs, error-message tests that compare rendered text, and
end-to-end tests that compile and run `.em` files and compare stdout.

## 5. Trade-offs

| Decision | Chosen | Alternative | Why / cost |
|---|---|---|---|
| Backend | emit C, use gcc | own x86 backend; LLVM | gcc's optimiser beats anything hand-written; small project. Cost: needs gcc installed, slower builds. |
| Compiler language | Python | Rust/Go | Owner knows it; fast to change. Cost: slow compiler (irrelevant at this size). Can be rewritten in Ember later. |
| Typing | static, locals inferred | fully dynamic | Static types are what makes the C fast. Cost: no Python-style flexibility. |
| Syntax | indentation | braces | Python feel. Cost: lexer must track indentation (done, tested). |
| Memory v1 | never free | GC; ownership now | Fastest to build, fine for short programs. Cost: long-running programs leak until ownership lands. |
| Integer overflow | crash | wrap silently | Clear errors are a goal. Cost: a few percent speed on arithmetic. |

## 6. Float printing (settled with the owner)

`/` always returns a float. Floats print with up to 15 significant digits and a trailing `.0` is
dropped, so `14.0` prints `14` and `0.1 + 0.2` prints `0.3`. This differs from Python on purpose.

String indexing is `s[i]` (gives a one-character string) and `len(s)` is a built-in.

## 7. What to revisit as it grows

- **Ownership** (second big project): checker gains a move/borrow pass; `ember_alloc` gains a matching
  free; codegen inserts frees at scope end.
- **Lists and dictionaries** (version 2) need generics or built-in container types; this changes the
  checker most.
- **Compile speed** if programs get big: cache per-file output, or stop re-running gcc on unchanged C.
- **Multiple files / imports:** version 1 is one file only.
- **Own backend** once the language is stable and there is appetite for it.
