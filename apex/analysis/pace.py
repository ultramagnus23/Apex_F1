"""Race-pace inference: fuel-, tyre- and stint-adjusted driver pace with posteriors.

Lap time is modelled as a linear Bayesian regression::

    y = pace[driver] + stint[driver, stint] + compound[c] + gamma * (lap - L_ref)
        + delta[c] * tyre_age + noise

* ``pace``   one value per driver (the quantity of interest): lap time on the
             reference compound, with a fresh tyre, at the reference lap number.
* ``stint``  a shrunk (random) effect per driver stint. It absorbs what a stint
             shares across its laps (fuel mode, setup change, traffic regime) so
             that the driver comparison is not driven by one stint.
* ``gamma``  the net lap-number trend. Fuel burn and track evolution both move with
             lap number and are **not separable** in public data. It is reported as
             one number, never as "fuel effect".
* ``delta``  tyre degradation per lap of tyre age, one per compound.

The posterior is the conjugate Normal-Inverse-Gamma, so it is exact (no sampler).
The stint-effect scale is chosen by maximising the marginal likelihood.
Everything reported is a posterior summary, not a point estimate.

Selection caveat: the model only sees laps classified as clean (no pit, flag, start
or outlier laps). It estimates pace when unimpeded, which can differ from race pace
in traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from apex.core.laps import flag_intervals
from apex.core.session import SessionData, parse_utc

WET_COMPOUNDS = ("INTERMEDIATE", "WET")
REASONS = ("NO_TIME", "START", "PIT_OUT", "PIT_IN", "FLAG", "OUTLIER")


@dataclass(frozen=True)
class PaceConfig:
    """Settings for lap filtering and the Bayesian model."""

    outlier_k: float = 4.0  # robust-sigma multiples against the stint's rolling median
    outlier_floor_s: float = 0.4  # never flag a lap closer than this to the median
    min_clean_laps: int = 12  # drivers with fewer clean laps are not estimated
    stint_scale_grid: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0)  # in units of sigma
    driver_prior_scale: float = 20.0  # in units of sigma (effectively flat)
    compound_prior_scale: float = 20.0
    trend_prior_scale: float = 0.5  # s/lap, in units of sigma
    deg_prior_scale: float = 0.5  # s per lap of age, in units of sigma
    a0: float = 1.0  # inverse-gamma prior on the noise variance (weak)
    b0: float = 0.05
    ci: float = 0.90
    max_wet_share: float = 0.10  # above this the result is NOT MODELLED
    max_sigma_s: float = 1.5
    min_total_clean: int = 200
    pace_ref_lap: int | None = None  # default: middle of the race
    quadratic_trend: bool = False  # add a curvature term to the lap-number trend


# --------------------------------------------------------------------------- laps


def race_lap_table(session: SessionData, cfg: PaceConfig | None = None) -> pd.DataFrame:
    """One row per lap with ``clean`` and a ``reason`` for every exclusion.

    Columns: driver_number, lap_number, stint_number, compound, tyre_age,
    lap_duration, clean, reason.
    """
    cfg = cfg or PaceConfig()
    laps = session.laps.copy()
    laps = laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    dur = pd.to_numeric(laps["lap_duration"], errors="coerce")
    laps["lap_duration"] = dur
    t0 = laps["t0"]
    t1 = t0 + pd.to_timedelta(dur.fillna(0.0), unit="s")

    reason = pd.Series("", index=laps.index, dtype=object)

    def mark(mask: pd.Series, name: str) -> None:
        m = mask.fillna(False) & (reason == "")
        reason.loc[m] = name

    mark(dur.isna(), "NO_TIME")
    mark(laps["lap_number"] == 1, "START")
    mark(laps["is_pit_out_lap"].astype(bool), "PIT_OUT")
    if not session.pit.empty:
        pit_in = {
            (int(d), int(n))
            for d, n in zip(session.pit["driver_number"], session.pit["lap_number"], strict=True)
        }
        keys = list(
            zip(laps["driver_number"].astype(int), laps["lap_number"].astype(int), strict=True)
        )
        mark(pd.Series([k in pit_in for k in keys], index=laps.index), "PIT_IN")

    if not session.race_control.empty and t1.notna().any():
        end = t1.max()
        flagged = pd.Series(False, index=laps.index)
        for a, b, _ in flag_intervals(session, end_of_data=end):
            flagged |= (t0 < b) & (t1 > a)
        mark(flagged, "FLAG")

    st = session.stints
    laps["stint_number"] = np.nan
    laps["compound"] = "UNKNOWN"
    laps["tyre_age"] = np.nan
    if not st.empty:
        last = int(laps["lap_number"].max())
        for r in st.itertuples():
            lo = int(r.lap_start) if pd.notna(r.lap_start) else 1
            hi = int(r.lap_end) if pd.notna(r.lap_end) else last
            m = (laps["driver_number"] == r.driver_number) & laps["lap_number"].between(lo, hi)
            laps.loc[m, "stint_number"] = r.stint_number
            laps.loc[m, "compound"] = str(r.compound or "UNKNOWN").upper()
            age0 = float(r.tyre_age_at_start) if pd.notna(r.tyre_age_at_start) else 0.0
            laps.loc[m, "tyre_age"] = age0 + (laps.loc[m, "lap_number"] - lo)
    no_stint = laps["stint_number"].isna()
    laps.loc[no_stint, "stint_number"] = 1
    laps.loc[laps["tyre_age"].isna(), "tyre_age"] = (laps["lap_number"] - 1).astype(float)

    laps["reason"] = reason
    laps = _flag_outliers(laps, cfg)
    laps["clean"] = laps["reason"] == ""
    cols = [
        "driver_number",
        "lap_number",
        "stint_number",
        "compound",
        "tyre_age",
        "lap_duration",
        "clean",
        "reason",
    ]
    return laps[cols].reset_index(drop=True)


def _flag_outliers(laps: pd.DataFrame, cfg: PaceConfig) -> pd.DataFrame:
    """Mark laps far from the stint's rolling median (traffic, errors, lock-ups)."""
    laps = laps.copy()
    ok = laps["reason"] == ""
    for _, g in laps[ok].groupby(["driver_number", "stint_number"], sort=False):
        y = g["lap_duration"]
        med = y.rolling(7, center=True, min_periods=3).median()
        r = y - med
        if r.notna().sum() < 3:
            continue
        sigma = max(1.4826 * float(np.nanmedian(np.abs(r))), 1e-6)
        bad = r.abs() > max(cfg.outlier_k * sigma, cfg.outlier_floor_s)
        laps.loc[bad[bad].index, "reason"] = "OUTLIER"
    return laps


