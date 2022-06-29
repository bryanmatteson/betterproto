import enum
import threading
import typing
import sys
from concurrent import futures
from types import TracebackType
from typing import Any, Literal, Optional, SupportsBytes, Union


_OptionKeyValue = typing.Tuple[str, typing.Any]
_Options = typing.Sequence[_OptionKeyValue]


class Compression(enum.IntEnum):
    NoCompression = ...
    Deflate = ...
    Gzip = ...


@enum.unique
class LocalConnectionType(enum.Enum):
    UDS = ...
    LOCAL_TCP = ...


Metadata = typing.Tuple[typing.Tuple[str, typing.Union[str, bytes]],...]


"""Create Client"""

def insecure_channel(
    target: str,
    options: typing.Optional[_Options] = None,
    compression: typing.Optional[Compression] = None,
) -> Channel:
    ...


def secure_channel(
    target: str,
    credentials: ChannelCredentials,
    options: typing.Optional[_Options] = None,
    compression: typing.Optional[Compression] = None,
) -> Channel:
    ...


Interceptor = typing.Union[
    UnaryUnaryClientInterceptor,
    UnaryStreamClientInterceptor,
    StreamUnaryClientInterceptor,
    StreamStreamClientInterceptor,
]

def intercept_channel(channel: Channel, *interceptors: Interceptor) -> Channel:
    ...


"""Create Client Credentials"""

def ssl_channel_credentials(
    root_certificates: typing.Optional[bytes] = None,
    private_key: typing.Optional[bytes] = None,
    certificate_chain: typing.Optional[bytes] = None,
) -> ChannelCredentials:
    ...


def local_channel_credentials(
    local_connect_type: LocalConnectionType = LocalConnectionType.LOCAL_TCP,
) -> ChannelCredentials:
    ...


def metadata_call_credentials(
    metadata_plugin: AuthMetadataPlugin,
    name: typing.Optional[str] = None,
) -> CallCredentials:
    ...


def access_token_call_credentials(access_token: str) -> CallCredentials:
    ...

def alts_channel_credentials(service_accounts: Optional[typing.Sequence[str]] = None) -> ChannelCredentials: ...
def compute_engine_channel_credentials() -> ChannelCredentials: ...
def xds_channel_credentials(fallback_credentials: Optional[ChannelCredentials] = None) -> ChannelCredentials: ...

def composite_call_credentials(
    creds1: CallCredentials,
    creds2: CallCredentials,
    *rest: CallCredentials,
) -> CallCredentials:
    ...

def composite_channel_credentials(
    channel_credentials: ChannelCredentials,
    call_credentials: CallCredentials,
    *rest: CallCredentials,
) -> ChannelCredentials:
    ...


"""Create Server"""

def server(
    thread_pool: futures.ThreadPoolExecutor,
    handlers: typing.Optional[typing.List[GenericRpcHandler]] = None,
    interceptors: typing.Optional[typing.List[ServerInterceptor]] = None,
    options: typing.Optional[_Options] = None,
    maximum_concurrent_rpcs: typing.Optional[int] = None,
    compression: typing.Optional[Compression] = None,
) -> Server:
    ...


"""Create Server Credentials"""

CertificateChainPair = typing.Tuple[bytes, bytes]

def ssl_server_credentials(
    private_key_certificate_chain_pairs: typing.List[CertificateChainPair],
    root_certificates: typing.Optional[bytes] = None,
    require_client_auth: bool = False,
) -> ServerCredentials:
    ...


def local_server_credentials(
    local_connect_type: LocalConnectionType = LocalConnectionType.LOCAL_TCP,
) -> ServerCredentials:
    ...


def ssl_server_certificate_configuration(
    private_key_certificate_chain_pairs: typing.List[CertificateChainPair],
    root_certificates: typing.Optional[bytes] = None,
) -> ServerCertificateConfiguration:
    ...


def dynamic_ssl_server_credentials(
    initial_certificate_configuration: ServerCertificateConfiguration,
    certificate_configuration_fetcher: typing.Callable[[], ServerCertificateConfiguration],
    require_client_authentication: bool = False,
) -> ServerCredentials:
    ...

def alts_server_credentials() -> ServerCredentials: ...
def insecure_server_credentials() -> ServerCredentials: ...
def xds_server_credentials(
    fallback_credentials: ServerCredentials,
) -> ServerCredentials: ...

"""RPC Method Handlers"""

