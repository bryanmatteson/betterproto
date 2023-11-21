import dataclasses
from typing import Any, Optional, Tuple

from ._types import UNSET
from .const import (
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
)


@dataclasses.dataclass(frozen=True)
class FieldMetadata:
    number: int
    proto_type: str
    map_types: Optional[Tuple[str, str]] = None
    group: Optional[str] = None
    wraps: Optional[str] = None
    optional: Optional[bool] = False

    @staticmethod
    def get(field: dataclasses.Field) -> "FieldMetadata":
        return field.metadata["betterproto"]


def proto_field(
    number: int,
    proto_type: str,
    *,
    map_types: Optional[Tuple[str, str]] = None,
    group: Optional[str] = None,
    wraps: Optional[str] = None,
    optional: bool = False,
) -> dataclasses.Field:
    default: Any = None if optional else UNSET
    return dataclasses.field(
        default=default,
        metadata={"betterproto": FieldMetadata(number, proto_type, map_types, group, wraps, optional)},
    )


def enum_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_ENUM, group=group, optional=optional)


def bool_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_BOOL, group=group, optional=optional)


def int32_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_INT32, group=group, optional=optional)


def int64_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_INT64, group=group, optional=optional)


def uint32_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_UINT32, group=group, optional=optional)


def uint64_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_UINT64, group=group, optional=optional)


def sint32_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_SINT32, group=group, optional=optional)


def sint64_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_SINT64, group=group, optional=optional)


def float_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_FLOAT, group=group, optional=optional)


def double_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_DOUBLE, group=group, optional=optional)


def fixed32_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_FIXED32, group=group, optional=optional)


def fixed64_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_FIXED64, group=group, optional=optional)


def sfixed32_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_SFIXED32, group=group, optional=optional)


def sfixed64_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_SFIXED64, group=group, optional=optional)


def string_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_STRING, group=group, optional=optional)


def bytes_field(number: int, group: Optional[str] = None, optional: bool = False) -> Any:
    return proto_field(number, TYPE_BYTES, group=group, optional=optional)


def message_field(
    number: int,
    group: Optional[str] = None,
    wraps: Optional[str] = None,
    optional: bool = False,
) -> Any:
    return proto_field(number, TYPE_MESSAGE, group=group, wraps=wraps, optional=optional)


def map_field(number: int, key_type: str, value_type: str, group: Optional[str] = None) -> Any:
    return proto_field(number, TYPE_MAP, map_types=(key_type, value_type), group=group)
