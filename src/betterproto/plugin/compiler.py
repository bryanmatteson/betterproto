from __future__ import annotations

import itertools
import pathlib
import re
import sys
import textwrap
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
    cast,
)

from typing_extensions import TypeAlias, dataclass_transform

import betterproto

from .._casing import sanitize_name
from ..lib.google.protobuf import (
    DescriptorProto,
    EnumDescriptorProto,
    EnumOptions,
    EnumValueDescriptorProto,
    EnumValueOptions,
    FieldDescriptorProto,
    FieldOptions,
    FileDescriptorProto,
    FileOptions,
    MessageOptions,
    MethodDescriptorProto,
    MethodOptions,
    ServiceDescriptorProto,
    ServiceOptions,
    SourceCodeInfo,
)
from ..lib.google.protobuf.compiler import CodeGeneratorRequest, CodeGeneratorResponse
from .utils import Formatter, TypeManager, pythonize_class_name, pythonize_field_name, pythonize_method_name

try:
    # betterproto[compiler] specific dependencies
    import black
    import isort.api
except ImportError as err:
    print(
        "\033[31m"
        f"Unable to import `{err.name}` from betterproto plugin! "
        "Please ensure that you've installed betterproto as "
        '`pip install "betterproto[compiler]"` so that compiler dependencies '
        "are included."
        "\033[0m"
    )
    raise SystemExit(1)

if TYPE_CHECKING:
    from dataclasses import field

    @dataclass_transform(kw_only_default=True, field_specifiers=(field,))
    def dataclass(
        cls=None,
        /,
        *,
        init=True,
        repr=True,
        eq=True,
        order=False,
        unsafe_hash=False,
        frozen=False,
        match_args=True,
        kw_only=False,
        slots=False,
    ) -> Any:
        ...

else:
    from dataclasses import dataclass, field


if TYPE_CHECKING:
    pass

_ProtoContentObject = Union[
    FileDescriptorProto,
    DescriptorProto,
    ServiceDescriptorProto,
    MethodDescriptorProto,
    EnumDescriptorProto,
    FieldDescriptorProto,
    EnumValueDescriptorProto,
]
_ProtoParent: TypeAlias = "Union[ProtoFile, ProtoMessage, ProtoEnum, ProtoService]"

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


from pydantic import BaseModel


def generate_code(input_request: CodeGeneratorRequest) -> CodeGeneratorResponse:
    compiler = Compiler(CompilationOptions.parse_args(input_request.parameter))
    compiler.add_source_files(*input_request.proto_file)
    return compiler.compile(*input_request.file_to_generate)


class CompilationOptions(BaseModel):
    mode: Optional[Literal["sync", "async"]] = None
    include_google: bool = False

    @classmethod
    def parse_args(cls, args: str) -> "CompilationOptions":
        all_options = [x.lower() for x in args.split(",")]
        options: Dict[str, Any] = {}
        for option in all_options:
            if "=" in option:
                key, value = option.split("=", 1)
                options[key] = value
            else:
                options[option] = True
        return cls(**options)


@dataclass
class CompilationContext:
    input_files: Mapping[str, ProtoFile]
    extensions: Dict[str, List[ProtoField]] = field(default_factory=dict, init=False)
    current_file: Optional[ProtoFile] = None
    messages_by_type: Dict[str, ProtoMessage] = field(init=False)
    mode: Union[str, Literal["async", "sync"]] = "sync"

    def __post_init__(self) -> None:
        for type_name, fields in itertools.chain.from_iterable(x.extensions.items() for x in self.input_files.values()):
            self.extensions.setdefault(type_name, []).extend(fields)

        self.messages_by_type = {
            f".{file.package}.{msg.fully_qualified_path}": msg
            for file in self.input_files.values()
            for msg in file.messages.values()
        }

    def set_current_file(self, file: ProtoFile) -> None:
        self.current_file = file

    def set_mode(self, mode: Union[str, Literal["async", "sync"]]) -> None:
        self.mode = mode

    @property
    def is_async(self) -> bool:
        return self.mode == "async"


