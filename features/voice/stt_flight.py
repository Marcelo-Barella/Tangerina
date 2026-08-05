from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Optional


class SttFailureKind(Enum):
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    HTTP_500 = "http_500"
    HTTP_OTHER = "http_other"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SttFailureEvent:
    kind: SttFailureKind
    provider: str
    detail: str
    at_epoch_s: float


@dataclass(frozen=True)
class SttFlightSnapshot:
    counts: dict[str, int]
    last: Optional[SttFailureEvent]


class SttFlight:
    def __init__(self, maxlen: int = 50) -> None:
        self._events: Deque[SttFailureEvent] = deque(maxlen=maxlen)

    def record(self, event: SttFailureEvent) -> None:
        self._events.append(event)

    def snapshot(self) -> SttFlightSnapshot:
        counts: dict[str, int] = {}
        for event in self._events:
            key = event.kind.value
            counts[key] = counts.get(key, 0) + 1
        last = self._events[-1] if self._events else None
        return SttFlightSnapshot(counts=counts, last=last)
