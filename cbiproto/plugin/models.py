from __future__ import annotations

import builtins
import re
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Literal, Optional, Set, Type, Union

import cbiproto
from cbiproto import which_one_of
from cbiproto.plugin.importing import get_type_reference
from cbiproto.plugin.naming import pythonize_class_name, pythonize_field_name, pythonize_method_name
from cbiproto.runtime import Cardinality

from .._casing import sanitize_name
from .._types import UNSET
from ..lib.google.protobuf import (
    DescriptorProto,
    EnumDescriptorProto,
    Field,
    FieldDescriptorProto,
    FileDescriptorProto,
    MethodDescriptorProto,
    ServiceDescriptorProto,
)
from ..lib.google.protobuf.compiler import CodeGeneratorRequest
from .formatter import Formatter

# Organize proto types into categories
PROTO_FLOAT_TYPES = (
    FieldDescriptorProto.Type.TYPE_DOUBLE,  # 1
    FieldDescriptorProto.Type.TYPE_FLOAT,  # 2
)
PROTO_INT_TYPES = (
    FieldDescriptorProto.Type.TYPE_INT64,  # 3
    FieldDescriptorProto.Type.TYPE_UINT64,  # 4
    FieldDescriptorProto.Type.TYPE_INT32,  # 5
    FieldDescriptorProto.Type.TYPE_FIXED64,  # 6
    FieldDescriptorProto.Type.TYPE_FIXED32,  # 7
    FieldDescriptorProto.Type.TYPE_UINT32,  # 13
    FieldDescriptorProto.Type.TYPE_SFIXED32,  # 15
    FieldDescriptorProto.Type.TYPE_SFIXED64,  # 16
    FieldDescriptorProto.Type.TYPE_SINT32,  # 17
    FieldDescriptorProto.Type.TYPE_SINT64,  # 18
)
PROTO_BOOL_TYPES = (FieldDescriptorProto.Type.TYPE_BOOL,)  # 8
PROTO_STR_TYPES = (FieldDescriptorProto.Type.TYPE_STRING,)  # 9
PROTO_BYTES_TYPES = (FieldDescriptorProto.Type.TYPE_BYTES,)  # 12
PROTO_MESSAGE_TYPES = (
    FieldDescriptorProto.Type.TYPE_MESSAGE,  # 11
    FieldDescriptorProto.Type.TYPE_ENUM,  # 14
)
PROTO_MAP_TYPES = (FieldDescriptorProto.Type.TYPE_MESSAGE,)  # 11
PROTO_PACKED_TYPES = (
    FieldDescriptorProto.Type.TYPE_DOUBLE,  # 1
    FieldDescriptorProto.Type.TYPE_FLOAT,  # 2
    FieldDescriptorProto.Type.TYPE_INT64,  # 3
    FieldDescriptorProto.Type.TYPE_UINT64,  # 4
    FieldDescriptorProto.Type.TYPE_INT32,  # 5
    FieldDescriptorProto.Type.TYPE_FIXED64,  # 6
    FieldDescriptorProto.Type.TYPE_FIXED32,  # 7
    FieldDescriptorProto.Type.TYPE_BOOL,  # 8
    FieldDescriptorProto.Type.TYPE_UINT32,  # 13
    FieldDescriptorProto.Type.TYPE_SFIXED32,  # 15
    FieldDescriptorProto.Type.TYPE_SFIXED64,  # 16
    FieldDescriptorProto.Type.TYPE_SINT32,  # 17
    FieldDescriptorProto.Type.TYPE_SINT64,  # 18
)


def unset(**kwargs: Any) -> Any:
    """
    A dataclass field that is unset by default.
    """
    return field(default=UNSET, **kwargs)


AnyDescriptor = Union[
    DescriptorProto, FieldDescriptorProto, EnumDescriptorProto, MethodDescriptorProto, ServiceDescriptorProto
]

AnyCompiler = Union[
    "MessageCompiler", "FieldCompiler", "ServiceCompiler", "ProtoContentBase", "ServiceMethodCompiler",
]


