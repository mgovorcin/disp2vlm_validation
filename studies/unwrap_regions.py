# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Unwrap-error regions of one DISP-S1 frame, and how each region ties to GNSS.

NA VLM baseline (cal-vlm-batch campaigns/na_coast/BASELINE.md, owner 2026-11-09).
Works on a decimated stack (~300 m): chained cumulative displacement, log10
|timeseries_inversion_residuals|, connected_component_labels, temporal
coherence, and the water mask.

1. **Regions** (`candidate_regions`): land pieces from the water mask, split
   inland by a watershed on the local contrast of the stack-median residual
   (the residual minus its ~12 km median, so a whole burst of high residual is
   not a boundary). The reference region is the largest.
2. **Tests** (`region_tests`), each region against a ring of reference-region
   pixels around it (10, 20 or 40 km, widened until coherent):

   - share of dates the unwrapper put it in another component, and its
     residual lift over the ring (local contrast): flag candidates;
   - rate and scatter of region minus ring: gradual errors (Bolivar);
   - trend inside blocks of dates against the steps between blocks:
     disconnection at data gaps (Matagorda, Alaska winters);
   - steps at rebases (first date of a ministack) against steps inside
     ministacks: ministack offsets (Central Valley).

   `verdict` turns them into error / candidate / consistent / untrusted.
3. **GNSS tie** (`gnss_tie`): the LOS rate a GNSS surface predicts between
   the region and its ring (the UNR grid interpolated to every pixel, which is
   what production has, or a surface from individual stations as a check), and
   the shift that puts an error region onto it (owner's approach, as in the
   Australia work and two-pass option C). On F28220 that alone takes raw DISP
   minus GNSS at 29 stations from RMSE 21.6 to 2.9 mm/yr (2026-11-10).

Thresholds are provisional (owner and Claude, 2026-11-10).
"""

from __future__ import annotations

import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import ndimage as ndi

MIN_CELLS = 100  # smallest region, decimated cells
SERIES_CELLS = 30  # coherent cells a region needs on a date
COH_GOOD = 0.6
RIDGE = 0.5  # local residual contrast that separates regions (orders of magnitude)
CONTRAST_PX = 41  # median-filter size of the local contrast (~12 km at 300 m)
GAP_YR = 0.25  # a gap in dates that starts a new block
RING_KM = (10.0, 20.0, 40.0, 80.0, 160.0, np.inf)  # inf = the whole reference region


def _med(a: np.ndarray) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(np.nanmedian(a)) if np.size(a) and np.isfinite(a).any() else np.nan


def _robust(a: np.ndarray) -> float:
    a = np.asarray(a)
    return float(1.4826 * np.median(np.abs(a - np.median(a)))) if a.size else np.nan


def decimal_year(d: str) -> float:
    """Decimal year of a YYYYMMDD date."""
    t = datetime.strptime(d, "%Y%m%d")
    start = datetime(t.year, 1, 1)
    return t.year + (t - start).days / (datetime(t.year + 1, 1, 1) - start).days


def chain(ref: list[str], sec: list[str], disp: np.ndarray) -> np.ndarray:
    """Cumulative displacement per secondary date.

    From reference-relative products sorted by secondary date.
    """
    level = {ref[0]: np.zeros(disp.shape[1:], np.float32)}
    out = np.empty_like(disp)
    for i, (r, s) in enumerate(zip(ref, sec, strict=True)):
        if r not in level:
            raise ValueError(
                f"reference {r} of product {i} is not reached by the chain"
            )
        out[i] = level[r] + disp[i]
        level[s] = out[i]
    return out


def local_contrast(med_logres: np.ndarray, size: int = CONTRAST_PX) -> np.ndarray:
    """Median residual minus its local median (removes burst-wide levels)."""
    sm = ndi.gaussian_filter(np.nan_to_num(med_logres, nan=_med(med_logres)), 1)
    return sm - ndi.median_filter(sm, size=size)


def candidate_regions(
    land: np.ndarray, med_logres: np.ndarray
) -> tuple[np.ndarray, int, np.ndarray]:
    """Region labels (0 = none), the reference label, and the residual local contrast.

    Seeds are the connected low-contrast parts of the land (ridges of the residual
    contrast split them); every other land pixel joins the nearest seed of its own
    water-bounded piece, so a region never crosses water.
    """
    hp = local_contrast(med_logres)
    pieces, n_pieces = ndi.label(land)
    seeds, n = ndi.label(ndi.binary_erosion(land & ~(hp > RIDGE), iterations=1))
    sizes = ndi.sum(np.ones_like(seeds), seeds, range(1, n + 1))
    seeds = np.where(
        np.concatenate([[False], sizes >= MIN_CELLS // 2])[seeds], seeds, 0
    )
    lab = np.zeros(land.shape, np.int32)
    for p in range(1, n_pieces + 1):
        piece = pieces == p
        sp = np.where(piece, seeds, 0)
        if not sp.any():
            sp = piece.astype(np.int32) * (
                seeds.max() + p
            )  # a piece without a seed is one region
        idx = ndi.distance_transform_edt(
            sp == 0, return_distances=False, return_indices=True
        )
        lab[piece] = sp[idx[0], idx[1]][piece]
    out = np.zeros(land.shape, np.int32)
    nxt = 1
    for v in np.unique(lab[lab > 0]):
        r = lab == v
        if r.sum() >= MIN_CELLS:
            out[r] = nxt
            nxt += 1
    if nxt == 1:
        raise ValueError("no region of at least MIN_CELLS cells")
    ids, cnt = np.unique(out[out > 0], return_counts=True)
    return out, int(ids[cnt.argmax()]), hp


def series(cum: np.ndarray, good: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Median displacement of the coherent cells of `m` per date (NaN if too few)."""
    return np.array(
        [
            _med(cum[i][good[i] & m]) if (good[i] & m).sum() >= SERIES_CELLS else np.nan
            for i in range(cum.shape[0])
        ]
    )