# -------------------------------------------------------------------------- model


@dataclass(frozen=True)
class _Design:
    X: np.ndarray
    names: list[str]
    prior_scale: np.ndarray  # in sigma units; stint entries are filled in at fit time
    stint_cols: np.ndarray
    driver_cols: dict[int, int]
    compound_cols: dict[str, int]
    trend_col: int
    trend2_col: int | None
    deg_cols: dict[str, int]
    ref_compound: str
    ref_lap: int
    y_center: float


def _design(table: pd.DataFrame, cfg: PaceConfig) -> _Design:
    drivers = sorted(int(d) for d in table["driver_number"].unique())
    stints = sorted(
        {
            (int(d), int(s))
            for d, s in zip(table["driver_number"], table["stint_number"], strict=True)
        }
    )
    comp_counts = table["compound"].value_counts()
    ref_compound = str(comp_counts.index[0])
    compounds = [str(c) for c in comp_counts.index]
    ref_lap = cfg.pace_ref_lap or round(table["lap_number"].max() / 2)

    names: list[str] = []
    scales: list[float] = []
    driver_cols: dict[int, int] = {}
    for d in drivers:
        driver_cols[d] = len(names)
        names.append(f"pace:{d}")
        scales.append(cfg.driver_prior_scale)
    stint_cols = []
    stint_idx: dict[tuple[int, int], int] = {}
    for key in stints:
        stint_idx[key] = len(names)
        stint_cols.append(len(names))
        names.append(f"stint:{key[0]}:{key[1]}")
        scales.append(np.nan)
    compound_cols: dict[str, int] = {}
    for c in compounds:
        if c == ref_compound:
            continue
        compound_cols[c] = len(names)
        names.append(f"compound:{c}")
        scales.append(cfg.compound_prior_scale)
    trend_col = len(names)
    names.append("trend")
    scales.append(cfg.trend_prior_scale)
    trend2_col: int | None = None
    if cfg.quadratic_trend:
        trend2_col = len(names)
        names.append("trend2")
        scales.append(cfg.trend_prior_scale)
    deg_cols: dict[str, int] = {}
    for c in compounds:
        deg_cols[c] = len(names)
        names.append(f"deg:{c}")
        scales.append(cfg.deg_prior_scale)

    n = len(table)
    X = np.zeros((n, len(names)))
    drv = table["driver_number"].to_numpy(int)
    stn = table["stint_number"].to_numpy(int)
    cmp_ = table["compound"].astype(str).to_numpy()
    lap = table["lap_number"].to_numpy(float)
    age = table["tyre_age"].to_numpy(float)
    for i in range(n):
        X[i, driver_cols[int(drv[i])]] = 1.0
        X[i, stint_idx[(int(drv[i]), int(stn[i]))]] = 1.0
        if cmp_[i] in compound_cols:
            X[i, compound_cols[cmp_[i]]] = 1.0
        X[i, trend_col] = lap[i] - ref_lap
        if trend2_col is not None:
            X[i, trend2_col] = (lap[i] - ref_lap) ** 2 / 100.0
        X[i, deg_cols[cmp_[i]]] = age[i]
    y = table["lap_duration"].to_numpy(float)
    return _Design(
        X=X,
        names=names,
        prior_scale=np.array(scales),
        stint_cols=np.array(stint_cols, dtype=int),
        driver_cols=driver_cols,
        compound_cols=compound_cols,
        trend_col=trend_col,
        trend2_col=trend2_col,
        deg_cols=deg_cols,
        ref_compound=ref_compound,
        ref_lap=ref_lap,
        y_center=float(np.median(y)),
    )


