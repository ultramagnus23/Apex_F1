# ADR 0003: Caching Strategy & Offline Verification Policy

## Status
Accepted

## Context
Raw Formula 1 telemetry datasets from FastF1 can be tens of megabytes per session and depend on live network connections. FastF1 calls external APIs (Ergast / OpenF1 / Formula1.com live timing) that may fail or rate-limit during local testing or CI.

## Decision
1. **Local Persistent Cache**: FastF1's built-in file caching is enabled in a dedicated non-versioned directory (`cache/fastf1`), configurable via `APEX_CACHE_DIR`.
2. **Deterministic Offline Fixtures**: Tests must never rely on network access. A curated, representative offline fixture set (covering a realistic F1 qualifying lap pair with all key channels: Distance, Time, Speed, Throttle, Brake, Gear, RPM, and official sector timing) is stored in `backend/tests/fixtures/`.
3. **Graceful Fallback**: If network calls fail or offline mode is forced, the system can seamlessly load validated local session fixtures.
4. **Git Hygiene**: Cache directories (`cache/`, `*.pkl`, `*.feather`) are strictly gitignored to keep the repository light and reproducible.
