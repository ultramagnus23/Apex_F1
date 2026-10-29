"""Golden outputs for case study 01 (2026 USA GP Q3, ANT lap 14 vs VER lap 8).

A refactor must not silently change any of these numbers. To regenerate after
an *intended* change: ``APEX_UPDATE_GOLDEN=1 uv run pytest tests/regression``
and explain the change in the commit message.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

GOLDEN = Path(__file__).parent / "golden_case_study_01.json"


def _summary(cmp: Any) -> dict[str, Any]:
    g = cmp.grid
    return {
        "reference_line_m": cmp.track.line.length,
        "corners": [[c.label, c.kind, c.s_apex] for c in cmp.track.corners],
        "sector_boundaries": [cmp.boundaries.s1, cmp.boundaries.s2],
        "sectors_unanchored_delta": cmp.sectors["unanchored_delta"].tolist(),
        "sectors_anchored_delta": (cmp.sectors["anchored_a"] - cmp.sectors["anchored_b"]).tolist(),
        "gate": [[gg.lap_time_z, *gg.errors, gg.passed] for gg in cmp.gate],
        "warp_shift_m": [cmp.a.params["sector_shift_m"], cmp.b.params["sector_shift_m"]],
        "delta_every_250m": np.interp(np.arange(0, g[-1], 250.0), g, cmp.delta).tolist(),
        "corner_segment_delta": cmp.corner_segments["delta"].tolist(),
        "corner_segment_sigma": cmp.corner_segments["sigma"].tolist(),
        "minisector_delta": cmp.minisectors["delta"].tolist(),
        "brake_on_diff": [
            None if x is None or x != x else x for x in cmp.corners["brake_on_s_diff"].tolist()
        ],
        "v_min": cmp.corners[["v_min_kmh_A", "v_min_kmh_B"]].to_numpy().tolist(),
    }


def _close(a: Any, b: Any, path: str = "") -> None:
    if isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert a == pytest.approx(b, abs=1e-9, rel=1e-9), path
    else:
        assert a == b, path


def test_case_study_01_matches_golden(case_study) -> None:  # type: ignore[no-untyped-def]
    got = json.loads(json.dumps(_summary(case_study)))
    if os.environ.get("APEX_UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8", newline="\n")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    _close(got, expected)


def test_case_study_01_end_delta_is_official_gap(case_study) -> None:  # type: ignore[no-untyped-def]
    assert case_study.delta[-1] == pytest.approx(94.035 - 94.214, abs=1e-9)
    assert all(g.passed for g in case_study.gate)
