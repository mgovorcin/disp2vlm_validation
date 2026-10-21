# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Validation metrics: velocity statistics and the double-difference sill.

Double differences (``geepers.validation``): for every station pair, the
InSAR-minus-GNSS misfit of the relative LOS series (B - A) is reduced to an
RMSE about its mean; ``gamma = rmse**2 / 2`` is the misfit semivariance.
Double differences cancel the datum, so raw and calibrated are directly
comparable; calibration removes long-wavelength error, so the sill (median
gamma of pairs at least `sill_min_km` apart) must drop.

The sill confidence interval is a station bootstrap: stations are resampled
with replacement, each pair weighted by the product of its stations' counts,
and the weighted median recomputed. All variants share the same resamples, so
their differences are paired. Ported from the trade study (plan T21.1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = [
    "DDResult",
    "SillResult",
    "bias_rise_ci",
    "bootstrap_sills",
    "ci95",
    "double_differences",
    "velocity_stats",
    "weighted_median",
]


def velocity_stats(insar: np.ndarray, gps: np.ndarray) -> dict[str, float]:
    """Residual statistics of InSAR - GNSS (same units as the inputs)."""
    insar = np.asarray(insar, float)
    gps = np.asarray(gps, float)
    ok = np.isfinite(insar) & np.isfinite(gps)
    res = insar[ok] - gps[ok]
    n = int(ok.sum())
    if n < 2:
        return {"n": n}
    return {
        "n": n,
        "bias": float(np.mean(res)),
        "median": float(np.median(res)),
        "rmse": float(np.sqrt(np.mean(res**2))),
        "std": float(np.std(res, ddof=1)),
        "nmad": float(1.4826 * np.median(np.abs(res - np.median(res)))),
        "r2": float(np.corrcoef(gps[ok], insar[ok])[0, 1] ** 2),
    }


def bias_rise_ci(
    candidate: np.ndarray,
    baseline: np.ndarray,
    statistic: str = "median",
    *,
    ci: float = 0.95,
    n_boot: int = 4000,
    seed: int = 0,
) -> tuple[float, float]:
    """Paired station-bootstrap interval of ``|bias(candidate)| - |bias(baseline)|``.

    `candidate` and `baseline` are the residuals (InSAR - GNSS) of the same
    stations; resampling stations jointly keeps the pairing, so the interval
    is that of the change, not of either bias (decision 0004).
    """
    c = np.asarray(candidate, dtype=float)
    b = np.asarray(baseline, dtype=float)
    if c.shape != b.shape:
        msg = f"candidate {c.shape} and baseline {b.shape} must be paired"
        raise ValueError(msg)
    ok = np.isfinite(c) & np.isfinite(b)
    c, b = c[ok], b[ok]
    if c.size < 3:
        return (float("nan"), float("nan"))
    stat = np.median if statistic == "median" else np.mean
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, c.size, size=(n_boot, c.size))
    d = np.abs(stat(c[idx], axis=1)) - np.abs(stat(b[idx], axis=1))
    lo, hi = np.percentile(d, [50 * (1 - ci), 50 * (1 + ci)])
    return float(lo), float(hi)


def weighted_median(x: np.ndarray, w: np.ndarray) -> float:
    """Weighted median (lower); NaN when no weight is positive."""
    keep = w > 0
    x, w = x[keep], w[keep]
    if x.size == 0:
        return float("nan")
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    return float(x[o][np.searchsorted(cw, 0.5 * cw[-1])])


def ci95(x: np.ndarray) -> tuple[float, float]:
    """2.5 and 97.5 percentiles."""
    return float(np.nanpercentile(x, 2.5)), float(np.nanpercentile(x, 97.5))


@dataclass
class SillResult:
    """Sill of one variant with its station-bootstrap 95% interval."""

    sill: float
    ci_lo: float
    ci_hi: float
    n_pairs: int
    n_stations: int
    near_gamma: float
    median_pair_rmse: float
    draws: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))


@dataclass
class DDResult:
    """Double-difference results of several variants on common station-dates."""

    pairs: dict[str, pd.DataFrame]
    semivariograms: dict[str, pd.DataFrame]
    sills: dict[str, SillResult]
    sill_min_km: float

    def change_pct(self, a: str, b: str) -> tuple[float, tuple[float, float]]:
        """Sill change of `a` relative to `b` in %, with its paired 95% CI."""
        d = 100.0 * (self.sills[a].sill / self.sills[b].sill - 1.0)
        draws_a, draws_b = self.sills[a].draws, self.sills[b].draws
        if draws_a.size and draws_b.size:
            return d, ci95(100.0 * (draws_a / draws_b - 1.0))
        return d, (float("nan"), float("nan"))


