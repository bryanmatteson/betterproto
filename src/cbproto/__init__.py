from __future__ import annotations

import dataclasses
import enum
import math
import struct
import sys
import warnings
from abc import ABC
from base64 import b64decode, b64encode
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from dateutil.parser import isoparse
from typing_extensions import Self

from . import aio
from ._casing import camel_case, pascal_case, safe_snake_case, snake_case
from ._types import UNSET
from .client import ServiceStub
from .const import (
    DATETIME_ZERO,
    FIXED_TYPES,
    INFINITY,
    INT_64_TYPES,
    NAN,
    NEG_INFINITY,
    PACKED_TYPES,
    TYPE_BOOL,
    TYPE_BYTES,
    TYPE_DOUBLE,
    TYPE_ENUM,
    TYPE_FIXED32,
    TYPE_FIXED64,
    TYPE_FLOAT,
    TYPE_INT32,
    TYPE_INT64,
    TYPE_MAP,
    TYPE_MESSAGE,
    TYPE_SFIXED32,
    TYPE_SFIXED64,
    TYPE_SINT32,
    TYPE_SINT64,
    TYPE_STRING,
    TYPE_UINT32,
    TYPE_UINT64,
    WIRE_FIXED_32,
    WIRE_FIXED_32_TYPES,
    WIRE_FIXED_64,
    WIRE_FIXED_64_TYPES,
    WIRE_LEN_DELIM,
    WIRE_LEN_DELIM_TYPES,
    WIRE_VARINT,
    WIRE_VARINT_TYPES,
    datetime_default_gen,
)
from .fields import (
    FieldMetadata,
    bool_field,
    bytes_field,
    double_field,
    enum_field,
    fixed32_field,
    fixed64_field,
    float_field,
    int32_field,
    int64_field,
    map_field,
    message_field,
    proto_field,
    sfixed32_field,
    sfixed64_field,
    sint32_field,
    sint64_field,
    string_field,
    uint32_field,
    uint64_field,
)
from .server import Server, ServiceBase, TLSConfig
from .types import Cardinality, Handler, IServable
from .utils import graceful_exit

Casing = Literal["camel", "snake", "pascal"]

MessageT = TypeVar("MessageT", bound="Message")