# XXX: This is probably what appears in the add_FooServicer_to_server function
# in the _pb2_grpc files that get generated, which points to the FooServicer
# handler functions that get generated, which look like this:
#
#    def FloobDoob(self, request, context):
#       return response
#
Behaviour = typing.Callable

# XXX: These are probably the SerializeToTring/FromString pb2 methods, but
# this needs further investigation
RequestDeserializer = typing.Callable
ResponseSerializer = typing.Callable


def unary_unary_rpc_method_handler(
    behavior: Behaviour,
    request_deserializer: typing.Optional[RequestDeserializer] = None,
    response_serializer: typing.Optional[ResponseSerializer] = None,
) -> RpcMethodHandler:
    ...

def unary_stream_rpc_method_handler(
    behavior: Behaviour,
    request_deserializer: typing.Optional[RequestDeserializer] = None,
    response_serializer: typing.Optional[ResponseSerializer] = None,
) -> RpcMethodHandler:
    ...

def stream_unary_rpc_method_handler(
    behavior: Behaviour,
    request_deserializer: typing.Optional[RequestDeserializer] = None,
    response_serializer: typing.Optional[ResponseSerializer] = None,
) -> RpcMethodHandler:
    ...

def stream_stream_rpc_method_handler(
    behavior: Behaviour,
    request_deserializer: typing.Optional[RequestDeserializer] = None,
    response_serializer: typing.Optional[ResponseSerializer] = None,
) -> RpcMethodHandler:
    ...

def method_handlers_generic_handler(
    service: str,
    method_handlers: typing.Dict[str, RpcMethodHandler],
) -> GenericRpcHandler:
    ...


"""Channel Ready Future"""

def channel_ready_future(channel: Channel) -> Future:
    ...


"""Channel Connectivity"""

class ChannelConnectivity(enum.Enum):
    IDLE = ...
    CONNECTING = ...
    READY = ...
    TRANSIENT_FAILURE = ...
    SHUTDOWN = ...



"""gRPC Status Code"""

class Status:
    code: StatusCode

    # XXX: misnamed property, does not align with status.proto, where it is called 'message':
    details: str

    trailing_metadata: Metadata


class StatusCode(enum.Enum):
    OK = ...
    CANCELLED = ...
    UNKNOWN = ...
    INVALID_ARGUMENT = ...
    DEADLINE_EXCEEDED = ...
    NOT_FOUND = ...
    ALREADY_EXISTS = ...
    PERMISSION_DENIED = ...
    UNAUTHENTICATED = ...
    RESOURCE_EXHAUSTED = ...
    FAILED_PRECONDITION = ...
    ABORTED = ...
    UNIMPLEMENTED = ...
    INTERNAL = ...
    UNAVAILABLE = ...
    DATA_LOSS = ...


"""Channel Object"""

# XXX: These are probably the SerializeToTring/FromString pb2 methods, but
# this needs further investigation
RequestSerializer = typing.Callable[[TRequest], bytes]
ResponseDeserializer = typing.Callable[[bytes], TResponse]


class Channel:
    def close(self) -> None: ...

    def stream_stream(
        self,
        method: str,
        request_serializer: typing.Optional[RequestSerializer[TRequest]],
        response_deserializer: typing.Optional[ResponseDeserializer[TResponse]],
    ) -> StreamStreamMultiCallable[TRequest, TResponse]:
        ...

    def stream_unary(
        self,
        method: str,
        request_serializer: typing.Optional[RequestSerializer[TRequest]],
        response_deserializer: typing.Optional[ResponseDeserializer[TResponse]],
    ) -> StreamUnaryMultiCallable[TRequest, TResponse]:
        ...

    def subscribe(
        self,
        callback: typing.Callable[[ChannelConnectivity], None],
        try_to_connect: bool = False,
    ) -> None:
        ...

    def unary_stream(
        self,
        method: str,
        request_serializer: typing.Optional[RequestSerializer[TRequest]],
        response_deserializer: typing.Optional[ResponseDeserializer[TResponse]],
    ) -> UnaryStreamMultiCallable[TRequest, TResponse]:
        ...

    def unary_unary(
        self,
        method: str,
        request_serializer: typing.Optional[RequestSerializer[TRequest]],
        response_deserializer: typing.Optional[ResponseDeserializer[TResponse]],
    ) -> UnaryUnaryMultiCallable[TRequest, TResponse]:
        ...

    def unsubscribe(
        self,
        callback: typing.Callable[[ChannelConnectivity], None],
    ) -> None:
        ...

    def __enter__(self) -> Channel:
        ...

    def __exit__(self,
        exc_type: typing.Optional[typing.Type[BaseException]],
        exc_val: typing.Optional[BaseException],
        exc_tb: typing.Optional[TracebackType],
    ) -> typing.Optional[bool]:
        ...