def monkey_patch_oneof_index():
    """
    The compiler message types are written for proto2, but we read them as proto3.
    For this to work in the case of the oneof_index fields, which depend on being able
    to tell whether they were set, we have to treat them as oneof fields. This method
    monkey patches the generated classes after the fact to force this behaviour.
    """
    object.__setattr__(
        FieldDescriptorProto.__dataclass_fields__["oneof_index"].metadata["cbiproto"], "group", "oneof_index",
    )
    object.__setattr__(
        Field.__dataclass_fields__["oneof_index"].metadata["cbiproto"], "group", "oneof_index",
    )


def get_comment(proto_file: "FileDescriptorProto", path: List[int]) -> str:
    for sci_loc in proto_file.source_code_info.location:
        if list(sci_loc.path) == path and sci_loc.leading_comments:
            lines = map(str.rstrip, sci_loc.leading_comments.strip().split("\n"))
            fixed_lines: List[str] = []
            for line in lines:
                i = 0
                while i < len(line) and line[i] == " ":
                    i += 1
                fixed_lines.append(line[i % 4 :])

            if len(fixed_lines) == 1:
                return f'"""{fixed_lines[0]}"""'
            joined = "\n".join(fixed_lines)
            return f'"""\n{joined}\n"""'

    return ""


class ProtoContentBase(ABC):
    """Methods common to MessageCompiler, ServiceCompiler and ServiceMethodCompiler."""

    source_file: FileDescriptorProto
    path: List[int]
    parent: Union[AnyCompiler, "OutputTemplate"]

    __dataclass_fields__: Dict[str, object]

    def __post_init__(self) -> None:
        for field_name, field_val in self.__dataclass_fields__.items():
            if field_val is UNSET:
                raise ValueError(f"`{field_name}` is a required field.")

    @property
    def output_file(self) -> "OutputTemplate":
        current = self
        while not isinstance(current, OutputTemplate):
            current = current.parent
        return current

    @property
    def request(self) -> "PluginRequestCompiler":
        current = self
        while not isinstance(current, OutputTemplate):
            current = current.parent
        return current.parent_request

    def get_comment(self) -> str:
        """Crawl the proto source code and retrieve comments
        for this object.
        """
        return get_comment(proto_file=self.source_file, path=self.path)


@dataclass
class PluginRequestCompiler:

    plugin_request_obj: CodeGeneratorRequest
    output_packages: Dict[str, "OutputTemplate"] = field(default_factory=dict)

    @property
    def all_messages(self) -> List["MessageCompiler"]:
        return [msg for output in self.output_packages.values() for msg in output.messages]


@dataclass
class OutputTemplate:
    """Representation of an output .py file.

    Each output file corresponds to a .proto input file,
    but may need references to other .proto files to be
    built.
    """

    parent_request: PluginRequestCompiler
    package_proto_obj: FileDescriptorProto
    mode: Literal["sync", "async"] = "sync"
    input_files: List[FileDescriptorProto] = field(default_factory=list)
    imports: Set[str] = field(default_factory=set)
    datetime_imports: Set[str] = field(default_factory=set)
    typing_imports: Set[str] = field(default_factory=set)
    builtins_import: bool = False
    messages: List[MessageCompiler] = field(default_factory=list)
    enums: List[EnumDefinitionCompiler] = field(default_factory=list)
    services: List[ServiceCompiler] = field(default_factory=list)
    imports_type_checking_only: Set[str] = field(default_factory=set)

    @property
    def package(self) -> str:
        return self.package_proto_obj.package

    @property
    def input_filenames(self) -> Iterable[str]:
        return sorted(f.name for f in self.input_files)

    @property
    def python_module_imports(self) -> Set[str]:
        imports = set()
        if any(x for x in self.messages if any(x.deprecated_fields)):
            imports.add("warnings")
        if self.builtins_import:
            imports.add("builtins")
        return imports


