#!/usr/bin/env python

import os
import sys
from pathlib import Path

from ..lib.google.protobuf.compiler import CodeGeneratorRequest
from .models import monkey_patch_oneof_index
from .parser import generate_code


def main() -> None:
    """The plugin's main entry point."""
    data = sys.stdin.buffer.read()

    # Apply Work around for proto2/3 difference in protoc messages
    monkey_patch_oneof_index()

    request = CodeGeneratorRequest()
    request.parse(data)

    if dump_file := os.getenv("CBIPROTO_DUMP"):
        sys.stderr.write(f"\033[31mWriting input from protoc to: {dump_file}\033[0m\n")
        Path(dump_file).write_bytes(bytes(request))

    # Generate code
    response = generate_code(request)

    # Write to stdout
    sys.stdout.buffer.write(bytes(response))


if __name__ == "__main__":
    main()
