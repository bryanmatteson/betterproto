from __future__ import annotations

import contextlib
import os.path
import re
from typing import Any, Dict, Iterator, Optional, Set, Tuple, Type

from .._casing import pascal_case, safe_snake_case
from ..lib.google import protobuf as google_protobuf

WRAPPER_TYPES: Dict[str, Type] = {
    ".google.protobuf.DoubleValue": google_protobuf.DoubleValue,
    ".google.protobuf.FloatValue": google_protobuf.FloatValue,
    ".google.protobuf.Int32Value": google_protobuf.Int32Value,
    ".google.protobuf.Int64Value": google_protobuf.Int64Value,
    ".google.protobuf.UInt32Value": google_protobuf.UInt32Value,
    ".google.protobuf.UInt64Value": google_protobuf.UInt64Value,
    ".google.protobuf.BoolValue": google_protobuf.BoolValue,
    ".google.protobuf.StringValue": google_protobuf.StringValue,
    ".google.protobuf.BytesValue": google_protobuf.BytesValue,
}


def pythonize_class_name(name: str) -> str:
    return ".".join(pascal_case(x) for x in name.split("."))


def pythonize_field_name(name: str) -> str:
    return safe_snake_case(name)


def pythonize_method_name(name: str) -> str:
    return safe_snake_case(name)


class TypeManager:
    def __init__(self, package: str) -> None:
        self.package = tuple(package.split("."))
        self._imports: Set[str] = set()
        self._from_imports: Dict[str, Set[str]] = {}

    def get_all_imports(self) -> Iterator[str]:
        yield from self._imports
        for module, names in self._from_imports.items():
            yield f"from {module} import {', '.join(names)}"

    def typing_import(self, typ: str) -> str:
        return self.from_import("typing", typ)

    def from_import(self, module: str, name: str) -> str:
        self._from_imports.setdefault(module, set()).add(name)
        return name

    def module_import(self, module: str, name: str) -> str:
        self._imports.add(f"import {module}")
        return f"{module}.{name}"

    def iterable_of(self, typ: str, aio: bool = False) -> str:
        it = self.typing_import("AsyncIterable" if aio else "Iterable")
        return f"{it}[{typ}]"

    def awaitable_of(self, typ: str) -> str:
        return f'{self.typing_import("Awaitable")}[{typ}]'

    def iterator_of(self, typ: str, aio: bool = False) -> str:
        it = self.typing_import("AsyncIterator" if aio else "Iterator")
        return f"{it}[{typ}]"

    def optional_of(self, typ: str) -> str:
        return f"{self.typing_import('Optional')}[{typ}]"

    def list_of(self, typ: str) -> str:
        return f"{self.typing_import('List')}[{typ}]"

    def dict_of(self, kt: str, vt: str) -> str:
        return f"{self.typing_import('Dict')}[{kt}, {vt}]"

    def get_type_reference(self, source_type: str, unwrap: bool = True) -> str:
        if unwrap:
            if source_type in WRAPPER_TYPES:
                wrapped_type = type(WRAPPER_TYPES[source_type]().value)
                return f"Optional[{wrapped_type.__name__}]"

            if source_type == ".google.protobuf.Duration":
                return "timedelta"

            elif source_type == ".google.protobuf.Timestamp":
                return "datetime"

        source_package, source_type = parse_source_type_name(source_type)

        py_package = tuple(source_package.split(".")) if source_package else ()
        py_type = pythonize_class_name(source_type)

        compiling_google_protobuf = self.package == ("google", "protobuf")
        importing_google_protobuf = py_package == ("google", "protobuf")
        if importing_google_protobuf and not compiling_google_protobuf:
            py_package = ("cbiproto", "lib") + py_package

        if py_package[:1] == ("cbiproto",):
            return self.reference_absolute(py_package, py_type)

        if py_package == self.package:
            return self.reference_sibling(py_type)

        if py_package[: len(self.package)] == self.package:
            return self.reference_descendent(py_package, py_type)

        if self.package[: len(py_package)] == py_package:
            return self.reference_ancestor(py_package, py_type)

        return self.reference_cousin(py_package, py_type)

    def reference_absolute(self, py_package: Tuple[str, ...], py_type: str) -> str:
        string_import = ".".join(py_package)
        string_alias = safe_snake_case(string_import)
        self._imports.add(f"import {string_import} as {string_alias}")
        return f"{string_alias}.{py_type}"

    def reference_sibling(self, py_type: str) -> str:
        return py_type

    def reference_descendent(self, py_package: Tuple[str, ...], py_type: str) -> str:
        importing_descendent = py_package[len(self.package) :]
        string_from = ".".join(importing_descendent[:-1])
        string_import = importing_descendent[-1]
        if string_from:
            string_alias = "_".join(importing_descendent)
            self._imports.add(f"from .{string_from} import {string_import} as {string_alias}")
            return f"{string_alias}.{py_type}"
        else:
            self._imports.add(f"from . import {string_import}")
            return f"{string_import}.{py_type}"

    def reference_ancestor(self, py_package: Tuple[str, ...], py_type: str) -> str:
        distance_up = len(self.package) - len(py_package)
        if py_package:
            string_import = py_package[-1]
            string_alias = f"_{'_' * distance_up}{string_import}"
            string_from = f"..{'.' * distance_up}"
            self._imports.add(f"from {string_from} import {string_import} as {string_alias}")
            return f'"{string_alias}.{py_type}"'
        else:
            string_alias = f"{'_' * distance_up}{py_type}"
            self._imports.add(f"from .{'.' * distance_up} import {py_type} as {string_alias}")
            return f"{string_alias}"

    def reference_cousin(self, py_package: Tuple[str, ...], py_type: str) -> str:
        shared_ancestry = os.path.commonprefix([tuple(self.package), py_package])
        distance_up = len(self.package) - len(shared_ancestry)
        string_from = f".{'.' * distance_up}" + ".".join(py_package[len(shared_ancestry) : -1])
        string_import = py_package[-1]

        string_alias = f"{'_' * distance_up}" + safe_snake_case(".".join(py_package[len(shared_ancestry) :]))
        self._imports.add(f"from {string_from} import {string_import} as {string_alias}")
        return f"{string_alias}.{py_type}"


def parse_source_type_name(field_type_name: str) -> Tuple[str, str]:
    package_match = re.match(r"^\.?([^A-Z]+)\.(.+)", field_type_name)
    if package_match:
        package = package_match.group(1)
        name = package_match.group(2)
    else:
        package = ""
        name = field_type_name.lstrip(".")
    return package, name


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


def monkey_patch_oneof_index():
    """
    The compiler message types are written for proto2, but we read them as proto3.
    For this to work in the case of the oneof_index fields, which depend on being able
    to tell whether they were set, we have to treat them as oneof fields. This method
    monkey patches the generated classes after the fact to force this behaviour.
    """
    object.__setattr__(
        google_protobuf.FieldDescriptorProto.__dataclass_fields__["oneof_index"].metadata["cbiproto"],
        "group",
        "oneof_index",
    )
    object.__setattr__(
        google_protobuf.Field.__dataclass_fields__["oneof_index"].metadata["cbiproto"], "group", "oneof_index",
    )