class Compiler:
    def __init__(self, options: CompilationOptions) -> None:
        self.options = options
        self.files: Dict[str, ProtoFile] = {}

    def add_source_files(self, *files: FileDescriptorProto):
        self.files.update({file.name: build_file(file) for file in files})

    def compile(self, *files: str) -> CodeGeneratorResponse:
        context = CompilationContext(input_files=self.files)
        context.set_mode(self.options.mode or "sync")
        for extension in context.extensions:
            if msg := context.messages_by_type.get(extension):
                msg.add_fields(*context.extensions[extension])

        header = textwrap.dedent(
            """
            # Generated by the protocol buffer compiler.  DO NOT EDIT!
            # type: ignore
            # flake8: noqa
            # nopycln: file
            # pyright: ignore
            # mypy: ignore-errors
            # fmt: off
            """
        ).lstrip()

        response = CodeGeneratorResponse(supported_features=CodeGeneratorResponse.Feature.FEATURE_PROTO3_OPTIONAL)
        output_paths: Set[pathlib.Path] = set()
        for file in map(self.files.__getitem__, files):
            if file.package == "google.protobuf" and not self.options.include_google:
                continue

            if not file.messages and not file.enums and not file.services:
                continue

            file.types.from_import("__future__", "annotations")
            context.set_current_file(file)
            code = file.compile(context)

            import_statements = "\n".join(file.types.get_all_imports()) + "\n\n"
            code = isort.api.sort_code_string(
                code="\n".join((import_statements, code)),
                show_diff=False,
                py_version=37,
                profile="black",
                combine_as_imports=True,
                lines_after_imports=2,
                quiet=True,
                force_grid_wrap=2,
                known_third_party=["grpc", "betterproto"],
            )
            code = black.format_str(code, mode=black.FileMode(line_length=120))
            code = "\n".join((header, code))

            output_file = "__init__.py"
            output_path = pathlib.Path(*file.package.split("."), output_file)
            output_paths.add(output_path)
            response.file.append(CodeGeneratorResponse.File(name=str(output_path), content=code))

        init_files = {
            directory.joinpath("__init__.py")
            for path in output_paths
            for directory in path.parents
            if not directory.joinpath("__init__.py").exists()
        } - output_paths

        for init_file in init_files:
            response.file.append(CodeGeneratorResponse.File(name=str(init_file)))

        for pkg_name in sorted(output_paths.union(init_files)):
            print(f"Writing {pkg_name}", file=sys.stderr)

        return response


@dataclass
class NamedModel:
    model: Any

    @property
    def name(self) -> str:
        return self.model.name

    @property
    def options(
        self,
    ) -> Union[FileOptions, MessageOptions, ServiceOptions, MethodOptions, EnumOptions, FieldOptions, EnumValueOptions]:
        return self.model.options


@dataclass
class ProtoContent(NamedModel):
    file: ProtoFile
    comment: str
    fully_qualified_path: str
    index_path: Tuple[int, ...]
    parent: Optional[_ProtoParent]


@dataclass
class ProtoFile(NamedModel):
    model: FileDescriptorProto

    messages: Dict[str, ProtoMessage] = field(default_factory=dict)
    enums: Dict[str, ProtoEnum] = field(default_factory=dict)
    services: Dict[str, ProtoService] = field(default_factory=dict)
    extensions: Dict[str, List[ProtoField]] = field(default_factory=dict)
    types: TypeManager = field(init=False)

    def __post_init__(self) -> None:
        self.types = TypeManager(self.model.package)

    def add_messages(self, *messages: ProtoMessage):
        self.messages.update({message.name: message for message in messages})

    def add_enums(self, *enums: ProtoEnum):
        self.enums.update({enum.name: enum for enum in enums})

    def add_services(self, *services: ProtoService):
        self.services.update({svc.name: svc for svc in services})

    def add_extensions(self, *extensions: ProtoField):
        for e in extensions:
            self.extensions.setdefault(e.model.extendee, []).extend(extensions)

    @property
    def package(self) -> str:
        return self.model.package

    def compile(self, context: CompilationContext) -> str:
        formatter = Formatter()

        for e in self.enums.values():
            formatter.writelines(e.compile(context))

        for m in self.messages.values():
            formatter.writelines(m.compile(context))

        for s in self.services.values():
            formatter.writelines(s.compile_client(context))

        for s in self.services.values():
            formatter.writelines(s.compile_server(context))
        return str(formatter)


