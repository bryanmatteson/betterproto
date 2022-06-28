from abc import ABC
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Type

import grpc
from grpc import Channel

from .._casing import snake_case
from .types import IProtoMessage, MessageT, MetadataLike, RequestT, ResponseT


class AsyncServiceStub(ABC):
    ...


class ServiceStub(ABC):
    _channel: Channel
    _timeout: Optional[float]
    _metadata: Optional[MetadataLike]
    _name: str

    def __init__(
        self,
        channel: Channel,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        name: Optional[str] = None,
    ) -> None:
        self._channel = channel
        self._timeout = timeout
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

    def __resolve_request_kwargs(self, timeout: Optional[float], metadata: Optional[MetadataLike]) -> Dict[str, Any]:
        timeout = self._timeout if timeout is None else timeout
        metadata = self._metadata if metadata is None else metadata
        if isinstance(metadata, Mapping):
            metadata = tuple(metadata.items())
        else:
            metadata = tuple(metadata or ())

        return {"timeout": timeout, "metadata": metadata}

    def _unary_unary(
        self,
        route: str,
        request: IProtoMessage,
        response_type: Type[MessageT],
        *,
        timeout: Optional[int] = None,
        metadata: Optional[MetadataLike] = None,
        wait_for_ready: Optional[bool] = None,
        call_credentials: Optional[grpc.CallCredentials] = None,
    ) -> MessageT:
        multicallable = self.channel.unary_unary(route, bytes, response_type.parse_raw)
        wait_for_ready = wait_for_ready if wait_for_ready is not None else True
        return multicallable(
            request,
            wait_for_ready=wait_for_ready,
            credentials=call_credentials,
            **self.__resolve_request_kwargs(timeout, metadata),
        )

    def _unary_stream(
        self,
        route: str,
        request: IProtoMessage,
        response_type: Type[MessageT],
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
        wait_for_ready: Optional[bool] = None,
        call_credentials: Optional[grpc.CallCredentials] = None,
    ) -> Iterable[MessageT]:
        multicallable = self.channel.unary_stream(route, bytes, response_type.parse_raw)
        wait_for_ready = wait_for_ready if wait_for_ready is not None else True
        return multicallable(
            request,
            wait_for_ready=wait_for_ready,
            credentials=call_credentials,
            **self.__resolve_request_kwargs(timeout, metadata),
        )

    def _stream_unary(
        self,
        route: str,
        request: Iterable[RequestT],
        response_type: Type[ResponseT],
        *,
        timeout: Optional[float] = None,
        wait_for_ready: Optional[bool] = None,
        metadata: Optional[MetadataLike] = None,
        call_credentials: Optional[grpc.CallCredentials] = None,
    ) -> ResponseT:
        multicallable = self.channel.stream_unary(route, bytes, response_type.parse_raw)
        wait_for_ready = wait_for_ready if wait_for_ready is not None else True
        return multicallable(
            iter(request),
            wait_for_ready=wait_for_ready,
            credentials=call_credentials,
            **self.__resolve_request_kwargs(timeout, metadata),
        )

    def _stream_stream(
        self,
        route: str,
        request: Iterator[RequestT],
        response_type: Type[ResponseT],
        *,
        timeout: Optional[float] = None,
        wait_for_ready: Optional[bool] = None,
        metadata: Optional[MetadataLike] = None,
        call_credentials: Optional[grpc.CallCredentials] = None,
    ) -> Iterable[ResponseT]:
        multicallable = self.channel.stream_stream(route, bytes, response_type.parse_raw)
        wait_for_ready = wait_for_ready if wait_for_ready is not None else True
        return multicallable(
            iter(request),
            wait_for_ready=wait_for_ready,
            credentials=call_credentials,
            **self.__resolve_request_kwargs(timeout, metadata),
        )