@dataclass(frozen=True)
class _Posterior:
    mean: np.ndarray
    chol_prec: np.ndarray  # lower Cholesky factor of the posterior precision
    a: float
    b: float
    stint_scale: float
    log_marginal: float


def _posterior(
    X: np.ndarray,
    y: np.ndarray,
    prior_scale: np.ndarray,
    stint_cols: np.ndarray,
    tau: float,
    cfg: PaceConfig,
) -> _Posterior:
    scale = prior_scale.copy()
    scale[stint_cols] = tau
    prec0 = np.diag(1.0 / scale**2)
    prec = X.T @ X + prec0
    chol = np.linalg.cholesky(prec)
    xty = X.T @ y
    mean = np.linalg.solve(prec, xty)
    a = cfg.a0 + len(y) / 2.0
    b = cfg.b0 + 0.5 * float(y @ y - mean @ xty)
    b = max(b, 1e-9)
    logdet_prec = 2.0 * float(np.log(np.diag(chol)).sum())
    logdet_prior = float(np.log(scale**2).sum())
    log_ml = -0.5 * logdet_prec - 0.5 * logdet_prior - a * np.log(b)
    return _Posterior(mean, chol, a, b, tau, log_ml)


def _fit_rows(d: _Design, y: np.ndarray, rows: np.ndarray, cfg: PaceConfig) -> _Posterior:
    best: _Posterior | None = None
    for tau in cfg.stint_scale_grid:
        p = _posterior(d.X[rows], y[rows] - d.y_center, d.prior_scale, d.stint_cols, tau, cfg)
        if best is None or p.log_marginal > best.log_marginal:
            best = p
    assert best is not None
    return best