class Message(ABC):
    """
    The base class for protobuf messages, all generated messages will inherit from
    this. This class registers the message fields which are used by the serializers and
    parsers to go between the Python, binary and JSON representations of the message.
    """

    _cbproto_meta: ClassVar[Optional[ProtoClassMetadata]] = None
    _serialized_on_wire: bool
    _unknown_fields: bytes
    _group_current: Dict[str, str]

    def __post_init__(self) -> None:
        # Keep track of whether every field was default
        all_sentinel = True

        # Set current field of each group after `__init__` has already been run.
        group_current: Dict[str, Optional[str]] = {}
        for field_name, meta in self.cbproto_meta.meta_by_field_name.items():

            if meta.group:
                group_current.setdefault(meta.group)

            value = self.__raw_get(field_name)
            if value != UNSET and not (meta.optional and value is None):
                # Found a non-sentinel value
                all_sentinel = False

                if meta.group:
                    # This was set, so make it the selected value of the one-of.
                    group_current[meta.group] = field_name

        # Now that all the defaults are set, reset it!
        self.__dict__["_serialized_on_wire"] = not all_sentinel
        self.__dict__["_unknown_fields"] = b""
        self.__dict__["_group_current"] = group_current

    def __raw_get(self, name: str) -> Any:
        return super().__getattribute__(name)

    def __eq__(self, other: Message) -> bool:
        if type(self) is not type(other):
            return False

        for field_name in self.cbproto_meta.meta_by_field_name:
            self_val = self.__raw_get(field_name)
            other_val = other.__raw_get(field_name)
            if self_val is UNSET:
                if other_val is UNSET:
                    continue
                self_val = self.cbproto_meta.get_field_default(field_name)
            elif other_val is UNSET:
                other_val = other.cbproto_meta.get_field_default(field_name)

            if self_val != other_val:
                # We consider two nan values to be the same for the
                # purposes of comparing messages (otherwise a message
                # is not equal to itself)
                if (
                    isinstance(self_val, float)
                    and isinstance(other_val, float)
                    and math.isnan(self_val)
                    and math.isnan(other_val)
                ):
                    continue
                else:
                    return False

        return True

    def __repr__(self) -> str:
        parts = [
            f"{field_name}={value!r}"
            for field_name in self.cbproto_meta.sorted_field_names
            for value in (self.__raw_get(field_name),)
            if value is not UNSET
        ]
        return f"{self.__class__.__name__}({', '.join(parts)})"

    if not TYPE_CHECKING:

        def __getattribute__(self, name: str) -> Any:
            """
            Lazily initialize default values to avoid infinite recursion for recursive
            message types
            """
            value = super().__getattribute__(name)
            if value is not UNSET:
                return value

            value = self.cbproto_meta.get_field_default(name)
            super().__setattr__(name, value)
            return value

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr != "_serialized_on_wire":
            self.__dict__["_serialized_on_wire"] = True

        if hasattr(self, "_group_current"):  # __post_init__ had already run
            if attr in self.cbproto_meta.oneof_group_by_field:
                group = self.cbproto_meta.oneof_group_by_field[attr]
                for field in self.cbproto_meta.oneof_field_by_group[group]:
                    if field.name == attr:
                        self._group_current[group] = field.name
                    else:
                        super().__setattr__(field.name, UNSET)

        super().__setattr__(attr, value)

    def __bool__(self) -> bool:
        return any(
            self.__raw_get(field_name) not in (UNSET, self.cbproto_meta.get_field_default(field_name))
            for field_name in self.cbproto_meta.meta_by_field_name
        )

    def __deepcopy__(self: MessageT, _: Any = {}) -> MessageT:
        kwargs = {}
        for name in self.cbproto_meta.sorted_field_names:
            value = self.__raw_get(name)
            if value is not UNSET:
                kwargs[name] = deepcopy(value)
        return self.__class__(**kwargs)  # type: ignore

    def _include_default_value_for_oneof(self, field_name: str, meta: FieldMetadata) -> bool:
        return meta.group is not None and self._group_current.get(meta.group) == field_name

    def is_set(self, name: str) -> bool:
        default = UNSET if not self.cbproto_meta.meta_by_field_name[name].optional else None
        return self.__raw_get(name) is not default

    @classmethod
    @property
    def cbproto_meta(cls) -> ProtoClassMetadata:
        if not cls._cbproto_meta:
            cls._cbproto_meta = ProtoClassMetadata(cls)
        return cls._cbproto_meta

    @classmethod
    def parse_raw(cls, s: bytes) -> Self:
        return deserialize_from_bytes(cls, s)

    @classmethod
    def parse_obj(cls, obj: Dict[str, Any]) -> Self:
        return deserialize_from_dict(cls, obj)

    @classmethod
    def parse_json(cls, obj: str) -> Self:
        import json

        return cls.parse_obj(json.loads(obj))

    def __bytes__(self) -> bytes:
        return serialize_to_bytes(self)

    SerializeToString = __bytes__
    FromString = parse_raw

    def to_dict(self, casing: Casing = "camel", include_defaults: bool = False) -> Dict[str, Any]:
        return serialize_to_dict(self, casing, include_defaults)

    def merge_dict(self: MessageT, value: Dict[str, Any]) -> MessageT:
        return deserialize_from_dict(self, value)

    def to_pydict(self, casing: Casing = "camel", include_defaults: bool = False) -> Dict[str, Any]:
        return serialize_to_pydict(self, casing, include_defaults)

    def merge_pydict(self: MessageT, value: Dict[str, Any]) -> MessageT:
        return deserialize_from_pydict(self, value)

    # def get_extension(self, extension: Type[MessageT]) -> MessageT:
    #     # unknown_fields = parse_fields(self._unknown_fields)
    #     # if extension_field := next(unknown_fields, None):
    #     #     if extension_field.
    #     return extension.parse_raw(self._unknown_fields)


class Enum(enum.IntEnum):
    """
    The base class for protobuf enumerations, all generated enumerations will inherit
    from this. Bases :class:`enum.IntEnum`.
    """

    @classmethod
    def from_string(cls, name: str) -> "Enum":
        try:
            return cls._member_map_[name]  # type: ignore
        except KeyError as e:
            raise ValueError(f"Unknown value {name} for enum {cls.__name__}") from e


class ProtoClassMetadata:
    __slots__ = (
        "oneof_group_by_field",
        "oneof_field_by_group",
        "default_gen",
        "cls_by_field",
        "field_name_by_number",
        "meta_by_field_name",
        "sorted_field_names",
        "subject",
    )

    oneof_group_by_field: Dict[str, str]
    oneof_field_by_group: Dict[str, Set[dataclasses.Field]]
    field_name_by_number: Dict[int, str]
    meta_by_field_name: Dict[str, FieldMetadata]
    sorted_field_names: Tuple[str, ...]
    default_gen: Dict[str, Callable[[], Any]]
    cls_by_field: Dict[str, Type]
    subject: Type["Message"]

    def __init__(self, cls: Type["Message"]):
        by_field = {}
        by_group: Dict[str, Set] = {}
        by_field_name = {}
        by_field_number = {}

        fields = dataclasses.fields(cls)
        for field in fields:
            meta = FieldMetadata.get(field)

            if meta.group:
                # This is part of a one-of group.
                by_field[field.name] = meta.group
                by_group.setdefault(meta.group, set()).add(field)

            by_field_name[field.name] = meta
            by_field_number[meta.number] = field.name

        self.subject = cls
        self.oneof_group_by_field = by_field
        self.oneof_field_by_group = by_group
        self.field_name_by_number = by_field_number
        self.meta_by_field_name = by_field_name
        self.sorted_field_names = tuple(by_field_number[number] for number in sorted(by_field_number))
        self.default_gen = {field.name: _get_field_default_gen(cls, field) for field in fields}
        self.cls_by_field = _get_cls_by_field(cls, fields)

    def get_field_number(self, field_name: str) -> int:
        if field_name not in self.meta_by_field_name:
            raise ValueError(f"Unknown field {field_name}")
        return self.meta_by_field_name[field_name].number

    def get_field_default(self, field_name: str) -> Any:
        with warnings.catch_warnings():
            # ignore warnings when initialising deprecated field defaults
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            return self.default_gen[field_name]()


