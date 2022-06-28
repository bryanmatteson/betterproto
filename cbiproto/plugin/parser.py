import pathlib
import sys
from typing import Dict, Generator, List, Set, Tuple, Union

from ..lib.google.protobuf import (
    DescriptorProto,
    EnumDescriptorProto,
    FieldDescriptorProto,
    FileDescriptorProto,
    ServiceDescriptorProto,
)
from ..lib.google.protobuf.compiler import CodeGeneratorRequest, CodeGeneratorResponse
from .compiler import outputfile_compiler
from .models import (
    EnumDefinitionCompiler,
    FieldCompiler,
    MapEntryCompiler,
    MessageCompiler,
    OneOfFieldCompiler,
    OutputTemplate,
    PluginRequestCompiler,
    ServiceCompiler,
    ServiceMethodCompiler,
    is_map,
    is_oneof,
)
from .options import PluginOptions


def traverse(
    proto_file: FileDescriptorProto,
) -> Generator[Tuple[Union[EnumDescriptorProto, DescriptorProto], List[int], str], None, None]:
    # Todo: Keep information about nested hierarchy
    def _traverse(
        path: List[int], items: Union[List[EnumDescriptorProto], List[DescriptorProto]], prefix: str = "",
    ) -> Generator[Tuple[Union[EnumDescriptorProto, DescriptorProto], List[int], str], None, None]:
        for i, item in enumerate(items):
            # Adjust the name since we flatten the hierarchy.
            # Todo: don't change the name, but include full name in returned tuple
            next_prefix = ".".join(filter(None, [prefix, item.name]))
            yield item, [*path, i], next_prefix

            if isinstance(item, DescriptorProto):
                # Get nested types.
                yield from _traverse([*path, i, 4], item.enum_type, next_prefix)
                yield from _traverse([*path, i, 3], item.nested_type, next_prefix)

    yield from _traverse([5], proto_file.enum_type)
    yield from _traverse([4], proto_file.message_type)


def generate_code(request: CodeGeneratorRequest) -> CodeGeneratorResponse:
    response = CodeGeneratorResponse(supported_features=CodeGeneratorResponse.Feature.FEATURE_PROTO3_OPTIONAL)
    plugin_options = PluginOptions.parse_args(request.parameter)

    sys.stderr.write(f"\033[31mPlugin options: {plugin_options!r}\033[0m\n")

    data = PluginRequestCompiler(plugin_request_obj=request)

    extensions: Dict[str, List[FieldDescriptorProto]] = {}

    for proto in request.proto_file:
        if proto.package == "google.protobuf" and not plugin_options.include_google:
            continue

        for extension in proto.extension:
            extensions.setdefault(extension.extendee, []).append(extension)

        if not proto.message_type and not proto.enum_type and not proto.service:
            continue

        pkg_name = proto.package
        if pkg_name not in data.output_packages:
            data.output_packages[pkg_name] = OutputTemplate(
                parent_request=data, package_proto_obj=proto, mode=plugin_options.mode,
            )
        data.output_packages[pkg_name].input_files.append(proto)

    # Read Messages and Enums
    # We need to read Messages before Services in so that we can
    # get the references to input/output messages for each service
    for pkg_name, output_package in data.output_packages.items():
        for proto_input_file in output_package.input_files:
            items = {qualname: (item, path) for item, path, qualname in traverse(proto_input_file)}
            keys = sorted(items.keys(), key=lambda x: x.count("."))

            proto_types: Dict[str, Union[MessageCompiler, EnumDefinitionCompiler]] = {}
            for key in keys:
                item, path = items[key]
                read_protobuf_type(
                    source_file=proto_input_file,
                    item=item,
                    path=path,
                    qualname=key,
                    output_package=output_package,
                    extensions=extensions,
                    proto_types=proto_types,
                )

    for pkg_name, output_package in data.output_packages.items():
        for proto_input_file in output_package.input_files:
            for index, service in enumerate(proto_input_file.service):
                read_protobuf_service(service, index, output_package, source_file=proto_input_file)

    output_paths: Set[pathlib.Path] = set()
    for pkg_name, output_package in data.output_packages.items():
        output_path = pathlib.Path(*pkg_name.split("."), "__init__.py")
        output_paths.add(output_path)

        response.file.append(
            CodeGeneratorResponse.File(name=str(output_path), content=outputfile_compiler(output_file=output_package),)
        )

    # Make each output directory a package with __init__ file
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


def read_protobuf_type(
    item: Union[EnumDescriptorProto, DescriptorProto],
    path: List[int],
    qualname: str,
    source_file: FileDescriptorProto,
    output_package: OutputTemplate,
    extensions: Dict[str, List[FieldDescriptorProto]],
    proto_types: Dict[str, Union[MessageCompiler, EnumDefinitionCompiler]],
) -> None:
    type_name = f".{source_file.package}.{qualname}"
    parent = output_package

    if "." in qualname:
        parent = proto_types[qualname.rsplit(".", 1)[0]]

    if isinstance(item, DescriptorProto):
        if item.options.map_entry:
            return
        if type_name in extensions:
            item.field.append(*extensions[type_name])
            sys.stderr.write(
                f"\033[31m{type_name} has extensions: {[x.name for x in extensions[type_name]]!r} \033[0m\n"
            )

        message_data = MessageCompiler(
            source_file=source_file, parent=parent, proto_obj=item, path=path, type_name=type_name, qualname=qualname,
        )
        for index, field in enumerate(item.field):
            if is_map(field, item):
                MapEntryCompiler(
                    source_file=source_file, parent=message_data, proto_obj=field, path=path + [2, index],
                )
            elif is_oneof(field):
                OneOfFieldCompiler(
                    source_file=source_file, parent=message_data, proto_obj=field, path=path + [2, index],
                )
            else:
                FieldCompiler(
                    source_file=source_file, parent=message_data, proto_obj=field, path=path + [2, index],
                )
        proto_types[qualname] = message_data
    elif isinstance(item, EnumDescriptorProto):
        message_data = EnumDefinitionCompiler(
            source_file=source_file, parent=parent, proto_obj=item, path=path, type_name=type_name, qualname=qualname,
        )
        proto_types[qualname] = message_data


def read_protobuf_service(
    service: ServiceDescriptorProto, index: int, output_package: OutputTemplate, source_file: FileDescriptorProto
) -> None:
    service_data = ServiceCompiler(parent=output_package, proto_obj=service, path=[6, index], source_file=source_file)
    for j, method in enumerate(service.method):
        ServiceMethodCompiler(parent=service_data, proto_obj=method, path=[6, index, 2, j])