def ring(lab: np.ndarray, k: int, ref: int, px_km: float, km: float) -> np.ndarray:
    """Reference-region cells within `km` of region `k` (not touching it)."""
    m = lab == k
    return (
        ndi.binary_dilation(m, iterations=max(1, int(km / px_km)))
        & ~ndi.binary_dilation(m, iterations=3)
        & (lab == ref)
    )


def region_tests(delta: np.ndarray, years: np.ndarray, refdates: np.ndarray) -> dict:
    """Rate, scatter, block and rebase statistics of region minus ring (mm)."""
    ok = np.isfinite(delta)
    t, dl, rf = years[ok], delta[ok], np.asarray(refdates)[ok]
    if dl.size < 20:
        return {}
    g = np.zeros(dl.size, bool)  # single-date glitches
    noise = _robust(np.diff(dl)) + 1e-6
    g[1:-1] = (
        (np.abs(dl[1:-1] - dl[:-2]) > 4 * noise)
        & (np.abs(dl[1:-1] - dl[2:]) > 4 * noise)
        & (np.sign(dl[1:-1] - dl[:-2]) == np.sign(dl[1:-1] - dl[2:]))
    )
    p = np.polyfit(t[~g], dl[~g], 1)
    res = dl[~g] - np.polyval(p, t[~g])
    cut = np.where(np.diff(t) > GAP_YR)[0] + 1
    blocks = [
        b
        for b in np.split(np.arange(t.size), cut)
        if b.size >= 8 and t[b[-1]] - t[b[0]] >= 0.5
    ]
    if blocks:
        w = [t[b[-1]] - t[b[0]] for b in blocks]
        within = float(
            np.average([np.polyfit(t[b], dl[b], 1)[0] for b in blocks], weights=w)
        )
    else:
        within = np.nan
    inc = np.diff(dl)
    reb = rf[1:] != rf[:-1]
    # both sets of steps against the median step inside ministacks: alternating
    # offsets (+a, -a) at rebases
    # would give a near-zero spread around their own median
    centre = float(np.median(inc[~reb])) if (~reb).any() else 0.0

    def spread(q: np.ndarray) -> float:
        return float(1.4826 * np.median(np.abs(q - centre))) if q.size else np.nan

    inside = spread(inc[~reb])
    big = np.abs(inc - centre) > max(
        3 * (inside if np.isfinite(inside) else noise), 10.0
    )
    return {
        "n_dates": int(dl.size),
        "rate": float(p[0]),
        "scatter": _robust(res),
        "within_rate": within,
        "n_blocks": len(blocks),
        "glitch_share": float(g.mean()),
        "rebase_ratio": spread(inc[reb]) / (inside + 1e-6) if reb.any() else np.nan,
        "big_steps": int(big.sum()),
        "big_at_rebase": float(reb[big].mean()) if big.any() else np.nan,
    }


