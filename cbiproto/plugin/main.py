#!/usr/bin/env python

import os
import sys
from pathlib import Path

from ..lib.google.protobuf.compiler import CodeGeneratorRequest
from .compiler import generate_code
from .utils import monkey_patch_oneof_index

# from .parser import generate_code


def main() -> None:
    data = sys.stdin.buffer.read()

    if dump_file := os.getenv("CBIPROTO_DUMP"):
        sys.stderr.write(f"\033[31mWriting input from protoc to: {dump_file}\033[0m\n")
        Path(dump_file).write_bytes(data)

    monkey_patch_oneof_index()

    request = CodeGeneratorRequest.parse_raw(data)
    response = generate_code(request)
    sys.stdout.buffer.write(bytes(response))


if __name__ == "__main__":
    main()