def _get_cls_by_field(cls: Type[Message], fields: Iterable[dataclasses.Field]) -> Dict[str, Type]:
    field_cls = {}

    for field in fields:
        meta = FieldMetadata.get(field)
        if meta.proto_type == TYPE_MAP:
            assert meta.map_types
            kt = _cls_for(cls, field, index=0)
            vt = _cls_for(cls, field, index=1)
            field_cls[field.name] = dataclasses.make_dataclass(
                "Entry",
                [
                    ("key", kt, proto_field(1, meta.map_types[0])),
                    ("value", vt, proto_field(2, meta.map_types[1])),
                ],
                bases=(Message,),
            )
            field_cls[f"{field.name}.value"] = vt
        else:
            field_cls[field.name] = _cls_for(cls, field)

    return field_cls


def _get_field_default_gen(cls, field: dataclasses.Field) -> Any:
    t = _type_hint(cls, field.name)

    if hasattr(t, "__origin__"):
        if t.__origin__ in (dict, Dict):
            # This is some kind of map (dict in Python).
            return dict
        elif t.__origin__ in (list, List):
            # This is some kind of list (repeated) field.
            return list
        elif _is_optional(t):
            # This is an optional field (either wrapped, or using proto3
            # field presence). For setting the default we really don't care
            # what kind of field it is.
            return type(None)
        else:
            return t
    elif issubclass(t, Enum):
        # Enums always default to zero.
        return int
    elif t is datetime:
        # Offsets are relative to 1970-01-01T00:00:00Z
        return datetime_default_gen
    else:
        # This is either a primitive scalar or another message type. Calling
        # it should result in its zero value.
        return t


def _type_hint(cls, field_name: str) -> Type:
    return _type_hints(cls)[field_name]


def _type_hints(cls) -> Dict[str, Type]:
    module = sys.modules[cls.__module__]
    return get_type_hints(cls, {**globals(), **module.__dict__}, {})


def _cls_for(cls, field: dataclasses.Field, index: int = 0) -> Type:
    """Get the message class for a field from the type hints."""
    field_cls = _type_hint(cls, field.name)
    if hasattr(field_cls, "__args__") and index >= 0:
        if field_cls.__args__ is not None:
            field_cls = field_cls.__args__[index]
    return field_cls


def _is_optional(typ: Type) -> bool:
    if get_origin(typ) is Union:
        args = get_args(typ)
        return len(args) == 2 and type(None) in args
    return False


def serialize_to_pydict(message: Message, casing: Casing = "camel", include_defaults: bool = False) -> Dict[str, Any]:
    casing_func = get_casing_fn(casing)

    output: Dict[str, Any] = {}
    defaults = message.cbproto_meta.default_gen
    for field_name, meta in message.cbproto_meta.meta_by_field_name.items():
        field_is_repeated = defaults[field_name] is list
        value = getattr(message, field_name)
        cased_name = casing_func(field_name).rstrip("_")  # type: ignore
        if meta.proto_type == TYPE_MESSAGE:
            if isinstance(value, datetime):
                if (
                    value != DATETIME_ZERO
                    or include_defaults
                    or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
                ):
                    output[cased_name] = value
            elif isinstance(value, timedelta):
                if (
                    value != timedelta(0)
                    or include_defaults
                    or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
                ):
                    output[cased_name] = value
            elif meta.wraps:
                if value is not None or include_defaults:
                    output[cased_name] = value
            elif field_is_repeated:
                # Convert each item.
                value = [i.to_pydict(casing, include_defaults) for i in value]
                if value or include_defaults:
                    output[cased_name] = value
            elif (
                value._serialized_on_wire
                or include_defaults
                or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
            ):
                output[cased_name] = value.to_pydict(casing, include_defaults)
        elif meta.proto_type == TYPE_MAP:
            for k in value:
                if hasattr(value[k], "to_pydict"):
                    value[k] = value[k].to_pydict(casing, include_defaults)

            if value or include_defaults:
                output[cased_name] = value
        elif (
            value != message.cbproto_meta.get_field_default(field_name)
            or include_defaults
            or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
        ):
            output[cased_name] = value
    return output


@overload
def deserialize_from_pydict(message_cls: Type[MessageT], /, value: Dict[str, Any]) -> MessageT:
    ...