@dataclass
class MessageCompiler(ProtoContentBase):
    source_file: FileDescriptorProto
    proto_obj: DescriptorProto = unset()
    parent: Union[MessageCompiler, OutputTemplate] = unset()
    path: List[int] = unset()
    type_name: str = unset()
    qualname: str = unset()
    fields: List[Union[FieldCompiler, MessageCompiler]] = field(default_factory=list)
    deprecated: bool = field(default=False, init=False)
    builtins_types: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Add message to output file
        if isinstance(self.parent, OutputTemplate):
            if isinstance(self, EnumDefinitionCompiler):
                self.output_file.enums.append(self)
            else:
                self.output_file.messages.append(self)
        elif isinstance(self.parent, MessageCompiler):
            self.parent.fields.append(self)

        self.output_file.imports.add("from dataclasses import dataclass")
        self.deprecated = self.proto_obj.options.deprecated
        super().__post_init__()

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.proto_name)

    @property
    def repeated(self) -> bool:
        return False

    @property
    def annotation(self) -> str:
        if self.repeated:
            return f"List[{self.py_name}]"
        return self.py_name

    @property
    def deprecated_fields(self) -> Iterator[str]:
        for f in self.fields:
            if f.deprecated:
                yield f.py_name

    @property
    def has_deprecated_fields(self) -> bool:
        return any(self.deprecated_fields)

    def render(self) -> str:
        formatter = Formatter()
        formatter.writeline("@dataclass(eq=False, repr=False)")
        formatter.writeline(f"class {self.py_name}(cbiproto.Message):")
        with formatter.block_with_comment(self.get_comment()):
            for fld in self.fields:
                formatter.writelines(fld.render())
            if not self.fields:
                formatter.writeline("pass")

            if self.deprecated or self.has_deprecated_fields:
                formatter.writeline("def __post_init__(self) -> None:")
                with formatter.block():
                    if self.deprecated:
                        formatter.writeline(f"warnings.warn('{self.py_name} is deprecated', DeprecationWarning)")
                    if self.has_deprecated_fields:
                        for fld in self.deprecated_fields:
                            formatter.writeline(f"if self.is_set('{fld}'):")
                            with formatter.block():
                                formatter.writeline(
                                    f"warnings.warn('{self.py_name}.{fld} is deprecated', DeprecationWarning)"
                                )
        return str(formatter)


@dataclass
class FieldCompiler(MessageCompiler):
    parent: MessageCompiler = unset()
    proto_obj: FieldDescriptorProto = unset()

    def __post_init__(self) -> None:
        self.add_imports_to(self.output_file)
        super().__post_init__()

    @property
    def cbiproto_field_args(self) -> List[str]:
        args = []
        if self.field_wraps:
            args.append(f"wraps={self.field_wraps}")
        if self.optional:
            args.append("optional=True")
        return args

    @property
    def datetime_imports(self) -> Set[str]:
        imports = set()
        annotation = self.annotation
        # FIXME: false positives - e.g. `MyDatetimedelta`
        if "timedelta" in annotation:
            imports.add("timedelta")
        if "datetime" in annotation:
            imports.add("datetime")
        return imports

    @property
    def typing_imports(self) -> Set[str]:
        imports = set()
        annotation = self.annotation
        if "Optional[" in annotation:
            imports.add("Optional")
        if "List[" in annotation:
            imports.add("List")
        if "Dict[" in annotation:
            imports.add("Dict")
        return imports

    @property
    def use_builtins(self) -> bool:
        return self.py_type in self.parent.builtins_types or (
            self.py_type == self.py_name and self.py_name in dir(builtins)
        )

    def add_imports_to(self, output_file: OutputTemplate) -> None:
        output_file.datetime_imports.update(self.datetime_imports)
        output_file.typing_imports.update(self.typing_imports)
        output_file.builtins_import = output_file.builtins_import or self.use_builtins

    @property
    def field_wraps(self) -> Optional[str]:
        match_wrapper = re.match(r"\.google\.protobuf\.(.+)Value$", self.proto_obj.type_name)
        if match_wrapper:
            wrapped_type = "TYPE_" + match_wrapper.group(1).upper()
            if hasattr(cbiproto, wrapped_type):
                return f"cbiproto.{wrapped_type}"
        return None

    @property
    def repeated(self) -> bool:
        return self.proto_obj.label == FieldDescriptorProto.Label.LABEL_REPEATED and not is_map(
            self.proto_obj, self.parent
        )

    @property
    def optional(self) -> bool:
        return self.proto_obj.proto3_optional

    @property
    def mutable(self) -> bool:
        return self.annotation.startswith(("List[", "Dict["))

    @property
    def field_type(self) -> str:
        return FieldDescriptorProto.Type(self.proto_obj.type).name.lower().replace("type_", "")

    @property
    def default_value_string(self) -> str:
        if self.repeated:
            return "[]"
        if self.optional:
            return "None"
        if self.py_type == "int":
            return "0"
        if self.py_type == "float":
            return "0.0"
        elif self.py_type == "bool":
            return "False"
        elif self.py_type == "str":
            return '""'
        elif self.py_type == "bytes":
            return 'b""'
        elif self.field_type == "enum":
            enum_proto_obj_name = self.proto_obj.type_name.split(".").pop()
            enum = next(e for e in self.output_file.enums if e.proto_obj.name == enum_proto_obj_name)
            return enum.default_value_string
        else:
            # Message type
            return "None"

    @property
    def packed(self) -> bool:
        return self.repeated and self.proto_obj.type in PROTO_PACKED_TYPES

    @property
    def py_name(self) -> str:
        return pythonize_field_name(self.proto_name)

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def py_type(self) -> str:
        if self.proto_obj.type in PROTO_FLOAT_TYPES:
            return "float"
        elif self.proto_obj.type in PROTO_INT_TYPES:
            return "int"
        elif self.proto_obj.type in PROTO_BOOL_TYPES:
            return "bool"
        elif self.proto_obj.type in PROTO_STR_TYPES:
            return "str"
        elif self.proto_obj.type in PROTO_BYTES_TYPES:
            return "bytes"
        elif self.proto_obj.type in PROTO_MESSAGE_TYPES:
            # Type referencing another defined Message or a named enum
            type_name = get_type_reference(
                package=self.output_file.package,
                imports=self.output_file.imports,
                source_type=self.proto_obj.type_name,
            )
            return type_name
        else:
            raise NotImplementedError(f"Unknown type {self.proto_obj.type}")

    @property
    def annotation(self) -> str:
        py_type = self.py_type
        if self.use_builtins:
            py_type = f"builtins.{py_type}"
        if self.repeated:
            return f"List[{py_type}]"
        if self.optional:
            return f"Optional[{py_type}]"
        return py_type

    def render(self) -> str:
        field_args = ", ".join(([""] + self.cbiproto_field_args) if self.cbiproto_field_args else [])
        cbiproto_field_type = f"cbiproto.{self.field_type}_field({self.proto_obj.number}{field_args})"

        if self.py_name in dir(builtins):
            self.parent.builtins_types.add(self.py_name)

        if comment := self.get_comment():
            comment = f"\n{comment}\n"
        return f"{self.py_name}: {self.annotation} = {cbiproto_field_type}{comment}"


