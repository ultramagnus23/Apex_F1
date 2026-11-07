"""Reference line, projection onto it, curvature and corner detection.

The reference line is the kernel-averaged path of several clean laps, so it is
a *mean driven line*, not the geometric track centreline. All distances in
Apex are arc length along this line, in metres, with s = 0 at the estimated
timing line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.signal import find_peaks, savgol_filter

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class ReferenceLine:
    """Closed reference line sampled every ``spacing`` metres of arc length."""

    s: FloatArray
    x: FloatArray
    y: FloatArray
    length: float
    spacing: float
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (len(self.s) == len(self.x) == len(self.y)):
            raise ValueError("s, x, y must have equal length")

    def curvature(self, window_m: float = 30.0) -> FloatArray:
        """Signed curvature κ(s) [1/m] via periodic Savitzky-Golay derivatives.

        Positive = turning left (counter-clockwise).
        """
        n = max(5, round(window_m / self.spacing) | 1)
        h = self.spacing
        dx = savgol_filter(self.x, n, 3, deriv=1, delta=h, mode="wrap")
        dy = savgol_filter(self.y, n, 3, deriv=1, delta=h, mode="wrap")
        ddx = savgol_filter(self.x, n, 3, deriv=2, delta=h, mode="wrap")
        ddy = savgol_filter(self.y, n, 3, deriv=2, delta=h, mode="wrap")
        k: FloatArray = (dx * ddy - dy * ddx) / np.power(dx * dx + dy * dy, 1.5)
        return k


def _arc_length(xy: FloatArray, closed: bool) -> FloatArray:
    d = np.hypot(*np.diff(xy, axis=0).T)
    if closed:
        d = np.r_[d, np.hypot(*(xy[0] - xy[-1]))]
    out: FloatArray = np.r_[0.0, np.cumsum(d)]
    return out


def project(
    points: FloatArray,
    line: ReferenceLine,
    s_guess: FloatArray | None = None,
    window_m: float = 250.0,
) -> tuple[FloatArray, FloatArray]:
    """Project XY points [m] onto the closed reference line.

    Returns (s, lateral distance). With ``s_guess`` the search is restricted to
    ±``window_m`` around the guess, which prevents snapping onto a different
    part of the circuit that happens to be nearby. Output s is in [0, length).
    """
    pts = np.asarray(points, dtype=np.float64)
    a = np.c_[line.x, line.y]
    b = np.roll(a, -1, axis=0)
    ab = b - a
    l2 = np.maximum((ab**2).sum(1), 1e-12)
    seg_len = np.sqrt(l2)
    s_out = np.empty(len(pts))
    lat_out = np.empty(len(pts))
    n_seg = len(a)
    if s_guess is not None and line.spacing <= 0:
        raise ValueError("windowed projection needs a uniformly spaced line")
    half = int(window_m / line.spacing) + 1 if s_guess is not None else 0
    for i, p in enumerate(pts):
        if s_guess is None:
            idx = np.arange(n_seg)
        else:
            c = round(float(s_guess[i] % line.length) / line.spacing)
            idx = np.arange(c - half, c + half + 1) % n_seg
        ap = p - a[idx]
        t = np.clip((ap * ab[idx]).sum(1) / l2[idx], 0.0, 1.0)
        q = a[idx] + t[:, None] * ab[idx]
        d = np.hypot(*(p - q).T)
        j = int(np.argmin(d))
        s_out[i] = (line.s[idx[j]] + t[j] * seg_len[idx[j]]) % line.length
        lat_out[i] = d[j]
    return s_out, lat_out


def _kernel_resample(
    s_pts: FloatArray, xy: FloatArray, length: float, spacing: float, sigma: float
) -> tuple[FloatArray, FloatArray]:
    grid = np.arange(0.0, length, spacing)
    # periodic padding
    s_all = np.r_[s_pts - length, s_pts, s_pts + length]
    xy_all = np.vstack([xy, xy, xy])
    order = np.argsort(s_all)
    s_all, xy_all = s_all[order], xy_all[order]
    out = np.empty((len(grid), 2))
    lo = np.searchsorted(s_all, grid - 4 * sigma)
    hi = np.searchsorted(s_all, grid + 4 * sigma)
    for k, g in enumerate(grid):
        ss = s_all[lo[k] : hi[k]]
        w = np.exp(-0.5 * ((ss - g) / sigma) ** 2)
        if w.sum() == 0:
            raise ValueError(f"no position samples near s={g:.0f} m; widen sigma")
        out[k] = (w[:, None] * xy_all[lo[k] : hi[k]]).sum(0) / w.sum()
    return grid.astype(np.float64), out.astype(np.float64)


def build_reference_line(
    laps_xy: list[FloatArray],
    origin_xy: FloatArray,
    *,
    spacing: float = 1.0,
    sigma: float = 6.0,
    iterations: int = 3,
) -> ReferenceLine:
    """Average several laps' position traces into a closed reference line.

    ``laps_xy``: per lap, an (N, 2) array of positions in metres, in time
    order, covering one lap. ``origin_xy``: the point that becomes s = 0
    (estimated timing line). ``sigma``: Gaussian kernel width along the line
    in metres. Each iteration re-projects every point onto the current line
    and re-averages; the result is re-parameterised by its own arc length.
    """
    if len(laps_xy) < 1:
        raise ValueError("need at least one lap")
    first = laps_xy[0]
    cum = _arc_length(first, closed=True)
    line = ReferenceLine(cum[:-1], first[:, 0].copy(), first[:, 1].copy(), float(cum[-1]), 0.0)
    # The seed polyline is irregular; give project() a uniform-looking spacing
    # attribute only for windowed search, which we do not use on the seed.
    pts = np.vstack(laps_xy)
    for _ in range(iterations):
        s_pts, _ = project(pts, line)
        _, xy = _kernel_resample(s_pts, pts, line.length, spacing, sigma)
        cum = _arc_length(xy, closed=True)
        length = float(cum[-1])
        # Re-parameterise by arc length on an exactly uniform *closed* grid
        # (n points, step length/n), so periodic filters see no short closing
        # segment at the line.
        n = max(4, round(length / spacing))
        step = length / n
        grid = (np.arange(n) * step).astype(np.float64)
        x = np.interp(grid, cum, np.r_[xy[:, 0], xy[0, 0]])
        y = np.interp(grid, cum, np.r_[xy[:, 1], xy[0, 1]])
        line = ReferenceLine(grid, x, y, length, step)

    # shift origin to the projection of origin_xy
    s0, _ = project(np.atleast_2d(origin_xy), line)
    shift = round(float(s0[0]) / line.spacing)
    x, y = np.roll(line.x, -shift), np.roll(line.y, -shift)
    params = {
        "method": "gaussian-kernel mean of laps",
        "sigma_m": sigma,
        "spacing_m": spacing,
        "iterations": iterations,
        "n_laps": len(laps_xy),
    }
    return ReferenceLine(line.s, x, y, line.length, line.spacing, params)


# ---------------------------------------------------------------------------
# Corners


@dataclass(frozen=True)
class Corner:
    number: int
    label: str
    s_apex: float  # location of reference minimum speed (or curvature peak if flat)
    s_start: float  # segment boundaries used for corner-based deltas
    s_end: float
    v_min_kmh: float
    curvature_peak: float
    direction: str  # "L" or "R"
    kind: str  # "braking" (speed minimum) or "flat" (curvature only)


@dataclass(frozen=True)
class CornerConfig:
    # Tuned on 2026 Austin: 40-80 m windows with R<=150 m give a stable
    # 16-18 peak set; narrower windows produce spurious kinks on straights.
    # kappa passed to detect_corners should use curvature_window_m.
    min_speed_prominence_kmh: float = 15.0
    min_curvature: float = 1 / 150.0  # 1/m, i.e. radius <= 150 m
    curvature_window_m: float = 60.0
    min_separation_m: float = 80.0
    match_window_m: float = 80.0
    include_flat: bool = True


def detect_corners(
    s: FloatArray,
    v_ref_kmh: FloatArray,
    kappa: FloatArray,
    length: float,
    cfg: CornerConfig | None = None,
) -> list[Corner]:
    """Corners from speed minima and curvature peaks together.

    A *braking* corner is a reference-speed minimum with prominence
    ≥ ``min_speed_prominence_kmh`` that has a curvature peak above
    ``min_curvature`` within ``match_window_m``. A *flat* corner is a curvature
    peak with no qualifying speed minimum (optional). Segment boundaries are
    midpoints between consecutive apexes (wrapping at the line).
    """
    cfg = cfg or CornerConfig()
    ds = float(s[1] - s[0])
    absk = np.abs(kappa)
    kpk, _ = find_peaks(
        absk,
        height=cfg.min_curvature,
        distance=max(1, int(cfg.min_separation_m / ds)),
        prominence=cfg.min_curvature / 2,
    )
    vmin, _ = find_peaks(
        -v_ref_kmh, prominence=cfg.min_speed_prominence_kmh, distance=max(1, int(60 / ds))
    )
    win = cfg.match_window_m / ds
    used_k: set[int] = set()
    raw: list[tuple[float, float, float, str]] = []  # s_apex, vmin, kpeak, kind
    for i in vmin:
        near = [k for k in kpk if abs(k - i) <= win]
        if not near:
            continue
        k = max(near, key=lambda kk: absk[kk])
        used_k.update(near)
        raw.append((float(s[i]), float(v_ref_kmh[i]), float(kappa[k]), "braking"))
    if cfg.include_flat:
        for k in kpk:
            if k not in used_k:
                raw.append((float(s[k]), float(v_ref_kmh[k]), float(kappa[k]), "flat"))
    raw.sort()
    corners: list[Corner] = []
    n = len(raw)
    for j, (sa, vm, kp, kind) in enumerate(raw):
        prev_s = raw[j - 1][0] - (length if j == 0 else 0.0)
        next_s = raw[(j + 1) % n][0] + (length if j == n - 1 else 0.0)
        corners.append(
            Corner(
                number=j + 1,
                label=f"C{j + 1}",
                s_apex=sa,
                s_start=max(0.0, (prev_s + sa) / 2),
                s_end=min(length, (sa + next_s) / 2),
                v_min_kmh=vm,
                curvature_peak=kp,
                direction="L" if kp > 0 else "R",
                kind=kind,
            )
        )
    if corners:
        # first/last segments extend to the line
        c0, cl = corners[0], corners[-1]
        corners[0] = Corner(**{**c0.__dict__, "s_start": 0.0})
        corners[-1] = Corner(**{**cl.__dict__, "s_end": length})
    return corners


def apply_numbering_override(corners: list[Corner], path: Path) -> tuple[list[Corner], list[str]]:
    """Relabel detected corners from a per-circuit TOML file.

    File format::

        [[turn]]
        official = "T1"
        s = 640.0          # metres from the line along the reference line
        tolerance_m = 60   # optional

    A detected corner gets an official label only if exactly one override
    turn lies within tolerance; everything else keeps its ``C<n>`` label and
    the mismatch is reported.
    """
    import tomllib

    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    notes: list[str] = []
    out: list[Corner] = []
    for c in corners:
        hits = [
            t
            for t in spec.get("turn", [])
            if abs(float(t["s"]) - c.s_apex) <= float(t.get("tolerance_m", 60.0))
        ]
        if len(hits) == 1:
            out.append(Corner(**{**c.__dict__, "label": str(hits[0]["official"])}))
        else:
            out.append(c)
            notes.append(f"{c.label} at {c.s_apex:.0f} m matched {len(hits)} override turns")
    return out, notes


def reference_from_laps(
    tels: list[Any], *, spacing: float = 1.0, sigma: float = 6.0
) -> ReferenceLine:
    """Reference line from extracted laps (``LapTelemetry``), origin at date_start.

    The origin is the median position at each lap's ``date_start`` instant,
    so it inherits that field's ±~0.1 s (≈8 m) scatter as a *common* offset;
    deltas between laps are insensitive to it, absolute positions are not.
    """
    laps_xy: list[FloatArray] = []
    origins = []
    for tel in tels:
        p = tel.pos
        inside = (p["t"] >= 0) & (p["t"] <= tel.lap.lap_duration)
        laps_xy.append(p.loc[inside, ["x", "y"]].to_numpy(dtype=np.float64))
        origins.append([np.interp(0.0, p["t"], p["x"]), np.interp(0.0, p["t"], p["y"])])
    origin = np.median(np.asarray(origins), axis=0)
    line = build_reference_line(laps_xy, origin, spacing=spacing, sigma=sigma)
    params = {
        **line.params,
        "origin": "median position at date_start",
        "laps": [t.lap.key for t in tels],
    }
    return ReferenceLine(line.s, line.x, line.y, line.length, line.spacing, params)