class Server:
    def add_generic_rpc_handlers(self, generic_rpc_handlers: typing.Iterable[GenericRpcHandler]) -> None: ...
    def add_insecure_port(self, address: str) -> int: ...
    def add_secure_port(self, address: str, server_credentials: ServerCredentials) -> int: ...
    def start(self) -> None: ...
    def stop(self, grace: typing.Optional[float] = None) -> threading.Event: ...
    def wait_for_termination(self, timeout: typing.Optional[float] = None) -> bool: ...

class ChannelCredentials:
    """This class has no supported interface"""

class CallCredentials:
    """This class has no supported interface"""

class AuthMetadataContext:
    service_url: str
    method_name: str

class AuthMetadataPluginCallback:
    def __call__(self, metadata: Metadata, error: typing.Optional[Exception]) -> None: ...

class AuthMetadataPlugin:
    def __call__(self, context: AuthMetadataContext, callback: AuthMetadataPluginCallback) -> None: ...

class ServerCredentials:
    """This class has no supported interface"""

class ServerCertificateConfiguration:
    """This class has no supported interface"""

class _Metadatum:
    key: str
    value: bytes


class RpcError(Exception):
    def code(self) -> StatusCode: ...
    def details(self) -> str: ...
    def trailing_metadata(self) -> typing.Tuple[_Metadatum, ...]: ...



class RpcContext:
    def add_callback(self, callback: typing.Callable[[], None]) -> bool: ...
    def cancel(self): ...
    def is_active(self) -> bool: ...
    def time_remaining(self) -> float: ...


class Call(RpcContext):
    def code(self) -> StatusCode: ...
    def details(self) -> str: ...
    def initial_metadata(self) -> Metadata: ...
    def trailing_metadata(self) -> Metadata: ...


class ClientCallDetails:
    method: str
    timeout: typing.Optional[float]
    metadata: typing.Optional[Metadata]
    credentials: typing.Optional[CallCredentials]
    wait_for_ready: typing.Optional[bool]
    compression: typing.Optional[Compression]


TRequest = typing.TypeVar("TRequest")
TResponse = typing.TypeVar("TResponse")

class CallFuture(typing.Generic[TResponse], Call, Future[TResponse]):
    pass


class UnaryUnaryClientInterceptor(typing.Generic[TRequest, TResponse]):
    def intercept_unary_unary(
        self,
        continuation: typing.Callable[[ClientCallDetails, TRequest], CallFuture[TResponse]],
        client_call_details: ClientCallDetails,
        request: TRequest,
    ) -> CallFuture[TResponse]:
        ...


class CallIterator(typing.Generic[TResponse], Call):
    def __iter__(self) -> typing.Iterator[TResponse]: ...

class UnaryStreamClientInterceptor(typing.Generic[TRequest, TResponse]):
    def intercept_unary_stream(
        self,
        continuation: typing.Callable[[ClientCallDetails, TRequest], CallIterator[TResponse]],
        client_call_details: ClientCallDetails,
        request: TRequest,
    ) -> CallIterator[TResponse]:
        ...


class StreamUnaryClientInterceptor(typing.Generic[TRequest, TResponse]):
    def intercept_stream_unary(
        self,
        continuation: typing.Callable[[ClientCallDetails, TRequest], CallFuture[TResponse]],
        client_call_details: ClientCallDetails,
        request_iterator: typing.Iterator[TRequest],
    ) -> CallFuture[TResponse]:
        ...


class StreamStreamClientInterceptor(typing.Generic[TRequest, TResponse]):
    def intercept_stream_stream(
        self,
        continuation: typing.Callable[[ClientCallDetails, TRequest], CallIterator[TResponse]],
        client_call_details: ClientCallDetails,
        request_iterator: typing.Iterator[TRequest],
    ) -> CallIterator[TResponse]:
        ...


