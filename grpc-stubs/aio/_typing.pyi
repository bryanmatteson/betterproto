from ._metadata import Metadata as Metadata, MetadataKey as MetadataKey, MetadataValue as MetadataValue
from _typeshed import Incomplete
from typing import Any, AsyncIterable, Callable, Iterable, Sequence, Tuple, TypeVar, Union

RequestType = TypeVar("RequestType")
ResponseType = TypeVar("ResponseType")
SerializingFunction = Callable[[Any], bytes]
DeserializingFunction = Callable[[bytes], Any]
MetadatumType = Tuple[MetadataKey, MetadataValue]
MetadataType = Union[Metadata, Sequence[MetadatumType]]
ChannelArgumentType = Sequence[Tuple[str, Any]]
EOFType: Incomplete
DoneCallbackType = Callable[[Any], None]
RequestIterableType = Union[Iterable[Any], AsyncIterable[Any]]
ResponseIterableType = AsyncIterable[Any]
