"""Markdown rendering of tagged claims, grouped so limits are never hidden."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from apex.core.claims import Claim, Kind

ORDER = (Kind.OBSERVED, Kind.HYPOTHESIS, Kind.INCONCLUSIVE, Kind.UNKNOWN)
HEADINGS = {
    Kind.OBSERVED: "Observed (data shows it, stable across configurations)",
    Kind.HYPOTHESIS: "Hypotheses (consistent with the data; not established)",
    Kind.INCONCLUSIVE: "Inconclusive (within noise, or not stable)",
    Kind.UNKNOWN: "Unknown (public data cannot establish this)",
}


def claims_markdown(claims: Sequence[Claim], title: str) -> str:
    lines = [f"# {title}", ""]
    counts = {k: sum(1 for c in claims if c.kind is k) for k in ORDER}
    lines.append("Tags: " + ", ".join(f"{k.value} {counts[k]}" for k in ORDER) + ".")
    lines.append("")
    for kind in ORDER:
        group = [c for c in claims if c.kind is kind]
        if not group:
            continue
        lines += [f"## {HEADINGS[kind]}", ""]
        for c in group:
            lines.append(f"- {c.render()}")
            if c.evidence:
                lines.append(f"  - evidence: {'; '.join(c.evidence)}")
            if c.confounders:
                lines.append(f"  - could also explain this: {'; '.join(c.confounders)}")
            if c.assumptions:
                lines.append(f"  - assumes: {'; '.join(c.assumptions)}")
            if c.note:
                lines.append(f"  - note: {c.note}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_claims(claims: Sequence[Claim], path: Path, title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(claims_markdown(claims, title), encoding="utf-8", newline="\n")
    return path
