from __future__ import annotations

import threading
from abc import ABC
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Dict, Optional

import grpc
import grpc.aio
from typing_extensions import assert_never

from .types import Cardinality, Handler, IServable


class ServiceBase(ABC):
    pass


@dataclass
class TLSConfig:
    cacert_file: str
    server_cert_file: str
    server_key_file: str
    require_client_auth: bool = False


class Server:
    _server: Optional[grpc.Server]
    _mapping: Dict[str, Handler]
    _max_workers: int

    def __init__(
        self, handlers: Collection[IServable], *, max_workers: int = 10, tls_config: Optional[TLSConfig] = None
    ) -> None:
        self._mapping = {}
        self._max_workers = max_workers
        self._server = None
        self._tls_config = tls_config

        for handler in handlers:
            self._mapping.update(handler.__mapping__())

    def start(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        if self._server is not None:
            raise RuntimeError("Server is already started")

        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=self._max_workers))
        handlers_by_service: Dict[str, Dict[str, grpc.RpcMethodHandler]] = {}

        for method, handler in self._mapping.items():
            service, method = method.strip("/").rsplit("/", maxsplit=1)

            if handler.cardinality == Cardinality.UNARY_UNARY:
                rpc_method = grpc.unary_unary_rpc_method_handler(
                    handler.func,
                    request_deserializer=handler.request_type.parse_raw,
                    response_serializer=handler.reply_type.__bytes__,
                )
            elif handler.cardinality == Cardinality.UNARY_STREAM:
                rpc_method = grpc.unary_stream_rpc_method_handler(
                    handler.func,
                    request_deserializer=handler.request_type.parse_raw,
                    response_serializer=handler.reply_type.__bytes__,
                )
            elif handler.cardinality == Cardinality.STREAM_UNARY:
                rpc_method = grpc.stream_unary_rpc_method_handler(
                    handler.func,
                    request_deserializer=handler.request_type.parse_raw,
                    response_serializer=handler.reply_type.__bytes__,
                )
            elif handler.cardinality == Cardinality.STREAM_STREAM:
                rpc_method = grpc.stream_stream_rpc_method_handler(
                    handler.func,
                    request_deserializer=handler.request_type.parse_raw,
                    response_serializer=handler.reply_type.__bytes__,
                )
            else:
                assert_never(handler.cardinality)

            handlers_by_service.setdefault(service, {})[method] = rpc_method

        for service, rpc_handlers in handlers_by_service.items():
            generic_handler = grpc.method_handlers_generic_handler(service, rpc_handlers)
            self._server.add_generic_rpc_handlers((generic_handler,))

        address = host or "localhost"
        if port:
            address += f":{port}"

        if self._tls_config is not None:
            cacert = Path(self._tls_config.cacert_file).read_bytes()
            server_key = Path(self._tls_config.server_key_file).read_bytes()
            server_cert = Path(self._tls_config.server_cert_file).read_bytes()
            server_credentials = grpc.ssl_server_credentials(
                [(server_key, server_cert)],
                root_certificates=cacert,
                require_client_auth=self._tls_config.require_client_auth,
            )
            self._server.add_secure_port(address, server_credentials)
        else:
            self._server.add_insecure_port(address)

        self._server.start()

    def close(self, grace_period: Optional[float] = None) -> threading.Event:
        if self._server is None:
            raise RuntimeError("Server is not started")
        return self._server.stop(grace_period)

    def wait_closed(self) -> bool:
        if self._server is None:
            raise RuntimeError("Server is not started")
        return self._server.wait_for_termination()
