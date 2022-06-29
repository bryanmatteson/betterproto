from abc import ABC
from typing import Any, Dict, Mapping, Optional

import grpc
import grpc.aio

from ._casing import snake_case
from .types import MetadataLike


class _Base(ABC):
    _channel: Any
    _timeout: Optional[float]
    _metadata: Optional[MetadataLike]
    _name: str

    def __init__(
        self,
        channel: Any,
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
    def name(self) -> str:
        return self._name

    def _resolve_request_kwargs(self, timeout: Optional[float], metadata: Optional[MetadataLike]) -> Dict[str, Any]:
        timeout = self._timeout if timeout is None else timeout
        metadata = self._metadata if metadata is None else metadata
        if isinstance(metadata, Mapping):
            metadata = tuple(metadata.items())
        else:
            metadata = tuple(metadata or ())

        return {"timeout": timeout, "metadata": metadata}


class ServiceStub(_Base, ABC):
    @property
    def channel(self) -> grpc.Channel:
        return self._channel
