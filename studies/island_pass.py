# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Baseline calibrated velocity: water-aware breaklines and an island pass.

A study of the NA VLM baseline (cal-vlm-batch ``campaigns/na_coast/BASELINE.md``).
The per-pair calibration (Venti loclin, 50 km half-response cutoff, fitted to
DISP minus the UNR grid in LOS) is linear in the data, so the rate of a
calibrated stack equals ``raw rate - surface(raw rate - grid rate)``. This
module redoes that calibration on a frame's velocity map with two changes that
keep an unwrapping offset on one land piece from leaking into another:

1. **Breaklines that never cross water.** Land pieces are the connected valid
   pixels; gaps are bridged over land without data, never over water. A large
   piece (other than the largest) gets a surface of its own.
2. **Island pass.** Small pieces stay out of the surface fit. Each is then
   compared with the surface extended to it; a piece whose good pixels sit
   `island_min` or more off is labelled and shifted whole onto the surface.

Like `ts_g1`, this study reads the UNR grid on purpose (its subject is the
calibration to that grid); nothing here feeds the gate or a report.

Result on the 22 reviewed coast frames (2026-11-12): median MIDAS LOS RMS
2.98 -> 1.25 mm/yr, mean overlap NMAD 3.23 -> 2.29 mm/yr against the
calibration without breaklines.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy import ndimage as ndi

__all__ = [
    "calibrate_two_pass",
    "dominant_offset",
    "fast_areas",
    "land_pieces",
    "mixed_sign_areas",
    "small_pieces",
    "surface_fit",
]

CUTOFF_KM = 50.0  # half-response wavelength of the calibration surface
PIECE_MIN_KM2 = 97.0  # Venti surface.piece_min_pixels (3000 cells at 180 m)
BRIDGE_KM = 1.5  # closing radius: gaps of about twice this are bridged over land
ISLAND_MIN = 5.0  # mm/yr off the surface that labels a small piece
LEVEL_HALF_WIDTH = 5.0  # mm/yr around the dominant level: the piece's good pixels
FAST_MIN = 10.0  # mm/yr off the surface that marks a fast-moving area
FAST_MIN_KM2 = 25.0  # smaller patches are left to the robust weights
FAST_BUFFER_KM = 3.0  # margin kept out of the fit around a fast area
MIXED_SHARE = 0.2  # minority-sign share of a fast area that marks an unwrapping area
ROBUST_ITERATIONS = 3  # reweighted refits of a surface
ROBUST_FLOOR = 5.0  # mm/yr: smallest Tukey cutoff, so quiet frames keep their pixels

Surface = Callable[
    [np.ndarray, np.ndarray, float, float, np.ndarray | None], np.ndarray
]


def land_pieces(valid: np.ndarray, land: np.ndarray, px_km: float) -> np.ndarray:
    """Label the land pieces of a frame; gaps are bridged over land only.

    Parameters
    ----------
    valid : np.ndarray
        Pixels with a rate.
    land : np.ndarray
        True on land (with or without data); False on water.
    px_km : float
        Pixel size in km.

    Returns
    -------
    np.ndarray
        int32 labels on the valid pixels, 0 elsewhere.

    """
    valid = np.asarray(valid, dtype=bool)
    n = max(1, round(BRIDGE_KM / px_km))
    closed = ndi.binary_closing(np.pad(valid, n), np.ones((3, 3), bool), iterations=n)
    bridged = (closed[n:-n, n:-n] & np.asarray(land, dtype=bool)) | valid
    labels, _ = ndi.label(bridged)
    return np.where(valid, labels, 0).astype(np.int32)