@dataclass
class ProtoMessage(ProtoContent):
    model: DescriptorProto

    fields: Dict[str, ProtoField] = field(default_factory=dict)
    messages: Dict[str, ProtoMessage] = field(default_factory=dict)
    enums: Dict[str, ProtoEnum] = field(default_factory=dict)

    def add_enums(self, *enums: ProtoEnum):
        self.enums.update({enum.name: enum for enum in enums})

    def add_messages(self, *messages: ProtoMessage):
        self.messages.update({message.name: message for message in messages})

    def add_fields(self, *fields: ProtoField):
        self.fields.update({field.name: field for field in fields})

    @property
    def is_map_entry(self) -> bool:
        return self.model.options.map_entry

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.name)

    @property
    def annotation(self) -> str:
        return self.py_name

    @property
    def deprecated_fields(self) -> Iterator[str]:
        for f in self.fields.values():
            if f.model.options.deprecated:
                yield f.py_name

    def compile(self, ctx: CompilationContext) -> str:
        formatter = Formatter()
        dc = self.file.types.from_import("dataclasses", "dataclass")
        formatter.writeline(f"@{dc}(eq=False, repr=False)")
        msg_type = self.file.types.module_import("betterproto", "Message")

        formatter.writeline(f"class {self.py_name}({msg_type}):")
        with formatter.block_with_comment(self.comment):
            for fld in self.fields.values():
                formatter.writelines(fld.compile(ctx))

            for e in self.enums.values():
                formatter.writelines(e.compile(ctx))

            for m in self.messages.values():
                if not m.is_map_entry:
                    formatter.writelines(m.compile(ctx))

            if not self.fields and not self.enums and not self.messages:
                formatter.writeline("pass")

            if self.model.options.deprecated or any(self.deprecated_fields):
                warn_mod = self.file.types.module_import("warnings", "warn")
                formatter.writeline("def __post_init__(self) -> None:")
                with formatter.block():
                    if self.model.options.deprecated:
                        formatter.writeline(f"{warn_mod}('{self.py_name} is deprecated', DeprecationWarning)")
                    for fld in self.deprecated_fields:
                        formatter.writeline(f"if self.is_set('{fld}'):")
                        with formatter.block():
                            formatter.writeline(f"{warn_mod}('{self.py_name}.{fld} is deprecated', DeprecationWarning)")

        return str(formatter)


