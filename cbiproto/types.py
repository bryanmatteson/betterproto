from __future__ import annotations

import enum
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    Callable,
    Iterable,
    Mapping,
    NamedTuple,
    Protocol,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from cbiproto import Message


TRequest = TypeVar("TRequest", bound="Message")
TResponse = TypeVar("TResponse", bound="Message")
TMessage = TypeVar("TMessage", bound="Message")
TCardinality = TypeVar("TCardinality", bound="Cardinality")
Value = Union[str, bytes]
MetadataLike = Union[Mapping[str, Value], Sequence[Tuple[str, Value]]]
MessageSource = Union[Iterable[TRequest], AsyncIterable[TResponse]]

P = ParamSpec("P")
Ret = ParamSpec("Ret")
T = TypeVar("T")


class _Cardinality(NamedTuple):
    client_streaming: bool
    server_streaming: bool


@enum.unique
class Cardinality(_Cardinality, enum.Enum):
    UNARY_UNARY = _Cardinality(False, False)
    UNARY_STREAM = _Cardinality(False, True)
    STREAM_UNARY = _Cardinality(True, False)
    STREAM_STREAM = _Cardinality(True, True)

    @classmethod
    def of(cls, client_streaming: bool, server_streaming: bool) -> "Cardinality":
        if client_streaming and server_streaming:
            return cls.STREAM_STREAM
        elif client_streaming:
            return cls.STREAM_UNARY
        elif server_streaming:
            return cls.UNARY_STREAM
        else:
            return cls.UNARY_UNARY

    def __str__(self) -> str:
        return self.name.lower()


class Handler(NamedTuple):
    func: Callable[..., Any]
    cardinality: Cardinality
    request_type: Type["Message"]
    reply_type: Type["Message"]


class IServable(Protocol):
    def __mapping__(self) -> Mapping[str, Handler]:
        ...


class IClosable(Protocol):
    def close(self) -> None:
        ...


class IAClosable(Protocol):
    async def aclose(self) -> None:
        ...


class IAsyncClosable(Protocol):
    async def close(self) -> None:
        ...


class IProtoMessage(Protocol):
    @classmethod
    def FromString(cls: Type[TMessage], s: bytes) -> TMessage:
        ...

    def SerializeToString(self) -> bytes:
        ...
