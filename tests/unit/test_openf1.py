from pathlib import Path

import pytest

from apex.core.sources import openf1
from apex.core.sources.openf1 import CachedResponse, OpenF1Client, OpenF1Error, build_url


def test_build_url_is_canonical_and_keeps_operators() -> None:
    a = build_url(
        "car_data", {"session_key": 11392, "date>": "2026-10-24T21:20:00", "driver_number": 1}
    )
    b = build_url(
        "car_data", {"driver_number": 1, "date>": "2026-10-24T21:20:00", "session_key": 11392}
    )
    assert a == b
    assert a == (
        f"{openf1.BASE_URL}/car_data?date>2026-10-24T21:20:00&driver_number=1&session_key=11392"
    )


def test_cache_hit_returns_identical_bytes_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    body = b'[{"speed": 104, "date": "2026-10-24T21:20:00.183000+00:00"}]'

    def fake_get(self: OpenF1Client, url: str) -> bytes:
        calls.append(url)
        return body

    monkeypatch.setattr(OpenF1Client, "_get", fake_get)
    first = OpenF1Client(tmp_path).fetch("car_data", {"session_key": 1})
    assert not first.from_cache

    # A fresh client in offline mode must be served from disk, byte for byte.
    second = OpenF1Client(tmp_path, offline=True).fetch("car_data", {"session_key": 1})
    assert second.from_cache
    assert second.body == body
    assert calls == [first.url]

    with pytest.raises(OpenF1Error):
        OpenF1Client(tmp_path, offline=True).fetch("car_data", {"session_key": 2})


def test_detail_response_is_empty_result() -> None:
    resp = CachedResponse("u", b'{"detail": "No results found."}', from_cache=True)
    assert resp.json() == []
    with pytest.raises(OpenF1Error):
        CachedResponse("u", b'{"unexpected": 1}', from_cache=True).json()