@dataclass
class ProtoField(ProtoContent):
    parent: Union[ProtoMessage, ProtoFile, None]
    model: FieldDescriptorProto

    @property
    def optional(self) -> bool:
        return self.model.proto3_optional

    @property
    def is_one_of_field(self) -> bool:
        name, _ = betterproto.which_one_of(self.model, "oneof_index")
        return name == "oneof_index"

    @property
    def is_map_field(self) -> bool:
        if self.model.type == FieldDescriptorProto.Type.TYPE_MESSAGE:
            if isinstance(self.parent, ProtoMessage):
                _, type_name = self.model.type_name.rsplit(".", 1)
                if entry := self.parent.messages.get(type_name):
                    return entry.model.options.map_entry
        return False

    @property
    def repeated(self) -> bool:
        return self.model.label == FieldDescriptorProto.Label.LABEL_REPEATED and not self.is_map_field

    @property
    def field_type(self) -> str:
        if self.is_map_field:
            return "map"
        return FieldDescriptorProto.Type(self.model.type).name.lower().replace("type_", "")

    @property
    def py_name(self) -> str:
        return pythonize_field_name(self.name)

    @property
    def py_type(self) -> str:
        if self.model.type in PROTO_FLOAT_TYPES:
            return "float"
        elif self.model.type in PROTO_INT_TYPES:
            return "int"
        elif self.model.type in PROTO_BOOL_TYPES:
            return "bool"
        elif self.model.type in PROTO_STR_TYPES:
            return "str"
        elif self.model.type in PROTO_BYTES_TYPES:
            return "bytes"
        elif self.model.type in PROTO_MESSAGE_TYPES:
            # Type referencing another defined Message or a named enum
            return self.file.types.get_type_reference(self.model.type_name)
        else:
            raise NotImplementedError(f"Unknown type {self.model.type}")

    @property
    def annotation(self) -> str:
        if self.is_map_field:
            parent = cast(ProtoMessage, self.parent)
            _, type_name = self.model.type_name.rsplit(".", 1)
            entry = parent.messages[type_name]
            key, value = entry.fields["key"], entry.fields["value"]
            return self.file.types.dict_of(key.py_type, value.py_type)

        py_type = self.py_type
        if self.repeated:
            return self.file.types.list_of(py_type)

        if self.optional:
            return self.file.types.optional_of(py_type)
        return py_type

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
            enum_proto_obj_name = self.model.type_name.split(".").pop()
            enum = next(e for e in self.file.enums.values() if e.name == enum_proto_obj_name)
            return enum.default_value_string
        else:
            return "None"

    @property
    def cbproto_field_args(self) -> List[str]:
        args: List[str] = []

        if self.is_map_field:
            parent = cast(ProtoMessage, self.parent)
            _, type_name = self.model.type_name.rsplit(".", 1)
            if entry := parent.messages.get(type_name):
                key, value = entry.fields["key"], entry.fields["value"]
                proto_k_type = FieldDescriptorProto.Type(key.model.type).name
                proto_v_type = FieldDescriptorProto.Type(value.model.type).name
                args.extend(
                    [
                        self.file.types.from_import("betterproto.const", proto_k_type),
                        self.file.types.from_import("betterproto.const", proto_v_type),
                    ]
                )

        if match_wrapper := re.match(r"\.google\.protobuf\.(.+)Value$", self.model.type_name):
            wrapped_type = "TYPE_" + match_wrapper.group(1).upper()
            if hasattr(betterproto, wrapped_type):
                typ = self.file.types.module_import(f"betterproto", wrapped_type)
                args.append(f"wraps={typ}")

        if self.optional:
            args.append("optional=True")

        if self.is_one_of_field and isinstance(self.parent, ProtoMessage):
            args.append(f"group={self.parent.model.oneof_decl[self.model.oneof_index].name!r}")

        return args

    def compile(self, ctx: CompilationContext) -> str:
        field_args = ", ".join([""] + self.cbproto_field_args)

        fn = self.file.types.module_import("betterproto", f"{self.field_type}_field")
        cbproto_field_type = f"{fn}({self.model.number}{field_args})"
        if comment := self.comment:
            comment = f"\n{comment}\n"
        return f"{self.py_name}: {self.annotation} = {cbproto_field_type}{comment}"


@dataclass
class ProtoService(ProtoContent):
    parent: ProtoFile
    model: ServiceDescriptorProto
    methods: Dict[str, ProtoMethod] = field(default_factory=dict)

    def add_methods(self, *methods: ProtoMethod):
        self.methods.update({method.name: method for method in methods})

    @property
    def py_name(self) -> str:
        return pythonize_class_name(self.name)

    def compile_client(self, ctx: CompilationContext) -> str:
        stub_base = "betterproto.aio" if ctx.is_async else "betterproto"
        stub_name = self.file.types.module_import(stub_base, "ServiceStub")

        client_stub = Formatter()
        client_stub.writeline(f"class {self.py_name}Stub({stub_name}):")
        with client_stub.block_with_comment(self.comment):
            for method in self.methods.values():
                client_stub.writelines(method.compile_client(ctx))
            if not self.methods:
                client_stub.writeline("pass\n")
        return str(client_stub)

    def compile_server(self, ctx: CompilationContext) -> str:
        stub_base = "betterproto.aio" if ctx.is_async else "betterproto"
        stub_name = self.file.types.module_import(stub_base, "ServiceBase")

        server_stub = Formatter()
        server_stub.writeline(f"class {self.py_name}Base({stub_name}):")
        with server_stub.block_with_comment(self.comment):
            for method in self.methods.values():
                server_stub.writelines(method.compile_server(ctx))

            handler_type = self.file.types.module_import("betterproto", "Handler")
            typing_dict = self.file.types.dict_of("str", handler_type)
            cardinality_type = self.file.types.module_import("betterproto", "Cardinality")

            server_stub.writeline(f"def __mapping__(self) -> {typing_dict}:")
            with server_stub.block():
                server_stub.writeline("return {")
                with server_stub.block():
                    for method in self.methods.values():
                        server_stub.writeline(
                            f"'{method.route}': "
                            f"{handler_type}(self.{method.py_name}, "
                            f"{cardinality_type}.{method.cardinality.name}, "
                            f"{method.py_input_message_type}, "
                            f"{method.py_output_message_type}),"
                        )
                server_stub.writeline("}\n")

        return str(server_stub)


