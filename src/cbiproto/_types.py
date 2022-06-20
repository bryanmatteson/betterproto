# nopycln: file

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from grpclib._typing import IProtoMessage

    from . import Message

MessageT = TypeVar("MessageT", bound="Message")
ProtoMessageT = TypeVar("ProtoMessageT", bound="IProtoMessage")
