from __future__ import annotations

import contextlib
from typing import Any, Iterator, Optional


class Formatter:
    _indent_level: int
    _indent_str: str
    _buffer: str

    def __init__(self, indent_level: int = 0, indent_str: str = "    ") -> None:
        self._indent_str = indent_str
        self._indent_level = indent_level
        self._buffer = ""

    @property
    def indent_level(self) -> int:
        return self._indent_level

    def __str__(self) -> str:
        return self._buffer

    @contextlib.contextmanager
    def block(self, delta: int = 1) -> Iterator[None]:
        self._indent_level += delta
        yield
        self._indent_level -= delta

    @contextlib.contextmanager
    def block_with_comment(self, comment: Optional[str] = None) -> Iterator[None]:
        with self.block():
            if comment:
                self.writelines(comment)
            yield

    def write(self, s: Any) -> "Formatter":
        self._buffer += str(s)
        return self

    def indent(self) -> "Formatter":
        return self.write(self._indent_str * self._indent_level)

    def writeline(self, s: Any) -> "Formatter":
        return self.indent().write(s).newline()

    def writelines(self, s: Any) -> "Formatter":
        for line in str(s).split("\n"):
            self.writeline(line)
        return self

    def newline(self) -> "Formatter":
        return self.write("\n")