def verdict(r: dict | pd.Series) -> str:
    """Provisional class from the tests (see module docstring)."""
    r = pd.Series(r)
    if pd.isna(r.get("rate")):
        return "no data"
    why = []
    linked = r.sep >= 0.5 or r.lift_local >= 1
    shifts = [v for k, v in r.items() if k.endswith("_shift") and pd.notna(v)]
    if linked and shifts and min(abs(v) for v in shifts) > 5:
        why.append("off GNSS surface")
    if r.sep >= 0.5 and abs(r.rate) > 5 and r.scatter > 15:
        why.append("gradual")
    gaps = (
        r.n_blocks >= 2 and pd.notna(r.within_rate) and abs(r.rate - r.within_rate) > 3
    )
    if gaps and (r.sep >= 0.5 or r.lift_local >= 1):
        why.append("steps at gaps")
    if (
        pd.notna(r.rebase_ratio)
        and r.rebase_ratio > 3
        and pd.notna(r.big_at_rebase)
        and r.big_at_rebase > 0.3
        and r.big_steps >= 5
    ):
        why.append("steps at rebases")
    if why:
        return "error: " + "+".join(why)
    if gaps:
        return "candidate: steps at gaps only"
    if r.n_blocks == 0:
        return "untrusted: too little data"
    if r.sep >= 0.5 or r.lift_local > 1:
        return "candidate, consistent"
    return "consistent"


def gnss_tie(m: np.ndarray, rg: np.ndarray, surface: np.ndarray) -> float:
    """Region-minus-ring LOS rate a GNSS surface predicts (mm/yr).

    `surface` is a GNSS LOS-rate surface on the stack grid: the UNR grid
    interpolated to every pixel (what production has) or a surface from
    individual stations (an independent check). Point sampling is not enough:
    grid nodes are ~25 km apart and rarely fall on a region's coherent cells.
    """
    a, b = surface[m], surface[rg]
    if np.isfinite(a).sum() < 10 or np.isfinite(b).sum() < 10:
        return np.nan
    return _med(a) - _med(b)


