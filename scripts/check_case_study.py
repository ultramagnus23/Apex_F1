"""Regenerate case study 01 into a temp directory and compare with the committed copy.

Numbers are compared with a tolerance (1e-9 relative), because the same arithmetic
differs in the last few bits between operating systems and BLAS builds. Text is
compared exactly. Exit status 1 on any difference.

    uv run python scripts/check_case_study.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
COMMITTED = ROOT / "docs" / "case_study_01"
RTOL = 1e-9
ATOL = 1e-12


def _close(a: Any, b: Any, where: str, errors: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            errors.append(f"{where}: keys differ")
            return
        for k in a:
            _close(a[k], b[k], f"{where}.{k}", errors)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            errors.append(f"{where}: length {len(a)} != {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _close(x, y, f"{where}[{i}]", errors)
    elif isinstance(a, float | int) and isinstance(b, float | int) and not isinstance(a, bool):
        if not np.isclose(float(a), float(b), rtol=RTOL, atol=ATOL):
            errors.append(f"{where}: {a!r} != {b!r}")
    elif a != b:
        errors.append(f"{where}: {a!r} != {b!r}")


def compare_csv(new: Path, old: Path, errors: list[str]) -> None:
    a = pd.read_csv(new)
    b = pd.read_csv(old)
    if set(a.columns) != set(b.columns):
        errors.append(f"{old.name}: columns differ")
        return
    b = b[a.columns]  # column order is not a result
    if a.shape != b.shape:
        errors.append(f"{old.name}: shape {a.shape} != {b.shape}")
        return
    for col in a.columns:
        if pd.api.types.is_numeric_dtype(a[col]):
            x, y = a[col].to_numpy(float), b[col].to_numpy(float)
            bad = ~np.isclose(x, y, rtol=RTOL, atol=ATOL, equal_nan=True)
            for i in np.flatnonzero(bad)[:5]:
                errors.append(f"{old.name}[{i}].{col}: {x[i]!r} != {y[i]!r}")
        elif not a[col].astype(str).equals(b[col].astype(str)):
            errors.append(f"{old.name}: text column {col} differs")


def main() -> int:
    from examples.case_study_01 import main as regenerate

    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "case_study_01"
        regenerate(out)
        for new in sorted(out.iterdir()):
            old = COMMITTED / new.name
            if new.suffix == ".png":
                continue  # pixel output depends on the font stack; reviewed by eye
            if not old.exists():
                errors.append(f"{new.name}: not committed")
                continue
            if new.suffix == ".csv":
                compare_csv(new, old, errors)
            elif new.suffix == ".json":
                _close(json.loads(new.read_text()), json.loads(old.read_text()), new.name, errors)
            else:
                if new.read_text(encoding="utf-8") != old.read_text(encoding="utf-8"):
                    errors.append(f"{new.name}: text differs")
    if errors:
        print("case study does not reproduce:")
        for e in errors[:50]:
            print("  " + e)
        return 1
    print("case study reproduces (numbers within 1e-9, text exact)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
