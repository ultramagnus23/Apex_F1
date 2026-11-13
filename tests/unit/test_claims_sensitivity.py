import numpy as np
import pandas as pd

from apex.analysis.sensitivity import summarise_events, summarise_segments, verdict
from apex.core.claims import Claim, Kind, downgrade_if_unstable


def test_unstable_observed_claim_is_downgraded() -> None:
    c = Claim(Kind.OBSERVED, "B is faster through C16", stability=0.52)
    out = downgrade_if_unstable(c)
    assert out.kind is Kind.INCONCLUSIVE
    assert "downgraded" in out.note


def test_stable_observed_claim_is_kept() -> None:
    c = Claim(Kind.OBSERVED, "A is faster through C7", stability=0.9)
    assert downgrade_if_unstable(c).kind is Kind.OBSERVED


def test_hypotheses_and_unknowns_are_never_upgraded_or_changed() -> None:
    h = Claim(Kind.HYPOTHESIS, "earlier traction", stability=0.1)
    assert downgrade_if_unstable(h) == h


def test_render_puts_tag_first_and_shows_stability() -> None:
    c = Claim(
        Kind.OBSERVED, "A is faster", magnitude=-0.1, magnitude_sigma=0.05, unit="s", stability=0.85
    )
    text = c.render()
    assert text.startswith("**OBSERVED** [stability 85%]")
    assert "-0.100 ± 0.050 s" in text


def test_verdict_respects_two_sigma() -> None:
    assert verdict(-0.05, 0.02) == "A"
    assert verdict(0.05, 0.02) == "B"
    assert verdict(0.03, 0.02) == "none"


def test_segment_stability_is_share_agreeing_with_majority() -> None:
    rows = []
    for i, v in enumerate(["A"] * 8 + ["B"] * 2):
        rows.append(
            {
                "segment": "C1",
                "ref": "baseline" if i < 4 else "mid",
                "method": "hybrid",
                "delta": -0.1,
                "sigma": 0.02,
                "verdict": v,
                "config": str(i),
            }
        )
    s = summarise_segments(pd.DataFrame(rows), n_boot=200)
    row = s.iloc[0]
    assert row["consensus"] == "A"
    assert np.isclose(row["stability"], 0.8)
    assert row["kind"] == "OBSERVED"


def test_segment_flipping_verdict_is_inconclusive() -> None:
    rows = [
        {
            "segment": "C7",
            "ref": "baseline",
            "method": "hybrid",
            "delta": -0.1,
            "sigma": 0.02,
            "verdict": "A" if i < 6 else "B",
            "config": str(i),
        }
        for i in range(10)
    ]
    s = summarise_segments(pd.DataFrame(rows), n_boot=200)
    assert s.iloc[0]["kind"] == "INCONCLUSIVE"
    assert "flips" in s.iloc[0]["why"]


def test_event_stability_counts_only_resolved_differences() -> None:
    ev = pd.DataFrame(
        {
            "corner": ["C1"] * 4,
            "kind": ["braking"] * 4,
            "brake_diff": [-20.0, -18.0, -2.0, 15.0],
            "brake_res": [5.0, 5.0, 5.0, 5.0],
            "pickup_diff": [0.0] * 4,
            "pickup_res": [5.0] * 4,
            "vmin_diff": [0.0] * 4,
            "vexit_diff": [0.0] * 4,
        }
    )
    row = summarise_events(ev).iloc[0]
    # three resolved differences, two earlier (negative) and one later: 2 of 4 agree
    assert np.isclose(row["brake_diff_stability"], 0.5)
