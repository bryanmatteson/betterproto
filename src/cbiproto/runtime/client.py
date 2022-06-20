import asyncio
from abc import ABC
from typing import (
    TYPE_CHECKING,
    AsyncIterable,
    AsyncIterator,
    Collection,
    Iterable,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import grpclib.const
from grpclib.client import Channel

from .._utils import snake_case
from .middleware import Middleware, add_channel_middleware

if TYPE_CHECKING:
    from grpclib.client import Stream
    from grpclib.metadata import Deadline

from .._types import MessageT, ProtoMessageT

Value = Union[str, bytes]
MetadataLike = Union[Mapping[str, Value], Collection[Tuple[str, Value]]]
MessageLike = Union[MessageT, ProtoMessageT]
MessageSource = Union[Iterable[ProtoMessageT], AsyncIterable[ProtoMessageT]]
ServiceStubT = TypeVar("ServiceStubT", bound="ServiceStub")


class ServiceStub(ABC):
    """
    Base class for async gRPC clients.
    """

    _channel: Channel
    _timeout: Optional[float]
    _deadline: Optional["Deadline"]
    _metadata: Optional[MetadataLike]
    _name: str

    @classmethod
    def create(
        cls: Type[ServiceStubT],
        host: str,
        port: int,
        *,
        ssl: bool = False,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        deadline: Optional["Deadline"] = None,
        name: Optional[str] = None,
        middleware: Optional[Iterable["Middleware"]] = None,
    ) -> ServiceStubT:
        channel = Channel(host=host, port=port, ssl=ssl)
        if middleware:
            add_channel_middleware(channel, *middleware)
        return cls(channel, timeout=timeout, deadline=deadline, metadata=metadata, name=name)

    def __init__(
        self,
        channel: Channel,
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
        name: Optional[str] = None,
    ) -> None:
        self._channel = channel
        self._timeout = timeout
        self._deadline = deadline
        self._metadata = metadata

        if name is None:
            name = self.__class__.__name__
            if name.endswith("Stub"):
                name = name[:-4]
            name = snake_case(name)

        self._name = name

    @property
    def channel(self) -> Channel:
        return self._channel

    @property
    def name(self) -> str:
        return self._name

    def __resolve_request_kwargs(
        self, timeout: Optional[float], deadline: Optional["Deadline"], metadata: Optional[MetadataLike],
    ):
        return {
            "timeout": self._timeout if timeout is None else timeout,
            "deadline": self._deadline if deadline is None else deadline,
            "metadata": self._metadata if metadata is None else metadata,
        }

    async def _unary_unary(
        self,
        route: str,
        request: MessageLike,
        response_type: Type[MessageT],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> MessageT:
        """Make a unary request and return the response."""
        async with self._channel.request(
            route,
            grpclib.const.Cardinality.UNARY_UNARY,
            type(request),
            response_type,
            **self.__resolve_request_kwargs(timeout, deadline, metadata),
        ) as stream:
            await stream.send_message(request, end=True)
            response = await stream.recv_message()
        assert response is not None
        return response

    async def _unary_stream(
        self,
        route: str,
        request: MessageLike,
        response_type: Type[MessageT],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> AsyncIterator[MessageT]:
        """Make a unary request and return the stream response iterator."""
        async with self._channel.request(
            route,
            grpclib.const.Cardinality.UNARY_STREAM,
            type(request),
            response_type,
            **self.__resolve_request_kwargs(timeout, deadline, metadata),
        ) as stream:
            await stream.send_message(request, end=True)
            async for message in stream:
                yield message

    async def _stream_unary(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type[ProtoMessageT],
        response_type: Type[MessageT],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> MessageT:
        """Make a stream request and return the response."""
        async with self._channel.request(
            route,
            grpclib.const.Cardinality.STREAM_UNARY,
            request_type,
            response_type,
            **self.__resolve_request_kwargs(timeout, deadline, metadata),
        ) as stream:
            await self._send_messages(stream, request_iterator)
            response = await stream.recv_message()
        assert response is not None
        return response

    async def _stream_stream(
        self,
        route: str,
        request_iterator: MessageSource,
        request_type: Type[ProtoMessageT],
        response_type: Type[MessageT],
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> AsyncIterator[MessageT]:
        """
        Make a stream request and return an AsyncIterator to iterate over response
        messages.
        """
        async with self._channel.request(
            route,
            grpclib.const.Cardinality.STREAM_STREAM,
            request_type,
            response_type,
            **self.__resolve_request_kwargs(timeout, deadline, metadata),
        ) as stream:
            await stream.send_request()
            sending_task = asyncio.ensure_future(self._send_messages(stream, request_iterator))
            try:
                async for response in stream:
                    yield response
            except BaseException:
                sending_task.cancel()
                raise

    @staticmethod
    async def _send_messages(stream: "Stream", messages: MessageSource):
        if isinstance(messages, AsyncIterable):
            async for message in messages:
                await stream.send_message(message)
        else:
            for message in messages:
                await stream.send_message(message)
        await stream.end()