def analyse(
    stack: dict, px_km: float, gnss: dict[str, np.ndarray] | None = None
) -> tuple[pd.DataFrame, np.ndarray, int]:
    """All tests for every region of one frame.

    `stack`: cum (n, h, w) mm, logres, cc, coh (n, h, w), water (h, w; 1 = land),
    ref and sec (YYYYMMDD strings). `gnss`: name -> LOS-rate surface (mm/yr) on the
    stack grid, e.g. {"grid": ..., "stations": ...}. A region's `<name>_shift` is
    the rate to remove to put it on that surface (observed minus expected).
    """
    cum, lr, cc, coh = stack["cum"], stack["logres"], stack["cc"], stack["coh"]
    years = np.array([decimal_year(s) for s in stack["sec"]])
    refd = np.asarray(stack["ref"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        valid = np.nanmean(coh, axis=0) >= 0.5
        med_lr = np.nanmedian(lr, axis=0)
    good = (coh >= COH_GOOD) & valid[None]
    lab, ref, hp = candidate_regions(stack["water"] == 1, med_lr)
    mref = lab == ref
    nt = cum.shape[0]
    refcc = np.array(
        [
            (
                np.bincount(cc[i][mref & (cc[i] > 0)]).argmax()
                if (mref & (cc[i] > 0)).any()
                else 0
            )
            for i in range(nt)
        ]
    )
    rows = []
    for k in np.unique(lab[lab > 0]):
        if k == ref:
            continue
        m = lab == k
        yy, xx = np.argwhere(m).mean(axis=0)
        row = {
            "region": int(k),
            "cells": int(m.sum()),
            "good_cells": int((m & valid).sum()),
            "row": float(yy),
            "col": float(xx),
        }
        dk = series(cum, good, m)
        if np.isfinite(dk).sum() >= 20:
            # nearest reference cells first; a region far across water (an island
            # more than 40 km off) falls back to wider rings, then to the whole
            # reference region (ring_km = inf). The GNSS tie uses the same cells,
            # so the long-wavelength difference over that distance is accounted for.
            for km in RING_KM:
                rg = ring(lab, k, ref, px_km, km) if np.isfinite(km) else mref
                dr = series(cum, good, rg)
                if np.isfinite(dr).sum() >= 0.8 * np.isfinite(dk).sum():
                    break
            t = region_tests(dk - dr, years, refd)
            if t:
                sep = np.array(
                    [
                        (
                            (np.bincount(cc[i][m & (cc[i] > 0)]).argmax() != refcc[i])
                            if (m & (cc[i] > 0)).any()
                            else False
                        )
                        for i in range(nt)
                    ]
                )
                row.update(
                    t,
                    ring_km=km,
                    sep=float(sep.mean()),
                    lift_local=_med(hp[m]) - _med(hp[rg]),
                )
                for name, surf in (gnss or {}).items():
                    exp = gnss_tie(m, rg, surf)
                    row.update(
                        {f"{name}_expected": exp, f"{name}_shift": t["rate"] - exp}
                    )
        rows.append(row)
    df = pd.DataFrame(rows)
    if len(df):
        df["verdict"] = df.apply(verdict, axis=1)
    return df, lab, ref


# --------------------------------------------------------------------------------------
# Regions from the calibration residual plane (owner 2026-11-11)
# --------------------------------------------------------------------------------------
# R = raw LOS velocity - UNR grid LOS velocity. Land pixels stay connected while their
# smoothed R differs by < RP_STEP; water and jumps in R cut regions apart. The reference
# level is a peak of the area-weighted R histogram, the one with the lowest median
# inversion residual among peaks holding >= RP_PEAK_SHARE of the land. Bias = region R
# minus the reference level's >50 km trend. Error: |bias| >= RP_BIG, or
# RP_FLAG <= |bias| < RP_BIG confirmed by a step of the same sign against nearby
# reference cells, or by an inversion residual RP_LR_EXCESS orders of magnitude above
# the reference level's.

RP_STEP = 5.0  # mm/yr between neighbours that still connects them
RP_FLAG = 10.0  # mm/yr bias that needs an edge step to confirm
RP_BIG = 30.0  # mm/yr bias that is an error on its own
RP_MIN_PX = 5
RP_PEAK_SHARE = 0.25
RP_TREND_KM = 9.4  # Gaussian sigma: half response at 50 km
RP_EDGE_KM = (1.5, 5.0, 10.0, 20.0)
RP_GAP_KM = (
    1.5  # land pixels without a rate join through the nearest valid pixel this close
)
RP_LR_EXCESS = (
    2.0  # orders of magnitude of inversion residual above the reference level
)


def rate_map(cum: np.ndarray, years: np.ndarray, good: np.ndarray) -> np.ndarray:
    """Per-pixel least-squares rate (mm/yr) over the coherent dates (>= 20)."""
    s = np.zeros(cum.shape[1:])
    st = s.copy()
    stt = s.copy()
    sd = s.copy()
    std = s.copy()
    for i, t in enumerate(years):
        m = good[i] & np.isfinite(cum[i])
        d = np.where(m, cum[i], 0.0)
        s += m
        st += m * t
        stt += m * t * t
        sd += d
        std += d * t
    with np.errstate(invalid="ignore", divide="ignore"):
        den = s * stt - st * st
        r = (s * std - st * sd) / den
    r[(s < 20) | ~np.isfinite(r)] = np.nan
    return r


def connected_levels(
    rs: np.ndarray, land: np.ndarray, step: float = RP_STEP
) -> np.ndarray:
    """Label land pixels connected through 4-neighbours closer than `step`.

    Labels are numbered by size (1 = largest).
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    h, w = rs.shape
    idx = np.arange(h * w).reshape(h, w)
    ok = land & np.isfinite(rs)
    r_, c_ = [], []
    for a, b in (
        ((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
        ((slice(0, -1), slice(None)), (slice(1, None), slice(None))),
    ):
        m = ok[a] & ok[b] & (np.abs(rs[a] - rs[b]) < step)
        r_.append(idx[a][m])
        c_.append(idx[b][m])
    r = np.concatenate(r_)
    c = np.concatenate(c_)
    g = coo_matrix((np.ones(r.size, bool), (r, c)), shape=(h * w, h * w))
    _, lab = connected_components(g, directed=False)
    lab = lab.reshape(h, w) + 1
    lab[~ok] = 0
    ids, cnt = np.unique(lab[lab > 0], return_counts=True)
    remap = np.zeros(lab.max() + 1, int)
    remap[ids[np.argsort(-cnt)]] = np.arange(1, len(ids) + 1)
    return remap[lab]


def reference_level(
    rs: np.ndarray, land: np.ndarray, med_logres: np.ndarray | None
) -> tuple[float, list[dict]]:
    """Pick the reference R level.

    Among histogram peaks holding >= RP_PEAK_SHARE of the land, the one with the
    lowest median inversion residual (the largest area when there is no residual).
    """
    x = rs[land & np.isfinite(rs)]
    lo, hi = np.percentile(x, [0.5, 99.5])
    edges = np.arange(lo, hi + 1.0, 1.0)
    if edges.size < 3:
        return float(np.median(x)), []
    hist = ndi.gaussian_filter1d(np.histogram(x, edges)[0].astype(float), 2)
    c = 0.5 * (edges[:-1] + edges[1:])
    peaks: list[dict] = []
    for i in np.argsort(-hist):
        if hist[i] < hist[max(0, i - 3) : i + 4].max() or any(
            abs(c[i] - p["level"]) < 2 * RP_STEP for p in peaks
        ):
            continue
        m = land & (np.abs(rs - c[i]) < RP_STEP)
        share = float(m.sum() / max(1, land.sum()))
        if share < 0.05:
            break
        peaks.append(
            {
                "level": float(c[i]),
                "share": share,
                "logres": _med(med_logres[m]) if med_logres is not None else np.nan,
            }
        )
    big = [p for p in peaks if p["share"] >= RP_PEAK_SHARE] or peaks[:1]
    if (
        med_logres is not None
        and len(big) > 1
        and all(np.isfinite(p["logres"]) for p in big)
    ):
        best = min(big, key=lambda p: p["logres"])
    else:
        best = max(big, key=lambda p: p["share"])
    return best["level"], peaks


def smooth_trend(vals: np.ndarray, use: np.ndarray, sig: float) -> np.ndarray:
    """Smooth `vals` over the `use` pixels (normalized Gaussian).

    Where `use` is sparse (weight < 0.1) a 3x then 9x broader kernel takes over, so
    the trend is never extrapolated from a few edge pixels.
    """
    out = np.full(vals.shape, np.nan)
    v = np.where(use, vals, 0.0)
    for k, s_ in enumerate((sig, 3 * sig, 9 * sig)):
        num = ndi.gaussian_filter(v, s_)
        den = ndi.gaussian_filter(use.astype(float), s_)
        sel = ((den > 0.1) if k < 2 else (den > 1e-9)) & np.isnan(out)
        out[sel] = num[sel] / den[sel]
    return np.nan_to_num(out)


def edge_step(
    r: np.ndarray, m: np.ndarray, refm: np.ndarray, px_km: float
) -> tuple[float, float]:
    """Return the step of a piece against nearby reference cells, and the band used.

    Median R of the piece minus that of the reference cells, in the narrowest band of
    RP_EDGE_KM with >= 20 valid cells on both sides; (nan, nan) when there is no
    reference within 20 km.
    """
    yy, xx = np.nonzero(m)
    w = int(max(RP_EDGE_KM) / px_km) + 2
    y0, y1 = max(0, yy.min() - w), yy.max() + w + 1
    x0, x1 = max(0, xx.min() - w), xx.max() + w + 1
    mm, rr, ref = m[y0:y1, x0:x1], r[y0:y1, x0:x1], refm[y0:y1, x0:x1]
    if not ref.any():
        return np.nan, np.nan
    d_ref = ndi.distance_transform_edt(~ref) * px_km
    d_m = ndi.distance_transform_edt(~mm) * px_km
    for km in RP_EDGE_KM:
        a = rr[mm & (d_ref <= km)]
        b = rr[ref & (d_m <= km)]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if a.size >= 20 and b.size >= 20:
            return float(np.median(a) - np.median(b)), km
    return np.nan, np.nan


def resplane_verdict(bias: float, step: float, lr_excess: float = np.nan) -> str:
    """Classify a level: ok, error or candidate.

    Error: bias >= RP_BIG; or >= RP_FLAG with an edge step of the same sign, or with
    an inversion residual RP_LR_EXCESS orders above the reference level.
    """
    if not np.isfinite(bias) or abs(bias) < RP_FLAG:
        return "ok"
    if abs(bias) >= RP_BIG:
        return "error: bias"
    if np.isfinite(step) and abs(step) >= RP_FLAG and np.sign(step) == np.sign(bias):
        return "error: edge step"
    if np.isfinite(lr_excess) and lr_excess >= RP_LR_EXCESS:
        return "error: inversion residual"
    return (
        "candidate: no reference nearby"
        if not np.isfinite(step)
        else "candidate: no edge step"
    )


def resplane_analyse(
    stack: dict, px_km: float, grid: np.ndarray, rate: np.ndarray | None = None
) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Find the regions of one frame on its residual plane (raw rate - UNR grid LOS).

    Returns one row per connected level (bias, edge step, median log residual,
    verdict, shift = bias: the rate that puts the level on the grid's trend), the
    level labels, and {reference level R0, peaks, residual plane, trend, shift map}.
    """
    years = np.array([decimal_year(s) for s in stack["sec"]])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        valid = np.nanmean(stack["coh"], axis=0) >= 0.5
        med_lr = np.nanmedian(stack["logres"], axis=0)
    good = (stack["coh"] >= COH_GOOD) & valid[None]
    if rate is None:
        rate = rate_map(stack["cum"], years, good)
    valid_r = (stack["water"] == 1) & np.isfinite(rate) & np.isfinite(grid)
    r = np.where(valid_r, rate - grid, np.nan)
    # fill gaps (incoherent pixels) with the nearest valid value first, then smooth:
    # a frame-wide fill value would pull sparse error areas onto the reference level
    dist, (iy, ix) = ndi.distance_transform_edt(~valid_r, return_indices=True)
    rs = ndi.median_filter(np.nan_to_num(r[iy, ix]), size=3)
    # connect through small gaps: land within RP_GAP_KM of a valid pixel
    land = (stack["water"] == 1) & (dist * px_km <= RP_GAP_KM)
    rs = np.where(land, rs, np.nan)
    lab = connected_levels(rs, land)
    lab[~valid_r] = 0  # statistics and shifts on valid pixels only
    r0, peaks = reference_level(rs, valid_r, med_lr)
    land = valid_r
    ids, cnt = np.unique(lab[lab > 0], return_counts=True)
    use = land & (np.abs(rs - r0) < RP_STEP)
    sig = RP_TREND_KM / px_km
    for _ in range(2):  # flagged levels must not pull the trend
        trend = smooth_trend(rs - r0, use, sig)
        bias = ndi.median(np.nan_to_num(rs - r0 - trend), lab, ids)
        bad = ids[(np.abs(bias) >= RP_FLAG) & (cnt >= RP_MIN_PX)]
        use = land & ~np.isin(lab, bad) & (np.abs(rs - r0 - trend) < RP_STEP)
    lr_l = ndi.median(np.nan_to_num(med_lr, nan=np.nanmedian(med_lr)), lab, ids)
    lr_ref = _med(med_lr[use])
    rows = []
    for k, n, b, lrk in zip(ids, cnt, bias, lr_l, strict=True):
        row = {
            "level": int(k),
            "px": int(n),
            "bias": float(b),
            "logres": float(lrk),
            "edge_step": np.nan,
            "edge_km": np.nan,
        }
        if n >= RP_MIN_PX and RP_FLAG <= abs(b) < RP_BIG:
            row["edge_step"], row["edge_km"] = edge_step(r, lab == k, use, px_km)
        row["lr_excess"] = float(lrk - lr_ref)
        row["verdict"] = (
            resplane_verdict(b, row["edge_step"], row["lr_excess"])
            if n >= RP_MIN_PX
            else "ok"
        )
        row["shift"] = float(b) if row["verdict"].startswith("error") else 0.0
        rows.append(row)
    df = pd.DataFrame(rows)
    shift = absorb(lab, df, rs - r0 - trend, px_km)
    return (
        df,
        lab,
        {
            "r0": r0,
            "peaks": peaks,
            "residual": r,
            "trend": trend,
            "shift": shift,
            "rs": rs,
        },
    )


def absorb(
    lab: np.ndarray,
    df: pd.DataFrame,
    rd: np.ndarray,
    px_km: float,
    km: float = RP_GAP_KM,
) -> np.ndarray:
    """Build the shift map: error levels, plus nearby pixels at the same level.

    Noise splits an error region into many small levels; a pixel outside every error
    level, within `km` of one, takes the shift of the nearest error pixel when its
    detrended residual `rd` is within max(RP_STEP, 15 %) of that shift.
    """
    shift = np.zeros(lab.shape)
    err = df[df.verdict.str.startswith("error")]
    if err.empty:
        return shift
    lut = np.zeros(lab.max() + 1)
    lut[err.level.values] = err.bias.values
    shift = lut[lab]
    em = shift != 0
    d, (iy, ix) = ndi.distance_transform_edt(~em, return_indices=True)
    near = shift[iy, ix]
    take = (
        (~em)
        & (lab > 0)
        & (d * px_km <= km)
        & (np.abs(rd - near) <= np.maximum(RP_STEP, 0.15 * np.abs(near)))
    )
    shift[take] = near[take]
    return shift