def double_differences(
    insar: Mapping[str, pd.DataFrame],
    gps: pd.DataFrame,
    coords: Mapping[str, tuple[float, float]],
    *,
    min_common_dates: int = 30,
    sill_min_km: float = 50.0,
    near_max_km: float = 10.0,
    n_bins: int = 12,
    n_boot: int = 1000,
    seed: int = 0,
) -> DDResult:
    """Pairwise DD RMSE, semivariograms and bootstrap sills per variant.

    Parameters
    ----------
    insar : mapping of name -> DataFrame
        dates x stations InSAR LOS series (mm) per variant (raw, calibrated,
        baseline...).
    gps : DataFrame
        dates x stations GNSS LOS series (mm).
    coords : mapping
        station -> (lon, lat).

    Only station-dates valid in every variant and in GNSS are used, so the
    variants are compared on the same data.

    """
    from geepers.validation import misfit_semivariogram, pairwise_differential_rmse

    valid = gps.notna()
    for df in insar.values():
        valid &= df.notna()
    pairs, svs = {}, {}
    for name, df in insar.items():
        merged = {
            s: pd.DataFrame({"los_gps": gps[s], "los_insar": df[s]})[valid[s]]
            for s in gps.columns
            if valid[s].sum() >= min_common_dates
        }
        rmse_df = pairwise_differential_rmse(
            merged, {s: coords[s] for s in merged}, min_common_dates=min_common_dates
        )
        pairs[name] = rmse_df
        svs[name] = (
            misfit_semivariogram(rmse_df, n_bins=n_bins, log_bins=True)
            if len(rmse_df)
            else pd.DataFrame()
        )
    sills = bootstrap_sills(
        pairs,
        sill_min_km=sill_min_km,
        near_max_km=near_max_km,
        n_boot=n_boot,
        seed=seed,
    )
    return DDResult(
        pairs=pairs, semivariograms=svs, sills=sills, sill_min_km=sill_min_km
    )


def bootstrap_sills(
    pairs: Mapping[str, pd.DataFrame],
    *,
    sill_min_km: float = 50.0,
    near_max_km: float = 10.0,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, SillResult]:
    """Sill (median gamma of far pairs) per variant with paired bootstrap CIs.

    `pairs` are ``pairwise_differential_rmse`` tables (``station1, station2,
    distance_km, rmse``) per variant.
    """
    names: Sequence[str] = list(pairs)
    stations = sorted(
        set().union(
            *(set(df["station1"]) | set(df["station2"]) for df in pairs.values())
        )
    )
    idx = {s: i for i, s in enumerate(stations)}
    rng = np.random.default_rng(seed)
    out: dict[str, SillResult] = {}
    far = {}
    for n in names:
        df = pairs[n]
        gamma = 0.5 * df["rmse"].to_numpy() ** 2
        dist = df["distance_km"].to_numpy()
        f = dist >= sill_min_km
        far[n] = (
            df["station1"][f].map(idx).to_numpy(),
            df["station2"][f].map(idx).to_numpy(),
            gamma[f],
        )
        near = dist < near_max_km
        n_st = len(set(df["station1"]) | set(df["station2"]))
        out[n] = SillResult(
            sill=float(np.median(gamma[f])) if f.any() else float("nan"),
            ci_lo=float("nan"),
            ci_hi=float("nan"),
            n_pairs=len(df),
            n_stations=n_st,
            near_gamma=float(np.median(gamma[near])) if near.any() else float("nan"),
            median_pair_rmse=float(np.median(df["rmse"])) if len(df) else float("nan"),
        )
    if n_boot > 0 and stations:
        draws = {n: np.empty(n_boot) for n in names}
        for b in range(n_boot):
            counts = np.bincount(
                rng.integers(0, len(stations), len(stations)), minlength=len(stations)
            ).astype(float)
            for n in names:
                i, j, g = far[n]
                draws[n][b] = weighted_median(g, counts[i] * counts[j])
        for n in names:
            lo, hi = ci95(draws[n])
            out[n].ci_lo, out[n].ci_hi, out[n].draws = lo, hi, draws[n]
    return out