@overload
def deserialize_from_pydict(message: MessageT, /, value: Dict[str, Any]) -> MessageT:
    ...


def deserialize_from_pydict(class_or_instance: Union[MessageT, Type[MessageT]], /, value: Dict[str, Any]) -> MessageT:
    if isinstance(class_or_instance, type):
        message = class_or_instance()
        message_cls = class_or_instance
    else:
        message = class_or_instance
        message_cls = type(message)

    message._serialized_on_wire = True
    for key in value:
        field_name = safe_snake_case(key)
        meta = message.cbproto_meta.meta_by_field_name.get(field_name)
        if not meta:
            continue

        if value[key] is not None:
            if meta.proto_type == TYPE_MESSAGE:
                v = getattr(message, field_name)
                if isinstance(v, list):
                    cls = message_cls.cbproto_meta.cls_by_field[field_name]
                    cls = cast(Type[MessageT], cls)
                    for item in value[key]:
                        v.append(deserialize_from_pydict(cls, item))
                elif isinstance(v, datetime):
                    v = value[key]
                elif isinstance(v, timedelta):
                    v = value[key]
                elif meta.wraps:
                    v = value[key]
                else:
                    v = cast(MessageT, v)
                    # NOTE: `from_pydict` mutates the underlying message, so no
                    # assignment here is necessary.
                    v = deserialize_from_pydict(v, value[key])
            elif meta.map_types and meta.map_types[1] == TYPE_MESSAGE:
                v = getattr(message, field_name)
                cls = message_cls.cbproto_meta.cls_by_field[f"{field_name}.value"]
                cls = cast(Type[MessageT], cls)

                for k in value[key]:
                    v[k] = deserialize_from_pydict(cls, value[key][k])
            else:
                v = value[key]

            if v is not None:
                setattr(message, field_name, v)
    return message


def serialize_to_dict(
    message: Message, casing: Casing = "camel", include_defaults: bool = False
) -> Dict[str, Any]:  # noqa: C901
    casing_func = get_casing_fn(casing)

    output: Dict[str, Any] = {}
    field_types = _type_hints(type(message))
    defaults = message.cbproto_meta.default_gen
    for field_name, meta in message.cbproto_meta.meta_by_field_name.items():
        field_is_repeated = defaults[field_name] is list
        value = getattr(message, field_name)
        cased_name = casing_func(field_name).rstrip("_")  # type: ignore
        if meta.proto_type == TYPE_MESSAGE:
            if isinstance(value, datetime):
                if (
                    value != DATETIME_ZERO
                    or include_defaults
                    or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
                ):
                    output[cased_name] = _Timestamp.timestamp_to_json(value)
            elif isinstance(value, timedelta):
                if (
                    value != timedelta(0)
                    or include_defaults
                    or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
                ):
                    output[cased_name] = _Duration.delta_to_json(value)
            elif meta.wraps:
                if value is not None or include_defaults:
                    output[cased_name] = value
            elif field_is_repeated:
                # Convert each item.
                cls = message.cbproto_meta.cls_by_field[field_name]
                if cls == datetime:
                    value = [_Timestamp.timestamp_to_json(i) for i in value]
                elif cls == timedelta:
                    value = [_Duration.delta_to_json(i) for i in value]
                else:
                    value = [serialize_to_dict(i, casing, include_defaults) for i in value]
                if value or include_defaults:
                    output[cased_name] = value
            elif value is None:
                if include_defaults:
                    output[cased_name] = value
            elif (
                value._serialized_on_wire
                or include_defaults
                or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
            ):
                output[cased_name] = serialize_to_dict(value, casing, include_defaults)
        elif meta.proto_type == TYPE_MAP:
            value = cast(Dict[str, Any], value)
            output_map = {**value}
            for k, v in value.items():
                if isinstance(v, Message):
                    output_map[k] = serialize_to_dict(v, casing, include_defaults)

            if value or include_defaults:
                output[cased_name] = output_map
        elif (
            value != message.cbproto_meta.get_field_default(field_name)
            or include_defaults
            or message._include_default_value_for_oneof(field_name=field_name, meta=meta)
        ):
            if meta.proto_type in INT_64_TYPES:
                if field_is_repeated:
                    output[cased_name] = [str(n) for n in value]
                elif value is None:
                    if include_defaults:
                        output[cased_name] = value
                else:
                    output[cased_name] = str(value)
            elif meta.proto_type == TYPE_BYTES:
                if field_is_repeated:
                    output[cased_name] = [b64encode(b).decode("utf8") for b in value]
                elif value is None and include_defaults:
                    output[cased_name] = value
                else:
                    output[cased_name] = b64encode(value).decode("utf8")
            elif meta.proto_type == TYPE_ENUM:
                if field_is_repeated:
                    enum_class = field_types[field_name].__args__[0]
                    if isinstance(value, Iterable) and not isinstance(value, str):
                        output[cased_name] = [enum_class(el).name for el in value]
                    else:
                        # transparently upgrade single value to repeated
                        output[cased_name] = [enum_class(value).name]
                elif value is None:
                    if include_defaults:
                        output[cased_name] = value
                elif meta.optional:
                    enum_class = field_types[field_name].__args__[0]
                    output[cased_name] = enum_class(value).name
                else:
                    enum_class = field_types[field_name]  # noqa
                    output[cased_name] = enum_class(value).name
            elif meta.proto_type in (TYPE_FLOAT, TYPE_DOUBLE):
                if field_is_repeated:
                    output[cased_name] = [_dump_float(n) for n in value]
                else:
                    output[cased_name] = _dump_float(value)
            else:
                output[cased_name] = value
    return output


