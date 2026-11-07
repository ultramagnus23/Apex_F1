import pandas as pd
import pytest

from apex.analysis.claims_build import Stability, build_claims
from apex.analysis.sensitivity import summarise_events, summarise_segments
from apex.core.claims import Kind
from apex.core.session import SessionData, load_parquet, save_parquet
from apex.report.claims_report import claims_markdown
from tests.conftest import CASE_A, CASE_B, FIXTURE


def test_parquet_roundtrip_preserves_raw_values(austin: SessionData, tmp_path) -> None:  # type: ignore[no-untyped-def]
    save_parquet(austin, tmp_path / "s")
    back = load_parquet(tmp_path / "s")
    assert back.session_key == austin.session_key
    pd.testing.assert_frame_equal(
        back.laps.reset_index(drop=True),
        austin.laps.reset_index(drop=True),
        check_dtype=False,
    )
    assert len(back.car) == len(austin.car)


def test_phase_windows_come_from_race_control(austin: SessionData) -> None:
    windows = austin.phase_windows()
    assert [w.phase for w in windows] == [1, 2, 3]
    assert all(w.start < w.end for w in windows)


def test_driver_lookup_by_code_and_number(austin: SessionData) -> None:
    assert austin.driver_number("ant") == CASE_A[0]
    assert austin.driver_code(CASE_B[0]) == "VER"
    with pytest.raises(KeyError):
        austin.driver_number("XXX")


def test_subset_keeps_only_requested_drivers(austin: SessionData) -> None:
    sub = austin.subset([CASE_A[0], CASE_B[0]])
    assert set(sub.car["driver_number"].unique()) == {CASE_A[0], CASE_B[0]}
    assert set(sub.laps["driver_number"].unique()) == {CASE_A[0], CASE_B[0]}


def test_claims_for_case_study_are_tagged_and_gated(case_study) -> None:  # type: ignore[no-untyped-def]
    from apex.analysis.sensitivity import verdict

    cs = case_study.corner_segments
    seg_rows = pd.DataFrame(
        {
            "segment": cs["segment"],
            "ref": "baseline",
            "method": "hybrid",
            "config": "baseline|hybrid",
            "pair": "one",
            "delta": cs["delta"],
            "sigma": cs["sigma"],
        }
    )
    seg_rows["verdict"] = [verdict(d, s_) for d, s_ in zip(cs["delta"], cs["sigma"], strict=True)]
    seg = summarise_segments(seg_rows, n_boot=50)
    corners = case_study.corners
    ev_rows = pd.DataFrame(
        {
            "config": "baseline|hybrid",
            "pair": "one",
            "ref": "baseline",
            "method": "hybrid",
            "corner": corners["corner"],
            "kind": corners["kind"],
            "brake_diff": corners["brake_on_s_diff"],
            "brake_res": corners["brake_on_resolution_m"],
            "pickup_diff": corners["pickup_s_diff"],
            "pickup_res": corners["pickup_resolution_m"],
            "vmin_diff": corners["v_min_kmh_diff"],
            "vexit_diff": corners["v_exit_kmh_diff"],
        }
    )
    ev = summarise_events(ev_rows)
    claims = build_claims(case_study, Stability(seg, ev), st_speeds=(328.0, 326.0))
    kinds = {c.kind for c in claims}
    assert kinds <= {Kind.OBSERVED, Kind.HYPOTHESIS, Kind.INCONCLUSIVE, Kind.UNKNOWN}
    # every OBSERVED claim that carries a stability clears the threshold
    for c in claims:
        if c.kind is Kind.OBSERVED and c.stability is not None:
            assert c.stability >= 0.8, c.statement
    # official gaps are always present and exact
    assert any("official gap" in c.statement for c in claims)
    # hypotheses always list confounders
    for c in claims:
        if c.kind is Kind.HYPOTHESIS:
            assert c.confounders, c.statement
    # unknowns are never attached to a number
    assert all(c.magnitude is None for c in claims if c.kind is Kind.UNKNOWN)


def test_markdown_groups_by_kind_and_lists_limits() -> None:
    from apex.core.claims import Claim

    text = claims_markdown(
        [
            Claim(Kind.UNKNOWN, "fuel mass"),
            Claim(Kind.OBSERVED, "A is faster", stability=0.9),
            Claim(Kind.HYPOTHESIS, "traction", confounders=("tyres",)),
        ],
        "t",
    )
    assert text.index("Observed") < text.index("Hypotheses") < text.index("Unknown")
    assert "could also explain this: tyres" in text


def test_fixture_path_exists() -> None:
    assert FIXTURE.exists()
