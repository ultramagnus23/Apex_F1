from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests

from apex.core.session import find_session_key
from apex.core.sources import fastf1_source
from apex.core.sources.openf1 import OpenF1Client, OpenF1Error


class _Resp:
    def __init__(self, status: int, body: bytes = b"[]") -> None:
        self.status_code = status
        self.content = body
        self.text = body.decode("utf-8", "replace")


def test_fastf1_refuses_without_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("F1_USERNAME", raising=False)
    monkeypatch.delenv("F1_PASSWORD", raising=False)
    assert not fastf1_source.has_credentials()
    with pytest.raises(fastf1_source.FastF1UnavailableError, match="F1_USERNAME"):
        fastf1_source.load_session(2026, "Austin", "Q", tmp_path)


def test_fastf1_has_credentials_when_both_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("F1_USERNAME", "u")
    monkeypatch.setenv("F1_PASSWORD", "p")
    assert fastf1_source.has_credentials()


def test_client_retries_transient_network_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = OpenF1Client(tmp_path, min_interval_s=0.0, max_retries=3)
    monkeypatch.setattr("apex.core.sources.openf1.time.sleep", lambda _s: None)
    calls: list[int] = []

    def flaky(url: str, timeout: float) -> _Resp:
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectionError("dropped")
        return _Resp(200, b'[{"ok": 1}]')

    monkeypatch.setattr(client._http, "get", flaky)
    assert client.frame("laps", {"session_key": 1}).iloc[0]["ok"] == 1
    assert len(calls) == 3


def test_client_gives_up_after_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = OpenF1Client(tmp_path, min_interval_s=0.0, max_retries=2)
    monkeypatch.setattr("apex.core.sources.openf1.time.sleep", lambda _s: None)

    def down(url: str, timeout: float) -> _Resp:
        raise requests.Timeout("slow")

    monkeypatch.setattr(client._http, "get", down)
    with pytest.raises(OpenF1Error, match="giving up"):
        client.fetch("laps", {"session_key": 2})


def test_client_rejects_http_errors_without_retrying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = OpenF1Client(tmp_path, min_interval_s=0.0)
    monkeypatch.setattr(client._http, "get", lambda url, timeout: _Resp(401, b"no"))
    with pytest.raises(OpenF1Error, match="HTTP 401"):
        client.fetch("laps", {"session_key": 3})


def test_find_session_key_resolves_unique_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = pd.DataFrame(
        {
            "session_key": [11, 22],
            "circuit_short_name": ["Austin", "Miami"],
            "location": ["Austin", "Miami Gardens"],
            "country_name": ["United States", "United States"],
        }
    )

    def fake_frame(self: OpenF1Client, endpoint: str, params: Any = None) -> pd.DataFrame:
        return sessions

    monkeypatch.setattr(OpenF1Client, "frame", fake_frame)
    assert find_session_key(2026, "austin", "Q", tmp_path, offline=True) == 11


def test_find_session_key_refuses_ambiguous_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = pd.DataFrame(
        {
            "session_key": [11, 22],
            "circuit_short_name": ["Miami", "Miami"],
            "location": ["Miami Gardens", "Miami"],
            "country_name": ["United States", "United States"],
        }
    )
    monkeypatch.setattr(OpenF1Client, "frame", lambda self, e, p=None: sessions)
    with pytest.raises(KeyError, match="matched 2"):
        find_session_key(2025, "Miami", "Q", tmp_path, offline=True)


def test_find_session_key_maps_short_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_frame(self: OpenF1Client, endpoint: str, params: Any = None) -> pd.DataFrame:
        seen.update(params or {})
        return pd.DataFrame(
            {
                "session_key": [5],
                "circuit_short_name": ["Monza"],
                "location": ["Monza"],
                "country_name": ["Italy"],
            }
        )

    monkeypatch.setattr(OpenF1Client, "frame", fake_frame)
    find_session_key(2026, "Monza", "SQ", tmp_path, offline=True)
    assert seen["session_name"] == "Sprint Qualifying"