def _draws(p: _Posterior, n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Joint posterior draws of (beta, sigma)."""
    sigma2 = p.b / rng.gamma(p.a, size=n)
    z = rng.standard_normal((n, len(p.mean)))
    # beta = mean + sigma * L^{-T} z  where prec = L L^T
    delta = np.linalg.solve(p.chol_prec.T, z.T).T
    return p.mean + np.sqrt(sigma2)[:, None] * delta, np.sqrt(sigma2)


# ------------------------------------------------------------------------- result


@dataclass(frozen=True)
class DriverPace:
    driver_number: int
    code: str
    mean_s: float
    lo_s: float
    hi_s: float
    n_laps: int
    rank_mean: float


@dataclass(frozen=True)
class PaceResult:
    session_key: int
    ref_compound: str
    ref_lap: int
    ci: float
    drivers: pd.DataFrame
    params: pd.DataFrame
    prob_faster: pd.DataFrame  # [row, col] = P(row driver's pace is faster than col driver's)
    sigma_s: float
    stint_sd_s: float
    n_clean: int
    exclusions: dict[str, int] = field(default_factory=dict)
    status: str = "OK"
    status_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "reference": {"compound": self.ref_compound, "lap": self.ref_lap, "tyre_age": 0},
            "credible_interval": self.ci,
            "noise_sigma_s": self.sigma_s,
            "stint_effect_sd_s": self.stint_sd_s,
            "status": self.status,
            "status_reasons": list(self.status_reasons),
            "clean_laps": self.n_clean,
            "exclusions": self.exclusions,
            "drivers": self.drivers.to_dict("records"),
            "parameters": self.params.to_dict("records"),
            "prob_faster": {
                "drivers": [str(c) for c in self.prob_faster.columns],
                "matrix": np.round(self.prob_faster.to_numpy(), 4).tolist(),
            },
        }


def fit_pace(
    table: pd.DataFrame,
    codes: dict[int, str] | None = None,
    cfg: PaceConfig | None = None,
    *,
    session_key: int = 0,
    n_draws: int = 2000,
    seed: int = 0,
) -> PaceResult:
    """Fit the model on clean laps and summarise driver pace and parameters."""
    cfg = cfg or PaceConfig()
    codes = codes or {}
    excl = {r: int((table["reason"] == r).sum()) for r in REASONS}
    clean = table[table["clean"]].copy()
    counts = clean.groupby("driver_number").size()
    keep = counts[counts >= cfg.min_clean_laps].index
    clean = clean[clean["driver_number"].isin(keep)].reset_index(drop=True)
    if clean.empty:
        raise ValueError("no driver has enough clean laps")

    d = _design(clean, cfg)
    y = clean["lap_duration"].to_numpy(float)
    rows = np.arange(len(clean))
    post = _fit_rows(d, y, rows, cfg)
    rng = np.random.default_rng(seed)
    beta, sigma = _draws(post, n_draws, rng)

    lo_q, hi_q = (1 - cfg.ci) / 2, 1 - (1 - cfg.ci) / 2
    drivers = sorted(d.driver_cols)
    pace = np.column_stack([beta[:, d.driver_cols[k]] for k in drivers]) + d.y_center
    ranks = pace.argsort(axis=1).argsort(axis=1) + 1
    rows_out = []
    for j, k in enumerate(drivers):
        rows_out.append(
            DriverPace(
                k,
                codes.get(k, str(k)),
                float(pace[:, j].mean()),
                float(np.quantile(pace[:, j], lo_q)),
                float(np.quantile(pace[:, j], hi_q)),
                int(counts[k]),
                float(ranks[:, j].mean()),
            )
        )
    drv_df = (
        pd.DataFrame([r.__dict__ for r in rows_out]).sort_values("mean_s").reset_index(drop=True)
    )

    labels = [codes.get(k, str(k)) for k in drivers]
    pf = np.array(
        [
            [
                float((pace[:, i] < pace[:, j]).mean()) if i != j else 0.5
                for j in range(len(drivers))
            ]
            for i in range(len(drivers))
        ]
    )
    order = [labels.index(c) for c in drv_df["code"]]
    prob = pd.DataFrame(pf[np.ix_(order, order)], index=drv_df["code"], columns=drv_df["code"])

    params = []

    def add(name: str, unit: str, col: int, note: str) -> None:
        s = beta[:, col]
        params.append(
            {
                "name": name,
                "unit": unit,
                "mean": float(s.mean()),
                "lo": float(np.quantile(s, lo_q)),
                "hi": float(np.quantile(s, hi_q)),
                "note": note,
            }
        )

    add("lap-number trend", "s/lap", d.trend_col, "fuel burn plus track evolution, not separable")
    for c, col in d.deg_cols.items():
        add(f"degradation {c}", "s per lap of tyre age", col, "positive = slower with age")
    for c, col in d.compound_cols.items():
        add(f"offset {c} vs {d.ref_compound}", "s", col, "at tyre age 0")
    stint_sd = float(post.stint_scale * np.median(sigma))
    sigma_med = float(np.median(sigma))
    reasons = []
    wet = float(clean["compound"].isin(WET_COMPOUNDS).mean())
    if wet > cfg.max_wet_share:
        reasons.append(
            f"{wet:.0%} of clean laps on wet-weather tyres; the tyre model assumes dry running"
        )
    if sigma_med > cfg.max_sigma_s:
        reasons.append(f"lap-time noise {sigma_med:.1f} s exceeds {cfg.max_sigma_s:.1f} s")
    if len(clean) < cfg.min_total_clean:
        reasons.append(f"only {len(clean)} clean laps")
    return PaceResult(
        session_key=session_key,
        ref_compound=d.ref_compound,
        ref_lap=d.ref_lap,
        ci=cfg.ci,
        drivers=drv_df,
        params=pd.DataFrame(params),
        prob_faster=prob,
        sigma_s=sigma_med,
        stint_sd_s=stint_sd,
        n_clean=len(clean),
        exclusions=excl,
        status="NOT MODELLED" if reasons else "OK",
        status_reasons=tuple(reasons),
    )


# ---------------------------------------------------------------------- validation


@dataclass(frozen=True)
class CvResult:
    scheme: str
    n_test: int
    coverage: float
    nominal: float
    mae_s: float
    mean_width_s: float


def cross_validate(
    table: pd.DataFrame,
    cfg: PaceConfig | None = None,
    *,
    scheme: str = "random",
    frac: float = 0.2,
    n_draws: int = 400,
    seed: int = 0,
) -> CvResult:
    """Held-out predictive check of the posterior.

    ``random``   hold out a random fraction of clean laps (interpolation).
    ``stint``    hold out whole stints (the stint effect is then unseen, so this tests
                 whether stint-to-stint variation is properly in the intervals).
    ``forward``  fit on the first (1 - frac) of the race, predict the rest
                 (extrapolation: later laps, mostly unseen stints).

    Reports the share of held-out laps inside the central predictive interval. A
    well-calibrated model covers close to the nominal level.
    """
    cfg = cfg or PaceConfig()
    clean = table[table["clean"]]
    counts = clean.groupby("driver_number").size()
    clean = clean[clean["driver_number"].isin(counts[counts >= cfg.min_clean_laps].index)]
    clean = clean.reset_index(drop=True)
    d = _design(clean, cfg)
    y = clean["lap_duration"].to_numpy(float)
    n = len(y)
    rng = np.random.default_rng(seed)
    if scheme == "random":
        test = rng.random(n) < frac
    elif scheme == "stint":
        keys = (
            clean["driver_number"].astype(str) + ":" + clean["stint_number"].astype(int).astype(str)
        )
        uniq = keys.unique()
        held = set(rng.choice(uniq, size=max(1, round(frac * len(uniq))), replace=False))
        test = keys.isin(held).to_numpy()
    elif scheme == "forward":
        cut = clean["lap_number"].quantile(1 - frac)
        test = (clean["lap_number"] > cut).to_numpy()
    else:
        raise ValueError(f"unknown scheme {scheme!r}")
    train = np.where(~test)[0]
    test_idx = np.where(test)[0]
    post = _fit_rows(d, y, train, cfg)
    beta, sigma = _draws(post, n_draws, rng)
    mu = beta @ d.X[test_idx].T + d.y_center  # draws x test
    pred = mu + sigma[:, None] * rng.standard_normal(mu.shape)
    lo_q, hi_q = (1 - cfg.ci) / 2, 1 - (1 - cfg.ci) / 2
    lo = np.quantile(pred, lo_q, axis=0)
    hi = np.quantile(pred, hi_q, axis=0)
    yt = y[test_idx]
    return CvResult(
        scheme=scheme,
        n_test=len(test_idx),
        coverage=float(((yt >= lo) & (yt <= hi)).mean()),
        nominal=cfg.ci,
        mae_s=float(np.abs(yt - np.median(pred, axis=0)).mean()),
        mean_width_s=float((hi - lo).mean()),
    )


def codes_for(session: SessionData) -> dict[int, str]:
    return {int(r.driver_number): str(r.name_acronym) for r in session.drivers.itertuples()}


__all__ = [
    "CvResult",
    "PaceConfig",
    "PaceResult",
    "codes_for",
    "cross_validate",
    "fit_pace",
    "parse_utc",
    "race_lap_table",
]
