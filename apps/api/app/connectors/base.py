from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


NormalizedPayload = dict[str, Any]
RawPayload = dict[str, Any]


@dataclass(frozen=True)
class MockConnector:
    connector_key: str
    source_code: str
    provider_name: str
    payload_shape: str
    records: tuple[RawPayload, ...]
    normalize: Callable[[RawPayload], NormalizedPayload]

    def iter_records(self) -> Iterable[RawPayload]:
        return self.records
