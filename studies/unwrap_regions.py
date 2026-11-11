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
