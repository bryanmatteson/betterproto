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

if TYPE_CHECKING:
    from cbiproto import Message


RequestT = TypeVar("RequestT", bound="Message")
ResponseT = TypeVar("ResponseT", bound="Message")
MessageT = TypeVar("MessageT", bound="Message")
Value = Union[str, bytes]
MetadataLike = Union[Mapping[str, Value], Sequence[Tuple[str, Value]]]
MessageSource = Union[Iterable[RequestT], AsyncIterable[ResponseT]]


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


@enum.unique
class Status(enum.Enum):
    """
    Predefined gRPC status codes represented as enum
    See also: https://github.com/grpc/grpc/blob/master/doc/statuscodes.md
    """

    #: The operation completed successfully
    OK = 0
    #: The operation was cancelled (typically by the caller)
    CANCELLED = 1
    #: Generic status to describe error when it can't be described using
    #: other statuses
    UNKNOWN = 2
    #: Client specified an invalid argument
    INVALID_ARGUMENT = 3
    #: Deadline expired before operation could complete
    DEADLINE_EXCEEDED = 4
    #: Some requested entity was not found
    NOT_FOUND = 5
    #: Some entity that we attempted to create already exists
    ALREADY_EXISTS = 6
    #: The caller does not have permission to execute the specified operation
    PERMISSION_DENIED = 7
    #: Some resource has been exhausted, perhaps a per-user quota, or perhaps
    #: the entire file system is out of space
    RESOURCE_EXHAUSTED = 8
    #: Operation was rejected because the system is not in a state required
    #: for the operation's execution
    FAILED_PRECONDITION = 9
    #: The operation was aborted
    ABORTED = 10
    #: Operation was attempted past the valid range
    OUT_OF_RANGE = 11
    #: Operation is not implemented or not supported/enabled in this service
    UNIMPLEMENTED = 12
    #: Internal errors
    INTERNAL = 13
    #: The service is currently unavailable
    UNAVAILABLE = 14
    #: Unrecoverable data loss or corruption
    DATA_LOSS = 15
    #: The request does not have valid authentication credentials for the
    #: operation
    UNAUTHENTICATED = 16


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
    def FromString(cls: Type[MessageT], s: bytes) -> MessageT:
        ...

    def SerializeToString(self) -> bytes:
        ...
