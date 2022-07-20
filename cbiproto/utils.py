import signal
from contextlib import contextmanager
from types import FrameType
from typing import Collection, Iterator, Optional

from .types import IClosable


class SignalHandler:
    def __init__(self, signals: Collection[int], closables: Collection[IClosable]):
        self._signals = signals
        self._closables = closables
        self._first = True

    def _handle_signal(self, sig: int, frame: Optional[FrameType]) -> None:
        if self._first:
            self._first = False
            fail = False
            for closable in self._closables:
                try:
                    closable.close()
                except RuntimeError:
                    fail = True
            if not fail:
                return
        raise SystemExit(128 + sig)

    def __enter__(self):
        for sig in self._signals:
            signal.signal(sig, self._handle_signal)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for sig in self._signals:
            signal.signal(sig, signal.SIG_DFL)


@contextmanager
def graceful_exit(
    servers: Collection[IClosable], *, signals: Collection[int] = (signal.SIGINT, signal.SIGTERM),
) -> Iterator[None]:
    signals = set(signals)
    with SignalHandler(signals, servers):
        yield
