from abc import ABC

import grpc.aio

from ..client import _Base


class ServiceStub(_Base, ABC):
    @property
    def channel(self) -> grpc.aio.Channel:
        return self._channel