@dataclass
class EnumDefinitionCompiler(MessageCompiler):
    """Representation of a proto Enum definition."""

    proto_obj: EnumDescriptorProto = unset()
    entries: List["EnumDefinitionCompiler.EnumEntry"] = unset()

    @dataclass(unsafe_hash=True)
    class EnumEntry:
        """Representation of an Enum entry."""

        name: str
        value: int
        comment: str

    def __post_init__(self) -> None:
        # Get entries/allowed values for this Enum
        self.entries = [
            self.EnumEntry(
                name=sanitize_name(entry_proto_value.name),
                value=entry_proto_value.number,
                comment=get_comment(proto_file=self.source_file, path=self.path + [2, entry_number]),
            )
            for entry_number, entry_proto_value in enumerate(self.proto_obj.value)
        ]
        super().__post_init__()  # call MessageCompiler __post_init__

    @property
    def default_value_string(self) -> str:
        return str(self.entries[0].value)

    def render(self) -> str:
        formatter = Formatter()
        formatter.writeline(f"class {self.py_name}(cbiproto.Enum):")
        with formatter.block_with_comment(self.get_comment()):
            for entry in self.entries:
                formatter.writeline(f"{entry.name} = {entry.value}")
                if entry.comment:
                    formatter.writelines(entry.comment).newline()
            formatter.newline()
        return str(formatter)


