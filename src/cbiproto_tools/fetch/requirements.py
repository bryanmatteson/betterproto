from __future__ import annotations

import io
import re
from configparser import RawConfigParser
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, NamedTuple, Optional, Sequence

DEFAULT = "default"
ROOT = "root"
_HDR_TMPL = r"^#!\[{hdr}\]\s*$"

_UNSET = object()


class Requirements(RawConfigParser):
    COMMENT_HDR = re.compile(r"^#!\[(.*?)\]\s*$", re.MULTILINE)
    INI_HDR = re.compile(r"^\[(.*?)\]\s*$", re.MULTILINE)
    DEFAULT_HDR = re.compile(_HDR_TMPL.format(hdr=DEFAULT), re.MULTILINE)

    @classmethod
    def from_file(cls, source: Path, ignore_errors: bool = False) -> Requirements:
        req = cls()
        try:
            req.read_file(source)
        except Exception as e:
            if not ignore_errors:
                raise e
        return req

    def __init__(self) -> None:
        super().__init__(delimiters="/:", default_section=DEFAULT)

    def read(self, filenames: Path | Iterable[Path], encoding: str | None = None) -> list[str]:
        return super().read(filenames, encoding)

    def read_dict(self, dictionary: Mapping[str, Mapping[str, Any]], source: str = ...) -> None:
        return super().read_dict(dictionary, source)

    def read_file(self, source: Path | str) -> None:
        source = source if isinstance(source, Path) else Path(source)
        if not source.exists():
            raise ValueError(f"requirements file {source} does not exist!")
        self.read_string(source.read_text(), source.name)

    def read_string(self, contents: str, source: str = "<??>") -> None:
        contents, n = self.COMMENT_HDR.subn(r"[\1]", contents)
        if n == 0:
            contents = f"[{ROOT}]\n" + contents
        return super().read_file(io.StringIO(contents), source)

    def write_file(self, path: Path | str, include_root_header: bool = True) -> None:
        path = Path(path) if isinstance(path, str) else path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fp:
            return self.write(fp, include_root_header)

    def write(self, fp: io.TextIOBase, include_root_header: bool = True) -> None:
        with io.StringIO(newline="") as target:
            super().write(target, space_around_delimiters=False)
            contents = self.INI_HDR.sub(r"#![\1]", target.getvalue()).strip()
            if include_root_header:
                fp.write(contents)
                return

            for line in contents.splitlines(keepends=True):
                if line.startswith(f"#![{ROOT}]"):
                    continue
                fp.write(line)

    def add(self, option: str, value: str, section: str = "") -> None:
        section = section or ROOT
        if not self.has_section(section):
            self.add_section(section)
        self.set(section, option, value)

    def filter(self, pred: Callable[[Entry], bool]) -> Iterator[Entry]:
        for section, options in self.items():
            for opt, value in options.items():
                if pred(entry := Entry(opt, value, section)):
                    yield entry

    def filter_first(self, pred: Callable[[Entry], bool]) -> Entry | None:
        return next(self.filter(pred), None)

    def find(self, section: str | None = None, option: str | None = None, value: str | None = None) -> Iterator[Entry]:
        sections = self.sections() if section is None else [section] if self.has_section(section) else []
        for sn in sections:
            options = self.options(sn) if option is None else [option] if self.has_option(sn, option) else []
            for opt in options:
                val = self.get(sn, opt)
                if value is None or value == val:
                    yield Entry(opt, val, sn)

    def find_first(
        self, section: Optional[str] = None, option: Optional[str] = None, value: Optional[str] = None
    ) -> Entry | None:
        return next(self.find(section, option, value), None)

    def has(self, option: str | None = None, value: str | None = None, section: str | None = None) -> bool:
        return any(self.find(section, option, value))

    @property
    def entries(self) -> Sequence[Entry]:
        return tuple(Entry(n, v, sn) for sn, s in self.items() for n, v in s.items())

    def entry(self, name: str, section: Optional[str] = None, default: Any = _UNSET) -> Entry:
        result = self.find_first(section, name)
        if result is None:
            if default is _UNSET:
                raise KeyError(section, name)
            result = default
        return result


class Entry(NamedTuple):
    name: str = ""
    value: str = ""
    section: str = ""

    def as_tag(self) -> str:
        return f"{self.name}/{self.value}"

    @classmethod
    def parse(cls, val: str) -> Entry:
        gen = ((val[:i], val[i + 1 :]) for i, c in enumerate(val) if c in "/:")
        return Entry(*next(gen, (val, "")))

    @classmethod
    def from_parts(cls, name: str, value: str) -> Entry:
        return Entry(name, value)
