#!/usr/bin/env python


from __future__ import annotations

import argparse
import functools
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Set

try:
    import grpc_tools.protoc as protoc
except ImportError as err:
    print(
        "\033[31m"
        f"Unable to import `{err.name}`!"
        "Please ensure that you've installed cbiproto with the [tools] extra"
        "so that compiler dependencies are included."
        "\033[0m"
    )
    raise SystemExit(1)


@dataclass
class Args:
    proto_dir: str
    output: str
    quiet: bool = field(default=False)
    legacy: bool = field(default=False)
    includes: List[str] = field(default_factory=list)
    options: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)


def compile_protos(args: Args) -> int:  # noqa: C901
    """Compiles protos and generates python classes"""

    @functools.wraps(print)
    def log(*a, **kw):
        if not args.quiet:
            print(*a, **kw)

    if not args.files:
        log("no files passed... using directory from proto_dir: ", args.proto_dir)
        args.files = [args.proto_dir]

    files: list[Path] = []
    for path in args.files:
        path = Path(path)
        if not path.exists():
            continue

        if path.is_dir():
            files.extend(path.rglob("*.proto"))
        elif path.suffix.endswith(".proto"):
            files.append(path)

    if not files:
        log("no files... skipping")
        return 0

    with TemporaryDirectory() as tmpdir:
        log("using temp dir ", tmpdir)
        temp_dir = Path(tmpdir)

        compilation = [f"-I{x}" for x in args.includes + [args.proto_dir]]
        if args.legacy:
            compilation += [
                f"--python_out={temp_dir}",
                f"--grpc_python_out={temp_dir}",
                f"--mypy_out=readable_stubs:{temp_dir}",
            ]
        else:
            compilation += [f"--python_cbiproto_out={temp_dir}"]
            for o in args.options:
                compilation.append(f"--python_cbiproto_opt={o}")

        command = ["protoc"] + compilation + list(map(str, files))
        log("running command: ", " ".join(command))

        try:
            result = protoc.main(command)
        except Exception as exc:
            print("Exception occured: ", exc)
            return -1
        else:
            log("Subprocess finished")

        if args.legacy:
            dirs: Set[str] = set()
            for path in temp_dir.rglob("*.py"):
                dirs.add(str(path.relative_to(temp_dir).parent))
            for path in dirs:
                (temp_dir / path / "__init__.py").touch()
        shutil.copytree(temp_dir, args.output, dirs_exist_ok=True)

        return result


def run(
    proto_dir: str,
    output: str,
    quiet: bool = False,
    files: list[str] = [],
    legacy: bool = False,
    includes: list[str] = [],
    options: list[str] = [],
) -> None:
    """Entrypoint when running from tools or scripts"""
    args = Args(
        proto_dir=proto_dir, legacy=legacy, quiet=quiet, output=output, includes=includes, options=options, files=files,
    )
    compile_protos(args)


def main():
    """Entrypoint when running from command line"""

    parser = argparse.ArgumentParser(prog="cbiproto-compiler")
    parser.add_argument("-o", "--output", dest="output")
    parser.add_argument("-l", "--legacy", dest="legacy", action="store_true", default=False)
    parser.add_argument("-q", "--quiet", dest="quiet", action="store_true", default=False)
    parser.add_argument("-p", "--proto-dir", dest="proto_dir", required=True)
    parser.add_argument("--option", dest="options", default=[], action="append")
    parser.add_argument("-i", "--include", dest="includes", default=[], action="append")
    parser.add_argument("files", nargs="*")
    result = parser.parse_args()
    return run(**result.__dict__)