class ServicerContext(RpcContext):
    def abort(self, code: StatusCode, details: str) -> typing.NoReturn: ...
    def abort_with_status(self, status: Status) -> typing.NoReturn: ...
    def auth_context(self) -> typing.Mapping[str, typing.Iterable[bytes]]: ...
    def disable_next_message_compression(self) -> None: ...
    def invocation_metadata(self) -> Metadata: ...
    def peer(self) -> str: ...
    def peer_identities(self) -> typing.Optional[typing.Iterable[bytes]]: ...
    def peer_identity_key(self) -> typing.Optional[str]: ...
    def send_initial_metadata(self, initial_metadata: Metadata) -> None: ...
    def set_code(self, code: StatusCode) -> None: ...
    def set_compression(self, compression: Compression) -> None: ...
    def set_trailing_metadata(self, trailing_metadata: Metadata) -> None: ...
    def set_details(self, details: str) -> None: ...

class RpcMethodHandler(typing.Generic[TRequest, TResponse]):
    request_streaming: bool
    response_streaming: bool
    request_deserializer: typing.Optional[RequestDeserializer]
    response_serializer: typing.Optional[ResponseSerializer]
    unary_unary: typing.Optional[typing.Callable[[TRequest, ServicerContext], TResponse]]
    unary_stream: typing.Optional[typing.Callable[[TRequest, ServicerContext], typing.Iterator[TResponse]]]
    stream_unary: typing.Optional[typing.Callable[[typing.Iterator[TRequest], ServicerContext], TResponse]]
    stream_stream: typing.Optional[typing.Callable[[typing.Iterator[TRequest], ServicerContext], typing.Iterator[TResponse]]]


class HandlerCallDetails:
    method: str
    invocation_metadata: Metadata


class GenericRpcHandler(typing.Generic[TRequest, TResponse]):
    def service(self, handler_call_details: HandlerCallDetails) -> typing.Optional[RpcMethodHandler[TRequest, TResponse]]:
        ...

class ServiceRpcHandler:
    def service_name(self) -> str: ...

class ServerInterceptor(typing.Generic[TRequest, TResponse]):
    def intercept_service(
        self,
        continuation: typing.Callable[
            [HandlerCallDetails],
            typing.Optional[RpcMethodHandler[TRequest, TResponse]]
        ],
        handler_call_details: HandlerCallDetails,
    ) -> RpcMethodHandler[TRequest, TResponse]:
        ...


class UnaryUnaryMultiCallable(typing.Generic[TRequest, TResponse]):
    def __call__(
        self,
        request: TRequest,
        timeout: typing.Optional[int] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> TResponse:
        ...

    def future(
        self,
        request: TRequest,
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> CallFuture[TResponse]:
        ...

    def with_call(
        self,
        request: TRequest,
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> typing.Tuple[TResponse, Call]:
        ...


class UnaryStreamMultiCallable(typing.Generic[TRequest, TResponse]):
    def __call__(
        self,
        request: TRequest,
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> CallIterator[TResponse]:
        ...


class StreamUnaryMultiCallable(typing.Generic[TRequest, TResponse]):
    def __call__(
        self,
        request_iterator: typing.Iterator[TRequest],
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> TResponse:
        ...

    def future(
        self,
        request_iterator: typing.Iterator[TRequest],
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> CallFuture[TResponse]:
        ...

    def with_call(
        self,
        request_iterator: typing.Iterator[TRequest],
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> typing.Tuple[TResponse, Call]:
        ...


class StreamStreamMultiCallable(typing.Generic[TRequest, TResponse]):
    def __call__(
        self,
        request_iterator: typing.Iterator[TRequest],
        timeout: typing.Optional[float] = None,
        metadata: typing.Optional[Metadata] = None,
        credentials: typing.Optional[CallCredentials] = None,
        wait_for_ready: typing.Optional[bool] = None,
        compression: typing.Optional[Compression] = None,
    ) -> CallIterator[TResponse]:
        ...


class FutureTimeoutError(Exception): ...
class FutureCancelledError(Exception): ...
TFutureValue = typing.TypeVar("TFutureValue")

class Future(typing.Generic[TFutureValue]):
    def add_done_callback(self, fn: typing.Callable[[Future[TFutureValue]], None]) -> None: ...
    def cancel(self) -> bool: ...
    def cancelled(self) -> bool: ...
    def done(self) -> bool: ...
    def exception(self) -> typing.Optional[Exception]: ...
    def result(self, timeout: typing.Optional[float] = None) -> TFutureValue: ...
    def running(self) -> bool: ...
    def traceback(self, timeout: typing.Optional[float] = None) -> typing.Any: ...
