from typing import Any


class Unset:
    def __eq__(self, other):
        return isinstance(other, Unset)

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> "Unset":
        return self

    def __deepcopy__(self, other: Any) -> "Unset":
        return self

    def __str__(self) -> str:
        return "<UNSET>"

    def __repr__(self) -> str:
        return "<UNSET>"

    def __hash__(self) -> int:
        return hash(str(self))


UNSET = Unset()
