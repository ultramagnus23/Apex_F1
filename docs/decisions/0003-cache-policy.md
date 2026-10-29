# ADR 0003: Caching Strategy & Offline Verification Policy

## Status
Accepted

## Context
Raw Formula 1 telemetry datasets from FastF1 can be tens of megabytes per session and depend on live network connections. FastF1 calls external APIs (Ergast / OpenF1 / Formula1.com live timing) that may fail or rate-limit during local testing or CI.

## Decision
1. **Local Persistent Cache**: Raw OpenF1 responses are cached byte-for-byte under `cache/openf1` (never rewritten). FastF1's file cache (when credentials allow FastF1 at all, see DATA_CONTRACT §0) lives in `cache/fastf1`. Both are non-versioned.
2. **Deterministic Offline Fixtures**: Tests must never rely on network access. A curated, representative offline fixture set (covering a realistic F1 qualifying lap pair with all key channels: Distance, Time, Speed, Throttle, Brake, Gear, RPM, and official sector timing) is stored in `tests/fixtures/` (Parquet subset of the raw OpenF1 rows around every push lap of 2026 USA GP qualifying, built by `scripts/make_fixture.py`). *(Path corrected 2026-10-29; there is no `backend/` directory.)*
3. **Graceful Fallback**: If network calls fail or offline mode is forced, the system can seamlessly load validated local session fixtures.
4. **Git Hygiene**: Cache directories (`cache/`, `*.pkl`, `*.feather`) are strictly gitignored to keep the repository light and reproducible.
