import inspect
import textwrap
from typing import Any, Callable, Coroutine, Dict, Literal, Protocol, Type, Union, cast, runtime_checkable

from grpclib._typing import IEventsTarget
from grpclib.events import (
    RecvInitialMetadata,
    RecvMessage,
    RecvRequest,
    RecvTrailingMetadata,
    SendInitialMetadata,
    SendMessage,
    SendRequest,
    SendTrailingMetadata,
    _Callback,
    _Dispatch,
    _Event,
    _EventType,
    listen,
)
from typing_extensions import TypeGuard


@runtime_checkable
class OnSendMessage(Protocol):
    def on_send_message(self, event: SendMessage) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnRecvMessage(Protocol):
    def on_recv_message(self, event: RecvMessage) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnSendRequest(Protocol):
    def on_send_request(self, event: SendRequest) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnRecvRequest(Protocol):
    def on_recv_request(self, event: RecvRequest) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnSendInitialMetadata(Protocol):
    def on_send_initial_metadata(self, event: SendInitialMetadata) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnRecvInitialMetadata(Protocol):
    def on_recv_initial_metadata(self, event: RecvInitialMetadata) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnSendTrailingMetadata(Protocol):
    def on_send_trailing_metadata(self, event: SendTrailingMetadata) -> Union[Coroutine[Any, Any, None], None]:
        ...


@runtime_checkable
class OnRecvTrailingMetadata(Protocol):
    def on_recv_trailing_metadata(self, event: RecvTrailingMetadata) -> Union[Coroutine[Any, Any, None], None]:
        ...


MiddlewareProtocols = Union[
    OnSendMessage,
    OnRecvMessage,
    OnSendRequest,
    OnRecvRequest,
    OnSendInitialMetadata,
    OnRecvInitialMetadata,
    OnSendTrailingMetadata,
    OnRecvTrailingMetadata,
]

_EventHandler = Callable[[_EventType], Union[Coroutine[Any, Any, None], None]]


def maybe_wrap(fn: _EventHandler[_EventType]) -> _Callback:
    if inspect.iscoroutinefunction(fn):
        return cast(Any, fn)

    fn = cast(Callable[[Any], None], fn)

    async def wrapped(event: _Event) -> None:
        return fn(event)

    return wrapped


EventName = Literal[
    "on_send_message",
    "on_recv_message",
    "on_send_request",
    "on_recv_request",
    "on_send_initial_metadata",
    "on_recv_initial_metadata",
    "on_send_trailing_metadata",
    "on_recv_trailing_metadata",
]
_name_to_events: Dict[EventName, Type[_Event]] = {
    "on_send_message": SendMessage,
    "on_recv_message": RecvMessage,
    "on_send_request": SendRequest,
    "on_recv_request": RecvRequest,
    "on_send_initial_metadata": SendInitialMetadata,
    "on_recv_initial_metadata": RecvInitialMetadata,
    "on_send_trailing_metadata": SendTrailingMetadata,
    "on_recv_trailing_metadata": RecvTrailingMetadata,
}


def is_events_target(obj: Any) -> TypeGuard[IEventsTarget]:
    return isinstance(getattr(obj, "__dispatch__", None), _Dispatch)


class ChannelMiddlewareMixin(IEventsTarget):
    __dispatch__: _Dispatch

    def add_middleware(self, *middleware: MiddlewareProtocols) -> None:
        for name, method in inspect.getmembers(middleware, inspect.ismethod):
            if name in _name_to_events:
                self.handle_event(name, method)

    def handle_event(self, name: EventName, handler: _EventHandler[_EventType]) -> None:
        if name not in _name_to_events:
            raise ValueError(f"Unknown event name: {name}")
        return listen(self, _name_to_events[name], maybe_wrap(handler))

    for name in _name_to_events:
        exec(
            textwrap.dedent(
                f"""
        def {name}(self, handler: _EventHandler[_EventType]) -> None:
            self.handle_event('{name}', handler)
            """
            )
        )


# class DefaultMiddlewareContext(ContextModel):
#     span: Optional[Span] = Field(default=None)
#     tags: List[str] = Field(default_factory=list)
#     start_time: datetime = Field(default_factory=datetime.utcnow)
#     service_name: str = Field(default="")
#     method_name: str = Field(default="")


# class DefaultMiddleware(Middleware):
#     ctx = DefaultMiddlewareContext()

#     async def on_send_request(self, event: SendRequest) -> None:
#         service_name, method_name = parse_endpoint(event.method_name)

#         if isinstance(event.metadata, MultiDict):
#             metadata = list(event.metadata.items())
#             update_metadata_from_context(metadata)
#             add_request_origin_to_metadata(metadata, getenv().service_name)
#             current_metadata_keys = get_current_metadata_keys(metadata)
#             span = initialize_tracing_info(metadata, current_metadata_keys, event.method_name)

#             event.metadata.clear()
#             event.metadata.extend(metadata)

#             if span:
#                 self.ctx.span = span.__enter__()

#         self.ctx.start_time = datetime.now()
#         self.ctx.tags = [f"endpoint:{event.method_name}"]
#         self.ctx.service_name = service_name
#         self.ctx.method_name = method_name

#     async def on_recv_trailing_metadata(self, event: RecvTrailingMetadata):
#         logger = logging.getLogger(__name__)
#         ctx = self.ctx
#         if ctx.span:
#             ctx.span.__exit__(*exc_info())

#         if event.status is not Status.OK:
#             message = (
#                 f"Calling {ctx.service_name}.{ctx.method_name}"
#                 f"failed with a status of {event.status}: {event.status_message}"
#             )
#             health_key = f"grpc.client.call.{ctx.service_name}.{ctx.method_name}"
#             HealthCheck.set_health_for_key(HealthLevels.DEGRADED, health_key, message)
#             logger.error(message)
#             DataDog.increment_error("client.all", tags=ctx.tags)
#             DataDog.increment_error(f"client.{ctx.service_name}.{ctx.method_name}", tags=ctx.tags)
#         else:
#             DataDog.client_call_time(
#                 int((datetime.now() - ctx.start_time).total_seconds() * 1000),
#                 client_name=ctx.service_name,
#                 tags=ctx.tags,
#             )