@overload
def deserialize_from_dict(message_cls: Type[MessageT], /, value: Dict[str, Any]) -> MessageT:
    ...


@overload
def deserialize_from_dict(message: MessageT, /, value: Dict[str, Any]) -> MessageT:
    ...


def deserialize_from_dict(class_or_instance: Union[MessageT, Type[MessageT]], /, value: Dict[str, Any]) -> MessageT:
    if isinstance(class_or_instance, type):
        message = class_or_instance()
        message_cls = class_or_instance
    else:
        message = class_or_instance
        message_cls = type(message)

    message._serialized_on_wire = True
    for key in value:
        field_name = safe_snake_case(key)
        meta = message.cbproto_meta.meta_by_field_name.get(field_name)
        if not meta:
            continue

        if value[key] is not None:
            if meta.proto_type == TYPE_MESSAGE:
                v = getattr(message, field_name)
                cls = message_cls.cbproto_meta.cls_by_field[field_name]
                cls = cast(Type[Message], cls)

                if isinstance(v, list):
                    if cls == datetime:
                        v = [isoparse(item) for item in value[key]]
                    elif cls == timedelta:
                        v = [timedelta(seconds=float(item[:-1])) for item in value[key]]
                    else:
                        v = [deserialize_from_dict(cls, item) for item in value[key]]
                elif cls == datetime:
                    v = isoparse(value[key])
                    setattr(message, field_name, v)
                elif cls == timedelta:
                    v = timedelta(seconds=float(value[key][:-1]))
                    setattr(message, field_name, v)
                elif meta.wraps:
                    setattr(message, field_name, value[key])
                elif v is None:
                    setattr(message, field_name, deserialize_from_dict(cls, value[key]))
                else:
                    v = deserialize_from_dict(v, value[key])
            elif meta.map_types and meta.map_types[1] == TYPE_MESSAGE:
                v = getattr(message, field_name)
                cls = message_cls.cbproto_meta.cls_by_field[f"{field_name}.value"]
                cls = cast(Type[Message], cls)
                for k in value[key]:
                    v[k] = deserialize_from_dict(cls, value[key][k])
            else:
                v = value[key]
                if meta.proto_type in INT_64_TYPES:
                    if isinstance(value[key], list):
                        v = [int(n) for n in value[key]]
                    else:
                        v = int(value[key])
                elif meta.proto_type == TYPE_BYTES:
                    if isinstance(value[key], list):
                        v = [b64decode(n) for n in value[key]]
                    else:
                        v = b64decode(value[key])
                elif meta.proto_type == TYPE_ENUM:
                    enum_cls = message_cls.cbproto_meta.cls_by_field[field_name]
                    enum_cls = cast(Type[Enum], enum_cls)
                    if isinstance(v, list):
                        v = [enum_cls.from_string(e) for e in v]
                    elif isinstance(v, str):
                        v = enum_cls.from_string(v)
                elif meta.proto_type in (TYPE_FLOAT, TYPE_DOUBLE):
                    if isinstance(value[key], list):
                        v = [_parse_float(n) for n in value[key]]
                    else:
                        v = _parse_float(value[key])

            if v is not None:
                setattr(message, field_name, v)
    return message