@dataclass
class ProtoMethod(ProtoContent):
    parent: ProtoService
    model: MethodDescriptorProto

    @property
    def py_name(self) -> str:
        return pythonize_method_name(self.name)

    @property
    def route(self) -> str:
        package_part = f"{self.file.package}." if self.file.package else ""
        return f"/{package_part}{self.parent.name}/{self.name}"

    @property
    def cardinality(self) -> betterproto.Cardinality:
        return betterproto.Cardinality.of(self.model.client_streaming, self.model.server_streaming)

    @property
    def py_input_message_type(self) -> str:
        return self.file.types.get_type_reference(self.model.input_type)

    @property
    def py_output_message_type(self) -> str:
        return self.file.types.get_type_reference(self.model.output_type, unwrap=False)

    @property
    def client_method_name(self) -> str:
        return self.cardinality.name.lower()

    def compile_client(self, ctx: CompilationContext) -> str:
        input_type = self.py_input_message_type
        output_type = self.py_output_message_type

        metadata_like = self.file.types.module_import("betterproto.types", "MetadataLike")
        grpc_creds_type = self.file.types.module_import("grpc", "CallCredentials")

        if self.model.client_streaming:
            input_type = self.file.types.iterable_of(input_type, ctx.is_async)
        if self.model.server_streaming:
            output_type = self.file.types.iterable_of(output_type, ctx.is_async)
        elif ctx.is_async:
            output_type = self.file.types.awaitable_of(output_type)

        opt_float = self.file.types.optional_of("float")
        opt_metadata = self.file.types.optional_of(metadata_like)
        opt_creds = self.file.types.optional_of(grpc_creds_type)
        kwargs_def = (
            f"timeout: {opt_float} = None, "
            f"metadata: {opt_metadata} = None, "
            f"call_credentials: {opt_creds} = None"
        )
        formatter = Formatter()

        method = f"def {self.py_name}(self, request: {input_type}, *, {kwargs_def}) -> {output_type}:"
        formatter.writeline(method)
        with formatter.block_with_comment(self.comment):
            formatter.writeline(
                f"mc = self.channel.{self.client_method_name}"
                f"({self.route!r}, {self.py_input_message_type}.__bytes__, {self.py_output_message_type}.parse_raw)"
            )
            if self.model.client_streaming:
                request_arg = "iter(request)" if not ctx.is_async else "request.__aiter__()"
            else:
                request_arg = "request"

            formatter.writeline(
                f"return mc({request_arg}, credentials=call_credentials, "
                f"**self._resolve_request_kwargs(timeout, metadata))"
            )
        return str(formatter)

    def compile_server(self, ctx: CompilationContext) -> str:
        input_type = self.py_input_message_type
        output_type = self.py_output_message_type

        if self.model.client_streaming:
            input_type = self.file.types.iterable_of(input_type, ctx.is_async)
        if self.model.server_streaming:
            output_type = self.file.types.iterable_of(output_type, ctx.is_async)

        grpcmod = "grpc.aio" if ctx.is_async else "grpc"
        formatter = Formatter()
        ctx_type = self.file.types.module_import(grpcmod, "ServicerContext")
        method = f"def {self.py_name}(self, request: {input_type}, context: {ctx_type}) -> {output_type}:"
        if ctx.is_async:
            method = "async " + method
        formatter.writeline(method)
        status_code = self.file.types.module_import("grpc", "StatusCode")
        with formatter.block_with_comment(self.comment):
            formatter.writeline(f"context.set_code({status_code}.UNIMPLEMENTED)")
            formatter.writeline(f'context.set_details("Route {self.route} not implemented")')
            formatter.writeline(f'raise NotImplementedError("Route {self.route} not implemented!")')
        return str(formatter)