@dataclass
class ServiceCompiler(ProtoContentBase):
    source_file: FileDescriptorProto = unset()
    parent: OutputTemplate = unset()
    proto_obj: ServiceDescriptorProto = unset()
    path: List[int] = unset()
    type_name: str = unset()
    methods: List["ServiceMethodCompiler"] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.output_file.services.append(self)
        self.output_file.typing_imports.add("Dict")
        self.output_file.imports.add("from cbiproto.runtime.server import ServiceBase")
        super().__post_init__()

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.proto_name)

    def render_client(self) -> str:
        formatter = Formatter()
        formatter.writeline(f"class {self.py_name}(cbiproto.ServiceStub):")
        with formatter.block_with_comment(self.get_comment()):
            for method in self.methods:
                formatter.writelines(method.render_client())
            if not self.methods:
                formatter.writeline("pass")
        return str(formatter)

    def render_server(self) -> str:
        formatter = Formatter()
        formatter.writeline(f"class {self.py_name}Base(ServiceBase):")
        with formatter.block_with_comment(self.get_comment()):
            for method in self.methods:
                formatter.writelines(method.render_server())

            formatter.writeline("def __mapping__(self) -> Dict[str, cbiproto.runtime.Handler]:")
            with formatter.block():
                formatter.writeline("return {")
                with formatter.block():
                    for method in self.methods:
                        formatter.writeline(
                            f"'{method.route}': "
                            f"cbiproto.runtime.Handler(self.{method.py_name}, "
                            f"cbiproto.runtime.Cardinality.{method.cardinality.name}, "
                            f"{method.py_input_message_type}, "
                            f"{method.py_output_message_type}),"
                        )
                formatter.writeline("}")
        return str(formatter)


@dataclass
class ServiceMethodCompiler(ProtoContentBase):
    parent: ServiceCompiler
    proto_obj: MethodDescriptorProto
    path: List[int] = unset()

    def __post_init__(self) -> None:
        # Add method to service
        self.parent.methods.append(self)

        # Check for imports
        if "Optional" in self.py_output_message_type:
            self.output_file.typing_imports.add("Optional")

        self.output_file.imports.add("import grpc")

        # Required by both client and server
        if self.client_streaming or self.server_streaming:
            if self.output_file.mode == "async":
                self.output_file.typing_imports.add("AsyncIterable")
            self.output_file.typing_imports.add("Iterable")

        # add imports required for request arguments timeout, deadline and metadata
        self.output_file.typing_imports.add("Optional")
        self.output_file.imports_type_checking_only.add("from cbiproto.runtime.types import MetadataLike")
        self.source_file = self.parent.source_file

        super().__post_init__()  # check for unset fields

    @property
    def py_name(self) -> str:
        return pythonize_method_name(self.proto_obj.name)

    @property
    def proto_name(self) -> str:
        return self.proto_obj.name

    @property
    def route(self) -> str:
        package_part = f"{self.output_file.package}." if self.output_file.package else ""
        return f"/{package_part}{self.parent.proto_name}/{self.proto_name}"

    @property
    def py_input_message(self) -> Optional[MessageCompiler]:
        for msg in self.request.all_messages:
            if msg.type_name == self.proto_obj.input_type:
                return msg
        return None

    @property
    def py_input_message_type(self) -> str:
        return get_type_reference(
            package=self.output_file.package, imports=self.output_file.imports, source_type=self.proto_obj.input_type,
        ).strip('"')

    @property
    def py_input_message_param(self) -> str:
        return "request"

    @property
    def py_output_message_type(self) -> str:
        return get_type_reference(
            package=self.output_file.package,
            imports=self.output_file.imports,
            source_type=self.proto_obj.output_type,
            unwrap=False,
        ).strip('"')

    @property
    def client_streaming(self) -> bool:
        return self.proto_obj.client_streaming

    @property
    def server_streaming(self) -> bool:
        return self.proto_obj.server_streaming

    @property
    def cardinality(self) -> Cardinality:
        return Cardinality.of(self.client_streaming, self.server_streaming)

    @property
    def client_method_name(self) -> str:
        return "_" + self.cardinality.name.lower()

    @property
    def is_async(self) -> bool:
        return self.output_file.mode == "async"

    def render_client(self) -> str:
        iterator_type = "AsyncIterable" if self.output_file.mode == "async" else "Iterable"
        input_type = self.py_input_message_type
        output_type = self.py_output_message_type
        if self.client_streaming:
            input_type = f"{iterator_type}[{input_type}]"
        if self.server_streaming:
            output_type = f"{iterator_type}[{output_type}]"

        timeout_metadata_def = 'timeout: Optional[float] = None, metadata: Optional["MetadataLike"] = None'
        timeout_metadata = "timeout=timeout, metadata=metadata"
        formatter = Formatter()

        method = f"def {self.py_name}(self, request: {input_type}, *, {timeout_metadata_def}) -> {output_type}:"
        if self.is_async:
            method = "async " + method
        formatter.writeline(method)
        with formatter.block_with_comment(self.get_comment()):
            statement = (
                f"return self.{self.client_method_name}"
                f'("{self.route}", request, {self.py_output_message_type}, {timeout_metadata})'
            )
            formatter.writeline(statement)
        return str(formatter)

    def render_server(self) -> str:
        iterator_type = "AsyncIterable" if self.output_file.mode == "async" else "Iterable"
        input_type = self.py_input_message_type
        output_type = self.py_output_message_type
        if self.client_streaming:
            input_type = f"{iterator_type}[{input_type}]"
        if self.server_streaming:
            output_type = f"{iterator_type}[{output_type}]"

        formatter = Formatter()
        method = f"def {self.py_name}(self, request: {input_type}, context: grpc.ServicerContext) -> {output_type}:"
        if self.is_async:
            method = "async " + method
        formatter.writeline(method)
        with formatter.block_with_comment(self.get_comment()):
            formatter.writeline("raise cbiproto.runtime.GRPCError(cbiproto.runtime.Status.UNIMPLEMENTED)")
        return str(formatter)


