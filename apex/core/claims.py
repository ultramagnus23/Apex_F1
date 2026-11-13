"""Claim objects: every statement Apex outputs is one of four kinds.

OBSERVED      recorded data shows it, beyond the stated resolution, and it is
              stable under alternative reference laps and methods.
HYPOTHESIS    consistent with the data, not established. Lists its confounders.
UNKNOWN       cannot be established from public data at all.
INCONCLUSIVE  a difference exists in the data but is within noise, or is not
              stable across configurations. Replaces an OBSERVED claim whose
              stability falls below the threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Final


class Kind(StrEnum):
    OBSERVED = "OBSERVED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


STABILITY_THRESHOLD: Final = 0.8


@dataclass(frozen=True)
class Claim:
    kind: Kind
    statement: str
    evidence: tuple[str, ...] = ()
    magnitude: float | None = None
    magnitude_sigma: float | None = None
    unit: str = ""
    stability: float | None = None
    assumptions: tuple[str, ...] = ()
    confounders: tuple[str, ...] = ()
    note: str = ""

    def render(self) -> str:
        """One markdown line, tag first."""
        mag = ""
        if self.magnitude is not None:
            sig = f" ± {self.magnitude_sigma:.3f}" if self.magnitude_sigma is not None else ""
            mag = f" ({self.magnitude:+.3f}{sig} {self.unit})".replace("+-", "-")
        stab = f" [stability {self.stability:.0%}]" if self.stability is not None else ""
        return f"**{self.kind.value}**{stab}: {self.statement}{mag}"


def downgrade_if_unstable(claim: Claim, threshold: float = STABILITY_THRESHOLD) -> Claim:
    """OBSERVED claims below the stability threshold become INCONCLUSIVE."""
    if claim.kind is not Kind.OBSERVED or claim.stability is None:
        return claim
    if claim.stability >= threshold:
        return claim
    return replace(
        claim,
        kind=Kind.INCONCLUSIVE,
        note=f"downgraded from OBSERVED: stability {claim.stability:.0%} < {threshold:.0%}",
    )


def with_confounders(*items: str) -> tuple[str, ...]:
    return tuple(items)


__all__ = ["STABILITY_THRESHOLD", "Claim", "Kind", "downgrade_if_unstable", "field"]
