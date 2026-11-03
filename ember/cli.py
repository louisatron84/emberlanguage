"""The `ember` command: `ember build file.em` and `ember run file.em`."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ember.checker import check
from ember.codegen import generate
from ember.errors import EmberError
from ember.lexer import lex
from ember.parser import parse
from ember.report import render

MSYS2_GCC = Path(r"C:\msys64\ucrt64\bin\gcc.exe")
EXE_SUFFIX = ".exe" if os.name == "nt" else ""


class BuildFailed(Exception):
    """Something already explained to the user went wrong; the message is ready to print."""


def compile_to_c(source: str, filename: str) -> str:
    return generate(check(parse(lex(source))), filename)


def find_gcc() -> str | None:
    found = shutil.which("gcc")
    if found:
        return found
    return str(MSYS2_GCC) if MSYS2_GCC.exists() else None


def build(source_path: Path, output: Path, emit_c: bool = False) -> None:
    """Compile an .em file to an executable, or raise BuildFailed with a ready-to-print message."""
    try:
        source = source_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise BuildFailed(f"error: I can't find the file `{source_path}`")
    try:
        c_code = compile_to_c(source, source_path.name)
    except EmberError as error:
        raise BuildFailed(render(error, source, source_path.name))

    if emit_c:
        source_path.with_suffix(".c").write_text(c_code, encoding="utf-8")

    gcc = find_gcc()
    if gcc is None:
        raise BuildFailed(
            "error: I can't find gcc, which Ember needs to build programs\n"
            "  = help: install MSYS2 from https://www.msys2.org, then run `pacman -S mingw-w64-ucrt-x86_64-gcc`"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ember-") as work:
        c_file = Path(work) / (source_path.stem + ".c")
        c_file.write_text(c_code, encoding="utf-8")
        result = subprocess.run(
            [gcc, "-O2", "-std=c11", "-static", "-o", str(output), str(c_file), "-lm"],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        raise BuildFailed(
            "error: internal compiler error: gcc rejected the C that Ember generated.\n"
            "This is a bug in Ember, not in your code. gcc said:\n\n" + result.stderr
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ember", description="The Ember compiler.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="compile a .em file into an executable")
    build_cmd.add_argument("file", type=Path)
    build_cmd.add_argument("-o", "--output", type=Path, help="where to write the executable")
    build_cmd.add_argument("--emit-c", action="store_true", help="also save the generated C next to the source")
    run_cmd = commands.add_parser("run", help="compile a .em file and run it straight away")
    run_cmd.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            output = args.output or args.file.with_suffix(EXE_SUFFIX)
            build(args.file, output, args.emit_c)
            return 0
        with tempfile.TemporaryDirectory(prefix="ember-run-") as work:
            exe = Path(work) / (args.file.stem + EXE_SUFFIX)
            build(args.file, exe)
            sys.stdout.flush()
            return subprocess.run([str(exe)]).returncode
    except BuildFailed as failure:
        print(failure, file=sys.stderr)
        return 1