def _piece_sizes(pieces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(pieces[pieces > 0], return_counts=True)


def small_pieces(pieces: np.ndarray, px_km: float) -> list[int]:
    """Return the pieces under PIECE_MIN_KM2, the largest piece excepted."""
    ids, cnt = _piece_sizes(pieces)
    if ids.size == 0:
        return []
    main = ids[cnt.argmax()]
    lim = PIECE_MIN_KM2 / px_km**2
    return [int(k) for k, n in zip(ids, cnt, strict=True) if k != main and n < lim]


def dominant_offset(values: np.ndarray) -> float:
    """Median of the values within LEVEL_HALF_WIDTH of their dominant level."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 5:
        return float(np.median(x)) if x.size else np.nan
    lo, hi = np.percentile(x, [1, 99])
    edges = np.arange(lo - 1.0, hi + 2.0, 1.0)
    if edges.size < 3:
        return float(np.median(x))
    hist = ndi.gaussian_filter1d(np.histogram(x, edges)[0].astype(float), 2)
    level = 0.5 * (edges[:-1] + edges[1:])[int(hist.argmax())]
    good = x[np.abs(x - level) < LEVEL_HALF_WIDTH]
    return float(np.median(good)) if good.size >= 3 else float(np.median(x))


def _venti_surface(
    field: np.ndarray,
    weight: np.ndarray,
    pixel_m: float,
    cutoff_m: float,
    fallback: np.ndarray | None,
) -> np.ndarray:
    from venti.calibration.loclin import loclin_surface

    return loclin_surface(field, weight, pixel_m, cutoff_m, fallback=fallback)[0]


def _fit_once(
    field: np.ndarray, w: np.ndarray, px_km: float, fit: Surface
) -> np.ndarray:
    sigma = CUTOFF_KM / px_km * float(np.sqrt(np.log(2.0) / 2.0) / np.pi)
    num = ndi.gaussian_filter(field * w, sigma, mode="nearest")
    den = ndi.gaussian_filter(w, sigma, mode="nearest")
    fallback = np.where(den > 1e-6, num / np.maximum(den, 1e-6), np.nan)
    if np.isnan(fallback).all():
        fallback = np.zeros(field.shape)
    elif np.isnan(fallback).any():
        _, (iy, ix) = ndi.distance_transform_edt(
            np.isnan(fallback), return_indices=True
        )
        fallback = fallback[iy, ix]
    return fit(field, w, px_km * 1000.0, CUTOFF_KM * 1000.0, fallback)


def surface_fit(
    rate: np.ndarray,
    grid: np.ndarray,
    weight: np.ndarray,
    px_km: float,
    *,
    surface: Surface | None = None,
    robust: bool = True,
) -> np.ndarray:
    """Calibration surface of ``rate - grid`` fitted on the `weight` pixels.

    Valid pixels outside `weight` are left out of the fit, so they must not
    reach the surface through its low-coverage fallback either: the fallback
    is a normalized Gaussian of the weighted field (nearest value where no
    weight is in reach), not the smoothed field Venti uses by default.

    `robust`: the fit is repeated with Tukey biweights on the residuals
    (cutoff 4.685 x their NMAD, at least ROBUST_FLOOR), so a local signal (a
    subsidence bowl, an unwrapping patch) does not bend the surface around it.
    """
    fit = _venti_surface if surface is None else surface
    field = np.where(np.isfinite(rate) & np.isfinite(grid), rate - grid, 0.0)
    w0 = np.asarray(weight, dtype=float)
    out = _fit_once(field, w0, px_km, fit)
    if not robust or not (w0 > 0).any():
        return out
    for _ in range(ROBUST_ITERATIONS):
        res = field - out
        r = res[w0 > 0]
        scale = 1.4826 * float(np.median(np.abs(r - np.median(r))))
        cut = max(4.685 * scale, ROBUST_FLOOR)
        u = np.clip(np.abs(res - np.median(r)) / cut, 0.0, 1.0)
        w = w0 * (1.0 - u**2) ** 2
        if w.sum() < 0.2 * w0.sum():  # keep a fit: never drop most of the piece
            break
        out = _fit_once(field, w, px_km, fit)
    return out


def fast_areas(residual: np.ndarray, valid: np.ndarray, px_km: float) -> np.ndarray:
    """Fast-moving areas of a calibrated residual (deformation mask).

    Pixels whose median-filtered residual is FAST_MIN or more off zero, in
    connected patches of at least FAST_MIN_KM2, grown by FAST_BUFFER_KM. A
    subsidence bowl (Mexico City, the Central Valley) or an unwrapping patch
    joined to the mainland must stay out of the calibration surface; this
    finds them where no hand-drawn polygon exists.
    """
    valid = np.asarray(valid, dtype=bool)
    sm = ndi.median_filter(np.where(valid, np.nan_to_num(residual), 0.0), size=5)
    hot = valid & (np.abs(sm) >= FAST_MIN)
    lab, n = ndi.label(hot)
    if n == 0:
        return np.zeros(valid.shape, bool)
    size = ndi.sum(hot, lab, np.arange(1, n + 1))
    keep = np.isin(lab, np.nonzero(size >= FAST_MIN_KM2 / px_km**2)[0] + 1)
    grow = max(1, round(FAST_BUFFER_KM / px_km))
    return ndi.binary_dilation(keep, iterations=grow) & valid if keep.any() else keep


def mixed_sign_areas(
    residual: np.ndarray, fast: np.ndarray, valid: np.ndarray
) -> np.ndarray:
    """Fast areas that look like unwrapping errors, not ground motion.

    Provisional rule (owner, 2026-11-12, option A): real deformation is
    one-signed (a subsidence bowl); an unwrapping area in incoherent land (the
    Everglades, F12638) carries strong positive and negative blobs side by
    side. A connected fast area whose minority sign holds MIXED_SHARE or more
    of its pixels at FAST_MIN or beyond is returned; the baseline blanks it.
    To be replaced by a test on the inversion residual (see the finding in
    cal-vlm-batch ``campaigns/na_coast/BASELINE.md``).
    """
    out = np.zeros(fast.shape, bool)
    lab, n = ndi.label(fast)
    if n == 0:
        return out
    sm = ndi.median_filter(np.where(valid, np.nan_to_num(residual), 0.0), size=5)
    idx = np.arange(1, n + 1)
    pos = ndi.sum(valid & (sm >= FAST_MIN), lab, idx)
    neg = ndi.sum(valid & (sm <= -FAST_MIN), lab, idx)
    share = np.minimum(pos, neg) / np.maximum(pos + neg, 1)
    return np.isin(lab, idx[share >= MIXED_SHARE])


def _piece_surface(
    rate: np.ndarray,
    grid: np.ndarray,
    w: np.ndarray,
    px_km: float,
    *,
    surface: Surface | None,
    auto_exclude: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Surface of one piece and its fast areas (2 = one-signed, 3 = mixed)."""
    surf = surface_fit(rate, grid, w, px_km, surface=surface)
    code = np.zeros(w.shape, np.uint8)
    if auto_exclude:
        fast = fast_areas(rate - grid - surf, w, px_km)
        if fast.any() and (w & ~fast).sum() >= 0.3 * w.sum():
            surf = surface_fit(rate, grid, w & ~fast, px_km, surface=surface)
            code[fast] = 2
            code[mixed_sign_areas(rate - grid - surf, fast, w)] = 3
    return surf, code


def calibrate_two_pass(
    rate: np.ndarray,
    grid: np.ndarray,
    valid: np.ndarray,
    pieces: np.ndarray,
    px_km: float,
    *,
    island_min: float = ISLAND_MIN,
    fit_exclude: np.ndarray | None = None,
    auto_exclude: bool = True,
    surface: Surface | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calibrate a velocity map with breaklines and the island pass.

    Parameters
    ----------
    rate, grid : np.ndarray
        Raw LOS rate and the UNR grid LOS rate, mm/yr.
    valid : np.ndarray
        Pixels that take part (land with a rate).
    pieces : np.ndarray
        Labels from `land_pieces`.
    px_km : float
        Pixel size in km.
    island_min : float
        Offset from the surface (mm/yr) that labels a small piece.
    fit_exclude : np.ndarray, optional
        Deformation mask: pixels that are calibrated but never fitted (known
        deformation areas).
    auto_exclude : bool
        Also leave the `fast_areas` of each piece out of its surface.
    surface : callable, optional
        ``surface(field, weight, pixel_m, cutoff_m, fallback) -> ndarray``;
        Venti's `loclin_surface` when omitted.

    Returns
    -------
    calibrated, island_shift, excluded : np.ndarray
        Calibrated rate (the island shift already removed), the shift of
        every labelled small piece (0 elsewhere), and the pixels left out of
        the fit (0 = fitted, 1 = `fit_exclude`, 2 = one-signed fast area found
        here, 3 = mixed-sign fast area: an unwrapping area the caller blanks).

    """
    valid = np.asarray(valid, dtype=bool)
    shift = np.zeros(rate.shape)
    excluded = np.zeros(rate.shape, np.uint8)
    keep = valid.copy()
    if fit_exclude is not None:
        known = valid & np.asarray(fit_exclude, dtype=bool)
        excluded[known] = 1
        keep &= ~known
    ids, cnt = _piece_sizes(pieces)
    small = small_pieces(pieces, px_km) if ids.size else []
    main = ids[cnt.argmax()] if ids.size else 0
    big = [int(k) for k in ids if k != main and int(k) not in small]
    frame_w = keep & ~np.isin(pieces, big + small)
    if frame_w.sum() < 0.3 * (valid & ~np.isin(pieces, big + small)).sum():
        frame_w = valid & ~np.isin(pieces, big + small)  # the mask covers the piece
    surf, code = _piece_surface(
        rate, grid, frame_w, px_km, surface=surface, auto_exclude=auto_exclude
    )
    out = rate - surf
    excluded = np.maximum(excluded, code)
    lim = PIECE_MIN_KM2 / px_km**2
    for k in big:  # breaklines: a large piece is calibrated on its own pixels
        w = keep & (pieces == k)
        if w.sum() < lim / 10:
            continue
        own, code = _piece_surface(
            rate, grid, w, px_km, surface=surface, auto_exclude=auto_exclude
        )
        out = np.where(pieces == k, rate - own, out)
        excluded = np.maximum(excluded, code)
    for k in small:  # island pass: every small piece is judged, however small
        m = valid & (pieces == k)
        off = dominant_offset((out - grid)[m])
        if np.isfinite(off) and abs(off) >= island_min:
            shift[pieces == k] = off
    return out - shift, shift, excluded