def serialize_to_bytes(message: Message) -> bytes:
    """
    Get the binary encoded Protobuf representation of this message instance.
    """
    output = bytearray()
    for field_name, meta in message.cbproto_meta.meta_by_field_name.items():
        value = getattr(message, field_name)

        if value is None:
            # Optional items should be skipped. This is used for the Google
            # wrapper types and proto3 field presence/optional fields.
            continue

        # Being selected in a a group means this field is the one that is
        # currently set in a `oneof` group, so it must be serialized even
        # if the value is the default zero value.
        #
        # Note that proto3 field presence/optional fields are put in a
        # synthetic single-item oneof by protoc, which helps us ensure we
        # send the value even if the value is the default zero value.
        selected_in_group = meta.group and message._group_current[meta.group] == field_name

        # Empty messages can still be sent on the wire if they were
        # set (or received empty).
        serialize_empty = isinstance(value, Message) and value._serialized_on_wire

        include_default_value_for_oneof = message._include_default_value_for_oneof(field_name=field_name, meta=meta)

        if value == message.cbproto_meta.get_field_default(field_name) and not (
            selected_in_group or serialize_empty or include_default_value_for_oneof
        ):
            # Default (zero) values are not serialized. Two exceptions are
            # if this is the selected oneof item or if we know we have to
            # serialize an empty message (i.e. zero value was explicitly
            # set by the user).
            continue

        if isinstance(value, list):
            if meta.proto_type in PACKED_TYPES:
                # Packed lists look like a length-delimited field. First,
                # preprocess/encode each value into a buffer and then
                # treat it like a field of raw bytes.
                buf = bytearray()
                for item in value:
                    buf += _preprocess_single(meta.proto_type, "", item)
                output += _serialize_single(meta.number, TYPE_BYTES, buf)
            else:
                for item in value:
                    output += (
                        _serialize_single(
                            meta.number,
                            meta.proto_type,
                            item,
                            wraps=meta.wraps or "",
                        )
                        # if it's an empty message it still needs to be represented
                        # as an item in the repeated list
                        or b"\n\x00"
                    )

        elif isinstance(value, dict):
            for k, v in value.items():
                assert meta.map_types
                sk = _serialize_single(1, meta.map_types[0], k)
                sv = _serialize_single(2, meta.map_types[1], v)
                output += _serialize_single(meta.number, meta.proto_type, sk + sv)
        else:
            # If we have an empty string and we're including the default value for
            # a oneof, make sure we serialize it. This ensures that the byte string
            # output isn't simply an empty string. This also ensures that round trip
            # serialization will keep `which_one_of` calls consistent.
            if isinstance(value, str) and value == "" and include_default_value_for_oneof:
                serialize_empty = True

            output += _serialize_single(
                meta.number,
                meta.proto_type,
                value,
                serialize_empty=serialize_empty or bool(selected_in_group),
                wraps=meta.wraps or "",
            )

    output += message._unknown_fields
    return bytes(output)


@overload
def deserialize_from_bytes(message_cls: Type[MessageT], /, data: bytes) -> MessageT:
    ...


@overload
def deserialize_from_bytes(message: MessageT, /, data: bytes) -> MessageT:
    ...


def deserialize_from_bytes(cls: Union[MessageT, Type[MessageT]], /, data: bytes) -> MessageT:
    if isinstance(cls, type):
        message = cls()
        message_cls = cls
    else:
        message = cls
        message_cls = type(message)

    message._serialized_on_wire = True
    proto_meta = message_cls.cbproto_meta
    for parsed in parse_fields(data):
        field_name = proto_meta.field_name_by_number.get(parsed.number)
        if not field_name:
            message._unknown_fields += parsed.raw
            continue

        meta = proto_meta.meta_by_field_name[field_name]

        value: Any
        if parsed.wire_type == WIRE_LEN_DELIM and meta.proto_type in PACKED_TYPES:
            # This is a packed repeated field.
            pos = 0
            value = []
            while pos < len(parsed.value):
                if meta.proto_type in (TYPE_FLOAT, TYPE_FIXED32, TYPE_SFIXED32):
                    decoded, pos = parsed.value[pos : pos + 4], pos + 4
                    wire_type = WIRE_FIXED_32
                elif meta.proto_type in (TYPE_DOUBLE, TYPE_FIXED64, TYPE_SFIXED64):
                    decoded, pos = parsed.value[pos : pos + 8], pos + 8
                    wire_type = WIRE_FIXED_64
                else:
                    decoded, pos = decode_varint(parsed.value, pos)
                    wire_type = WIRE_VARINT
                decoded = _postprocess_single(proto_meta, wire_type, meta, field_name, decoded)
                value.append(decoded)
        else:
            value = _postprocess_single(proto_meta, parsed.wire_type, meta, field_name, parsed.value)

        current = getattr(message, field_name)
        if meta.proto_type == TYPE_MAP:
            # Value represents a single key/value pair entry in the map.
            current[value.key] = value.value
        elif isinstance(current, list) and not isinstance(value, list):
            current.append(value)
        else:
            setattr(message, field_name, value)

    return message


def get_casing_fn(casing: str) -> Callable[[str], str]:
    if casing == "camel":
        return camel_case
    elif casing == "snake":
        return snake_case
    elif casing == "pascal":
        return pascal_case
    else:
        raise ValueError(f"Invalid casing: {casing}")


def serialized_on_wire(message: Message) -> bool:
    return message._serialized_on_wire


def which_one_of(message: Message, group_name: str) -> Tuple[str, Optional[Any]]:
    field_name = message._group_current.get(group_name)
    if not field_name:
        return "", None
    return field_name, getattr(message, field_name)


