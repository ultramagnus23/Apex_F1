"""Check that regenerated outputs match the committed ones, tolerant of float noise.

Usage: python scripts/check_regenerated.py DIR [--exclude GLOB ...]

Compares the working-tree files under DIR with their committed (HEAD) versions.
Everything that is not a number must match exactly; numbers must agree to a
relative tolerance of 1e-6 (absolute 1e-9). This keeps the "outputs are
reproducible" guarantee while not failing on last-digit floating-point differences
between CPUs / BLAS builds (a local run and a GitHub runner differ at ~1e-13).
"""

from __future__ import annotations

import argparse
import fnmatch
import math
import re
import subprocess
import sys
from pathlib import Path

NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
RTOL, ATOL = 1e-6, 1e-9


def committed(path: str) -> str | None:
    r = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def compare(old: str, new: str) -> str | None:
    if NUM.sub("#", old) != NUM.sub("#", new):
        return "non-numeric content differs"
    for a, b in zip(NUM.findall(old), NUM.findall(new), strict=True):
        x, y = float(a), float(b)
        if not math.isclose(x, y, rel_tol=RTOL, abs_tol=ATOL):
            return f"number differs beyond tolerance: {a} vs {b}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--exclude", action="append", default=[])
    args = ap.parse_args()
    bad = 0
    for p in sorted(Path(args.dir).rglob("*")):
        if not p.is_file() or any(fnmatch.fnmatch(p.name, g) for g in args.exclude):
            continue
        rel = p.as_posix()
        old = committed(rel)
        if old is None:
            print(f"NEW (not committed): {rel}")
            bad += 1
            continue
        why = compare(old, p.read_text(encoding="utf-8"))
        if why:
            print(f"DIFF {rel}: {why}")
            bad += 1
    print("regenerated outputs match committed outputs" if not bad else f"{bad} file(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