@dataclass
class ProtoEnum(ProtoContent):
    model: EnumDescriptorProto
    entries: List[EnumEntry] = field(default_factory=list)

    def add_entries(self, *entries: EnumEntry):
        self.entries.extend(entries)

    @property
    def default_value_string(self) -> str:
        return str(self.entries[0].value)

    @property
    def py_name(self) -> str:
        return sanitize_name(self.name)

    def compile(self, ctx: CompilationContext) -> str:
        formatter = Formatter()
        enum_type = self.file.types.module_import("betterproto", "Enum")
        formatter.writeline(f"class {self.py_name}({enum_type}):")
        with formatter.block_with_comment(self.comment):
            for entry in self.entries:
                formatter.writeline(f"{entry.name} = {entry.value}")
                if entry.comment:
                    formatter.writelines(entry.comment).newline()
            formatter.newline()
        return str(formatter)


@dataclass
class EnumEntry(ProtoContent):
    parent: ProtoEnum
    model: EnumValueDescriptorProto

    @property
    def value(self) -> int:
        return self.model.number


def build_file(f: FileDescriptorProto) -> ProtoFile:
    file = ProtoFile(model=f)

    path_to_loc: Dict[Tuple[int, ...], SourceCodeInfo.Location] = {}
    for sci_loc in f.source_code_info.location:
        path_to_loc[tuple(sci_loc.path)] = sci_loc

    def _num(obj: betterproto.Message, name: str) -> int:
        return obj.cbproto_meta.get_field_number(name)

    def _traverse(parent: Optional[_ProtoParent], path: List[int], items: List[Any], prefix: str = "") -> Iterator[Any]:
        for idx, item in enumerate(items):
            idx_path = (*path, idx)
            fqn = ".".join(filter(None, [prefix, item.name]))

            comment = ""
            if idx_path in path_to_loc and path_to_loc[idx_path].leading_comments:
                lines = path_to_loc[idx_path].leading_comments.strip().split("\n")
                fixed_lines: List[str] = []
                for line in lines:
                    i = 0
                    while i < len(line) and line[i] == " ":
                        i += 1
                    fixed_lines.append(line[i % 4 :])

                if len(fixed_lines) == 1:
                    comment = f'"""{fixed_lines[0]}"""'
                joined = "\n".join(fixed_lines)
                comment = f'"""\n{joined}\n"""'

            kwargs: Dict[str, Any] = dict(
                file=file, parent=parent, comment=comment, fully_qualified_path=fqn, index_path=idx_path
            )

            if isinstance(item, DescriptorProto):
                m = ProtoMessage(model=item, **kwargs)
                m.add_fields(*_traverse(m, [*path, idx, _num(item, "field")], item.field, fqn))
                m.add_messages(*_traverse(m, [*path, idx, _num(item, "nested_type")], item.nested_type, fqn))
                m.add_enums(*_traverse(m, [*path, idx, _num(item, "enum_type")], item.enum_type, fqn))
                yield m
            elif isinstance(item, ServiceDescriptorProto):
                service = ProtoService(model=item, **kwargs)
                service.add_methods(*_traverse(service, [*path, idx, _num(item, "method")], item.method, fqn))
                yield service
            elif isinstance(item, EnumDescriptorProto):
                e = ProtoEnum(model=item, **kwargs)
                e.add_entries(*_traverse(e, [*path, idx, _num(item, "value")], item.value, fqn))
                yield e
            elif isinstance(item, FieldDescriptorProto):
                yield ProtoField(model=item, **kwargs)
            elif isinstance(item, EnumValueDescriptorProto):
                yield EnumEntry(model=item, **kwargs)
            elif isinstance(item, MethodDescriptorProto):
                yield ProtoMethod(model=item, **kwargs)

    file.add_enums(*_traverse(file, [_num(f, "enum_type")], f.enum_type))
    file.add_messages(*_traverse(file, [_num(f, "message_type")], f.message_type))
    file.add_services(*_traverse(file, [_num(f, "service")], f.service))
    file.add_extensions(*_traverse(None, [_num(f, "extension")], f.extension))

    return file