def _postprocess_single(
    proto_meta: ProtoClassMetadata, wire_type: int, meta: FieldMetadata, field_name: str, value: Any
) -> Any:
    if wire_type == WIRE_VARINT:
        if meta.proto_type in (TYPE_INT32, TYPE_INT64):
            bits = int(meta.proto_type[3:])
            value = value & ((1 << bits) - 1)
            signbit = 1 << (bits - 1)
            value = int((value ^ signbit) - signbit)
        elif meta.proto_type in (TYPE_SINT32, TYPE_SINT64):
            # Undo zig-zag encoding
            value = (value >> 1) ^ (-(value & 1))
        elif meta.proto_type == TYPE_BOOL:
            # Booleans use a varint encoding, so convert it to true/false.
            value = value > 0
    elif wire_type in (WIRE_FIXED_32, WIRE_FIXED_64):
        fmt = _pack_fmt(meta.proto_type)
        value = struct.unpack(fmt, value)[0]
    elif wire_type == WIRE_LEN_DELIM:
        if meta.proto_type == TYPE_STRING:
            value = str(value, "utf-8")
        elif meta.proto_type == TYPE_MESSAGE:
            field_cls = proto_meta.cls_by_field[field_name]

            if field_cls == datetime:
                value = deserialize_from_bytes(_Timestamp, value).to_datetime()
            elif field_cls == timedelta:
                value = deserialize_from_bytes(_Duration, value).to_timedelta()
            elif meta.wraps:
                # This is a Google wrapper value message around a single
                # scalar type.
                value = deserialize_from_bytes(_get_wrapper(meta.wraps), value).value
            else:
                value = deserialize_from_bytes(field_cls, value)
                value._serialized_on_wire = True
        elif meta.proto_type == TYPE_MAP:
            value = deserialize_from_bytes(proto_meta.cls_by_field[field_name], value)

    return value


def _pack_fmt(proto_type: str) -> str:
    """Returns a little-endian format string for reading/writing binary."""
    return {
        TYPE_DOUBLE: "<d",
        TYPE_FLOAT: "<f",
        TYPE_FIXED32: "<I",
        TYPE_FIXED64: "<Q",
        TYPE_SFIXED32: "<i",
        TYPE_SFIXED64: "<q",
    }[proto_type]


def encode_varint(value: int) -> bytes:
    """Encodes a single varint value for serialization."""
    b: List[int] = []

    if value < 0:
        value += 1 << 64

    bits = value & 0x7F
    value >>= 7
    while value:
        b.append(0x80 | bits)
        bits = value & 0x7F
        value >>= 7
    return bytes(b + [bits])


def _preprocess_single(proto_type: str, wraps: str, value: Any) -> bytes:
    """Adjusts values before serialization."""
    if proto_type in (
        TYPE_ENUM,
        TYPE_BOOL,
        TYPE_INT32,
        TYPE_INT64,
        TYPE_UINT32,
        TYPE_UINT64,
    ):
        return encode_varint(value)
    elif proto_type in (TYPE_SINT32, TYPE_SINT64):
        # Handle zig-zag encoding.
        return encode_varint(value << 1 if value >= 0 else (value << 1) ^ (~0))
    elif proto_type in FIXED_TYPES:
        return struct.pack(_pack_fmt(proto_type), value)
    elif proto_type == TYPE_STRING:
        return value.encode("utf-8")
    elif proto_type == TYPE_MESSAGE:
        if isinstance(value, datetime):
            # Convert the `datetime` to a timestamp message.
            seconds = int(value.timestamp())
            nanos = int(value.microsecond * 1e3)
            value = _Timestamp(seconds=seconds, nanos=nanos)
        elif isinstance(value, timedelta):
            # Convert the `timedelta` to a duration message.
            total_ms = value // timedelta(microseconds=1)
            seconds = int(total_ms / 1e6)
            nanos = int((total_ms % 1e6) * 1e3)
            value = _Duration(seconds=seconds, nanos=nanos)
        elif wraps:
            if value is None:
                return b""
            value = _get_wrapper(wraps)(value=value)

        return bytes(value)

    return value


def _serialize_single(
    field_number: int,
    proto_type: str,
    value: Any,
    *,
    serialize_empty: bool = False,
    wraps: str = "",
) -> bytes:
    """Serializes a single field and value."""
    value = _preprocess_single(proto_type, wraps, value)

    output = bytearray()
    if proto_type in WIRE_VARINT_TYPES:
        key = encode_varint(field_number << 3)
        output += key + value
    elif proto_type in WIRE_FIXED_32_TYPES:
        key = encode_varint((field_number << 3) | 5)
        output += key + value
    elif proto_type in WIRE_FIXED_64_TYPES:
        key = encode_varint((field_number << 3) | 1)
        output += key + value
    elif proto_type in WIRE_LEN_DELIM_TYPES:
        if len(value) or serialize_empty or wraps:
            key = encode_varint((field_number << 3) | 2)
            output += key + encode_varint(len(value)) + value
    else:
        raise NotImplementedError(proto_type)

    return bytes(output)


def _parse_float(value: Any) -> float:
    """Parse the given value to a float

    Parameters
    ----------
    value: Any
        Value to parse

    Returns
    -------
    float
        Parsed value
    """
    if value == INFINITY:
        return float("inf")
    if value == NEG_INFINITY:
        return -float("inf")
    if value == NAN:
        return float("nan")
    return float(value)


