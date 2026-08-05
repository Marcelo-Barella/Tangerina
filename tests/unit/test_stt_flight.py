from __future__ import annotations

import pytest

from features.voice.stt_flight import SttFailureEvent, SttFailureKind, SttFlight


@pytest.mark.unit
def test_stt_flight_ring_and_snapshot():
    flight = SttFlight(maxlen=3)
    flight.record(SttFailureEvent(SttFailureKind.TIMEOUT, "sidecar", "t1", 1.0))
    flight.record(SttFailureEvent(SttFailureKind.HTTP_500, "sidecar", "t2", 2.0))
    flight.record(SttFailureEvent(SttFailureKind.EMPTY, "sidecar", "t3", 3.0))
    flight.record(SttFailureEvent(SttFailureKind.UNREACHABLE, "sidecar", "t4", 4.0))
    snap = flight.snapshot()
    assert snap.counts == {
        "http_500": 1,
        "empty": 1,
        "unreachable": 1,
    }
    assert snap.last is not None
    assert snap.last.kind is SttFailureKind.UNREACHABLE
    assert "timeout" not in snap.counts
