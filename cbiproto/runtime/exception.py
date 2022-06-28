from typing import Any, Optional

from .types import Status


class GRPCError(Exception):
    """
    Expected error, may be raised during RPC call
    """

    def __init__(self, status: Status, message: Optional[str] = None, details: Any = None) -> None:
        super().__init__(status, message, details)
        self.status = status
        self.message = message
        self.details = details