def _dump_float(value: float) -> Union[float, str]:
    """Dump the given float to JSON

    Parameters
    ----------
    value: float
        Value to dump

    Returns
    -------
    Union[float, str]
        Dumped value, either a float or the strings
    """
    if value == float("inf"):
        return INFINITY
    if value == -float("inf"):
        return NEG_INFINITY
    if isinstance(value, float) and math.isnan(value):
        return NAN
    return value


def decode_varint(buffer: bytes, pos: int) -> Tuple[int, int]:
    """
    Decode a single varint value from a byte buffer. Returns the value and the
    new position in the buffer.
    """
    result = 0
    shift = 0
    while True:
        b = buffer[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift >= 64:
            raise ValueError("Too many bytes when decoding varint.")


@dataclasses.dataclass(frozen=True)
class ParsedField:
    number: int
    wire_type: int
    value: Any
    raw: bytes


def parse_fields(value: bytes) -> Generator[ParsedField, None, None]:
    i = 0
    while i < len(value):
        start = i
        num_wire, i = decode_varint(value, i)
        number = num_wire >> 3
        wire_type = num_wire & 0x7

        decoded: Any = None
        if wire_type == WIRE_VARINT:
            decoded, i = decode_varint(value, i)
        elif wire_type == WIRE_FIXED_64:
            decoded, i = value[i : i + 8], i + 8
        elif wire_type == WIRE_LEN_DELIM:
            length, i = decode_varint(value, i)
            decoded = value[i : i + length]
            i += length
        elif wire_type == WIRE_FIXED_32:
            decoded, i = value[i : i + 4], i + 4

        yield ParsedField(number=number, wire_type=wire_type, value=decoded, raw=value[start:i])


# Circular import workaround: google.protobuf depends on base classes defined above.
from .lib.google.protobuf import (  # noqa
    BoolValue,
    BytesValue,
    DoubleValue,
    Duration,
    EnumValue,
    FloatValue,
    Int32Value,
    Int64Value,
    StringValue,
    Timestamp,
    UInt32Value,
    UInt64Value,
)


class _Duration(Duration):
    def to_timedelta(self) -> timedelta:
        return timedelta(seconds=self.seconds, microseconds=self.nanos / 1e3)

    @staticmethod
    def delta_to_json(delta: timedelta) -> str:
        parts = str(delta.total_seconds()).split(".")
        if len(parts) > 1:
            while len(parts[1]) not in (3, 6, 9):
                parts[1] = f"{parts[1]}0"
        return f"{'.'.join(parts)}s"


class _Timestamp(Timestamp):
    def to_datetime(self) -> datetime:
        ts = self.seconds + (self.nanos / 1e9)
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    @staticmethod
    def timestamp_to_json(dt: datetime) -> str:
        nanos = dt.microsecond * 1e3
        copy = dt.replace(microsecond=0, tzinfo=None)
        result = copy.isoformat()
        if (nanos % 1e9) == 0:
            # If there are 0 fractional digits, the fractional
            # point '.' should be omitted when serializing.
            return f"{result}Z"
        if (nanos % 1e6) == 0:
            # Serialize 3 fractional digits.
            return f"{result}.{int(nanos // 1e6) :03d}Z"
        if (nanos % 1e3) == 0:
            # Serialize 6 fractional digits.
            return f"{result}.{int(nanos // 1e3) :06d}Z"
        # Serialize 9 fractional digits.
        return f"{result}.{nanos:09d}"


def _get_wrapper(proto_type: str) -> Type:
    """Get the wrapper message class for a wrapped type."""

    # TODO: include ListValue and NullValue?
    return {
        TYPE_BOOL: BoolValue,
        TYPE_BYTES: BytesValue,
        TYPE_DOUBLE: DoubleValue,
        TYPE_FLOAT: FloatValue,
        TYPE_ENUM: EnumValue,
        TYPE_INT32: Int32Value,
        TYPE_INT64: Int64Value,
        TYPE_STRING: StringValue,
        TYPE_UINT32: UInt32Value,
        TYPE_UINT64: UInt64Value,
    }[proto_type]


__all__ = [
    "Message",
    "Enum",
    "FieldMetadata",
    "proto_field",
    "enum_field",
    "bool_field",
    "int32_field",
    "int64_field",
    "uint32_field",
    "uint64_field",
    "sint32_field",
    "sint64_field",
    "float_field",
    "double_field",
    "fixed32_field",
    "fixed64_field",
    "sfixed32_field",
    "sfixed64_field",
    "string_field",
    "bytes_field",
    "message_field",
    "map_field",
    "ServiceStub",
    "aio",
    "ServiceBase",
    "Server",
    "TLSConfig",
    "Handler",
    "Cardinality",
    "IServable",
    "graceful_exit",
]
