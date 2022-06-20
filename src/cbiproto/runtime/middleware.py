from grpclib.client import Channel
from grpclib.events import (
    RecvInitialMetadata,
    RecvMessage,
    RecvRequest,
    RecvTrailingMetadata,
    SendInitialMetadata,
    SendMessage,
    SendRequest,
    SendTrailingMetadata,
    listen,
)


class Middleware:
    async def on_send_message(self, event: SendMessage) -> None:
        pass

    async def on_recv_message(self, event: RecvMessage) -> None:
        pass

    async def on_send_request(self, event: SendRequest) -> None:
        pass

    async def on_recv_request(self, event: RecvRequest) -> None:
        pass

    async def on_send_initial_metadata(self, event: SendInitialMetadata) -> None:
        pass

    async def on_recv_initial_metadata(self, event: RecvInitialMetadata) -> None:
        pass

    async def on_send_trailing_metadata(self, event: SendTrailingMetadata) -> None:
        pass

    async def on_recv_trailing_metadata(self, event: RecvTrailingMetadata) -> None:
        pass


def add_channel_middleware(channel: Channel, *middleware: Middleware) -> None:
    for m in middleware:
        listen(channel, SendMessage, m.on_send_message)
        listen(channel, RecvMessage, m.on_recv_message)
        listen(channel, SendRequest, m.on_send_request)
        listen(channel, RecvRequest, m.on_recv_request)
        listen(channel, SendInitialMetadata, m.on_send_initial_metadata)
        listen(channel, RecvInitialMetadata, m.on_recv_initial_metadata)
        listen(channel, SendTrailingMetadata, m.on_send_trailing_metadata)
        listen(channel, RecvTrailingMetadata, m.on_recv_trailing_metadata)


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
