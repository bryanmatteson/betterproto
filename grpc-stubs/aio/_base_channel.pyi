import abc
import grpc
from . import _base_call
from ._typing import (
    DeserializingFunction as DeserializingFunction,
    MetadataType as MetadataType,
    RequestIterableType as RequestIterableType,
    SerializingFunction as SerializingFunction,
)
from typing import Any, Optional

class UnaryUnaryMultiCallable(abc.ABC, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __call__(
        self,
        request: Any,
        *,
        timeout: Optional[float] = ...,
        metadata: Optional[MetadataType] = ...,
        credentials: Optional[grpc.CallCredentials] = ...,
        wait_for_ready: Optional[bool] = ...,
        compression: Optional[grpc.Compression] = ...,
    ) -> _base_call.UnaryUnaryCall: ...

class UnaryStreamMultiCallable(abc.ABC, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __call__(
        self,
        request: Any,
        *,
        timeout: Optional[float] = ...,
        metadata: Optional[MetadataType] = ...,
        credentials: Optional[grpc.CallCredentials] = ...,
        wait_for_ready: Optional[bool] = ...,
        compression: Optional[grpc.Compression] = ...,
    ) -> _base_call.UnaryStreamCall: ...

class StreamUnaryMultiCallable(abc.ABC, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __call__(
        self,
        request_iterator: Optional[RequestIterableType] = ...,
        timeout: Optional[float] = ...,
        metadata: Optional[MetadataType] = ...,
        credentials: Optional[grpc.CallCredentials] = ...,
        wait_for_ready: Optional[bool] = ...,
        compression: Optional[grpc.Compression] = ...,
    ) -> _base_call.StreamUnaryCall: ...

class StreamStreamMultiCallable(abc.ABC, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def __call__(
        self,
        request_iterator: Optional[RequestIterableType] = ...,
        timeout: Optional[float] = ...,
        metadata: Optional[MetadataType] = ...,
        credentials: Optional[grpc.CallCredentials] = ...,
        wait_for_ready: Optional[bool] = ...,
        compression: Optional[grpc.Compression] = ...,
    ) -> _base_call.StreamStreamCall: ...

class Channel(abc.ABC, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    async def __aenter__(self): ...
    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb): ...
    @abc.abstractmethod
    async def close(self, grace: Optional[float] = ...): ...
    @abc.abstractmethod
    def get_state(self, try_to_connect: bool = ...) -> grpc.ChannelConnectivity: ...
    @abc.abstractmethod
    async def wait_for_state_change(self, last_observed_state: grpc.ChannelConnectivity) -> None: ...
    @abc.abstractmethod
    async def channel_ready(self) -> None: ...
    @abc.abstractmethod
    def unary_unary(
        self,
        method: str,
        request_serializer: Optional[SerializingFunction] = ...,
        response_deserializer: Optional[DeserializingFunction] = ...,
    ) -> UnaryUnaryMultiCallable: ...
    @abc.abstractmethod
    def unary_stream(
        self,
        method: str,
        request_serializer: Optional[SerializingFunction] = ...,
        response_deserializer: Optional[DeserializingFunction] = ...,
    ) -> UnaryStreamMultiCallable: ...
    @abc.abstractmethod
    def stream_unary(
        self,
        method: str,
        request_serializer: Optional[SerializingFunction] = ...,
        response_deserializer: Optional[DeserializingFunction] = ...,
    ) -> StreamUnaryMultiCallable: ...
    @abc.abstractmethod
    def stream_stream(
        self,
        method: str,
        request_serializer: Optional[SerializingFunction] = ...,
        response_deserializer: Optional[DeserializingFunction] = ...,
    ) -> StreamStreamMultiCallable: ...