@dataclass
class OneOfFieldCompiler(FieldCompiler):
    @property
    def cbiproto_field_args(self) -> List[str]:
        args = super().cbiproto_field_args
        group = self.parent.proto_obj.oneof_decl[self.proto_obj.oneof_index].name
        args.append(f'group="{group}"')
        return args


@dataclass
class MapEntryCompiler(FieldCompiler):
    py_k_type: Type = unset()
    py_v_type: Type = unset()
    proto_k_type: str = unset()
    proto_v_type: str = unset()

    def __post_init__(self) -> None:
        map_entry = f"{self.proto_obj.name.replace('_', '').lower()}entry"
        for nested in self.parent.proto_obj.nested_type:
            if nested.name.replace("_", "").lower() == map_entry and nested.options.map_entry:
                # Get Python types
                self.py_k_type = FieldCompiler(
                    source_file=self.source_file, parent=self, proto_obj=nested.field[0],  # key
                ).py_type
                self.py_v_type = FieldCompiler(
                    source_file=self.source_file, parent=self, proto_obj=nested.field[1],  # value
                ).py_type

                # Get proto types
                self.proto_k_type = FieldDescriptorProto.Type(nested.field[0].type).name
                self.proto_v_type = FieldDescriptorProto.Type(nested.field[1].type).name
        super().__post_init__()

    @property
    def cbiproto_field_args(self) -> List[str]:
        return [f"cbiproto.{self.proto_k_type}", f"cbiproto.{self.proto_v_type}"]

    @property
    def field_type(self) -> str:
        return "map"

    @property
    def annotation(self) -> str:
        return f"Dict[{self.py_k_type}, {self.py_v_type}]"

    @property
    def repeated(self) -> bool:
        return False  # maps cannot be repeated


def is_map(proto_field_obj: FieldDescriptorProto, parent_message: Union[DescriptorProto, ProtoContentBase]) -> bool:
    """True if proto_field_obj is a map, otherwise False."""
    if proto_field_obj.type == FieldDescriptorProto.Type.TYPE_MESSAGE:
        if not isinstance(parent_message, DescriptorProto):
            return False

        # This might be a map...
        message_type = proto_field_obj.type_name.split(".").pop().lower()
        map_entry = f"{proto_field_obj.name.replace('_', '').lower()}entry"
        if message_type == map_entry:
            for nested in parent_message.nested_type:  # parent message
                if nested.name.replace("_", "").lower() == map_entry and nested.options.map_entry:
                    return True
    return False


def is_oneof(proto_field_obj: FieldDescriptorProto) -> bool:
    """
    True if proto_field_obj is a OneOf, otherwise False.

    .. warning::
        Becuase the message from protoc is defined in proto2, and cbiproto works with
        proto3, and interpreting the FieldDescriptorProto.oneof_index field requires
        distinguishing between default and unset values (which proto3 doesn't support),
        we have to hack the generated FieldDescriptorProto class for this to work.
        The hack consists of setting group="oneof_index" in the field metadata,
        essentially making oneof_index the sole member of a one_of group, which allows
        us to tell whether it was set, via the which_one_of interface.
    """

    return which_one_of(proto_field_obj, "oneof_index")[0] == "oneof_index"
