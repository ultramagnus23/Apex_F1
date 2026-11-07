"""OpenF1 REST client with an immutable on-disk cache of raw responses.

Every response body is stored byte-for-byte as gzip JSON under
``<cache_dir>/<sha256(url)>.json.gz`` next to a small metadata sidecar. Cached
bodies are never rewritten: a cache hit returns exactly the bytes first
observed, which makes downstream processing deterministic and traceable.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

import pandas as pd
import requests

BASE_URL: Final = "https://api.openf1.org/v1"

# Operators OpenF1 accepts as a suffix on a filter key, e.g. ``date>=``.
_OPERATORS: Final = (">=", "<=", ">", "<")


class OpenF1Error(RuntimeError):
    """Raised when OpenF1 returns an unrecoverable error."""


def build_url(endpoint: str, params: Mapping[str, Any] | None = None) -> str:
    """Build a canonical OpenF1 URL.

    Keys may carry a comparison operator suffix (``"date>"``); the operator is
    kept literal because OpenF1 parses it from the raw query string. Params are
    sorted so the same request always maps to the same cache key.
    """
    if not endpoint or "/" in endpoint.strip("/"):
        raise ValueError(f"invalid OpenF1 endpoint: {endpoint!r}")
    parts: list[str] = []
    for key in sorted(params or {}):
        value = (params or {})[key]
        name, op = key, "="
        for candidate in _OPERATORS:
            if key.endswith(candidate):
                name, op = key[: -len(candidate)], candidate
                break
        parts.append(f"{quote(name)}{op}{quote(str(value), safe=':')}")
    query = "&".join(parts)
    url = f"{BASE_URL}/{endpoint.strip('/')}"
    return f"{url}?{query}" if query else url


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    url: str
    body: bytes
    from_cache: bool

    def json(self) -> list[dict[str, Any]]:
        data = json.loads(self.body)
        if isinstance(data, dict):
            # OpenF1 reports "no results" as {"detail": "No results found."}.
            if "detail" in data:
                return []
            raise OpenF1Error(f"unexpected object response for {self.url}: {data!r}")
        if not isinstance(data, list):
            raise OpenF1Error(f"unexpected response type for {self.url}: {type(data)}")
        return data


class OpenF1Client:
    """Minimal, polite OpenF1 client. Network access only on cache miss."""

    def __init__(
        self,
        cache_dir: Path | str,
        *,
        offline: bool = False,
        min_interval_s: float = 0.4,
        max_retries: int = 5,
        timeout_s: float = 60.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._last_request = 0.0
        self._http = requests.Session()

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = cache_key(url)
        return self.cache_dir / f"{key}.json.gz", self.cache_dir / f"{key}.meta.json"

    def fetch(self, endpoint: str, params: Mapping[str, Any] | None = None) -> CachedResponse:
        url = build_url(endpoint, params)
        body_path, meta_path = self._paths(url)
        if body_path.exists():
            return CachedResponse(url, gzip.decompress(body_path.read_bytes()), True)
        if self.offline:
            raise OpenF1Error(f"offline mode and no cached response for {url}")
        body = self._get(url)
        # Write body first, then metadata; a crash leaves at worst a body without
        # metadata, which is still a valid observation.
        tmp = body_path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body, mtime=0))
        tmp.replace(body_path)
        meta = {
            "url": url,
            "fetched_at_utc": datetime.now(UTC).isoformat(),
            "bytes": len(body),
            "sha256_body": hashlib.sha256(body).hexdigest(),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return CachedResponse(url, body, False)

    def _get(self, url: str) -> bytes:
        delay = 1.0
        for _attempt in range(self.max_retries):
            wait = self.min_interval_s - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            resp = self._http.get(url, timeout=self.timeout_s)
            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 404:
                # OpenF1 uses 404 + {"detail": ...} for empty result sets.
                return resp.content
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            raise OpenF1Error(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
        raise OpenF1Error(f"giving up after {self.max_retries} attempts: {url}")

    def frame(self, endpoint: str, params: Mapping[str, Any] | None = None) -> pd.DataFrame:
        """Fetch an endpoint as a DataFrame of raw values (no parsing beyond JSON)."""
        return pd.DataFrame.from_records(self.fetch(endpoint, params).json())
