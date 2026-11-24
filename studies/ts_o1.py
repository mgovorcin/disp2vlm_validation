# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-O1 (Venti plan T67.1): overshoot measures for the calibration surface.

The calibration surface should carry only the long-wavelength GNSS-tied field;
features shorter than the 50 km cutoff should pass through it unchanged. Two
measures, neither of which changes a value:

(a) **Signal preservation.** Inject a Gaussian bump or bowl into a frame's raw
    velocity, calibrate again, and report the share of the feature that is left
    (`survival`): ``1 - mean(dS) / mean(f)`` over the feature core, where ``dS`` is
    the change of the calibration surface. An ideal Gaussian smoother with the
    same kernel leaves `ideal_survival` at the centre. Below 0 is a sign flip.
(b) **Overshoot on real data.** For each segment (small land piece, coherent
    cluster, owner polygon), compare what calibration adds with the raw anomaly
    against a ring around it (`segment_anomalies`, `flags`).

The thresholds below are fixed before any T67.2 arm is scored (plan T67.4) and
must not be tuned on arm results. Cases with ``|raw| >= STRESS_MIN`` look like
unwrap errors (T62's) and are reported apart.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy import ndimage as ndi

__all__ = [
    "coherent_clusters",
    "flags",
    "gaussian_feature",
    "ideal_survival",
    "preservation_run",
    "ring_of",
    "segment_anomalies",
    "summarize_overshoot",
    "survival",
]

FLIP_RAW_MIN = 1.0  # mm/yr: raw anomaly large enough for a sign to mean something
FLIP_CAL_MIN = 0.5  # mm/yr: calibrated anomaly large enough to count as flipped
FLAT_MAX = 0.5  # mm/yr: raw anomaly below this is a flat feature
INJECT_MIN = 1.0  # mm/yr: calibration adds more than this to a flat feature
STRESS_MIN = 10.0  # mm/yr: raw anomaly of an unwrap-like case (T62), reported apart
RING_DEG = 0.15  # ring width around a segment, as the 2026-11-09 polygon triage
CLUSTER_KM2 = (1.0, 400.0)  # coherent-cluster sizes kept
CLUSTER_PERCENTILE = 90.0  # coherence percentile that seeds a cluster


def gaussian_feature(
    shape: tuple[int, int],
    center: tuple[int, int],
    diameter_px: float,
    amplitude: float,
    within: np.ndarray | None = None,
) -> np.ndarray:
    """Gaussian bump (amplitude > 0) or bowl, sigma = diameter / 4.

    `within` (bool) confines the feature to one land piece.
    """
    sigma = diameter_px / 4.0
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    r2 = (yy - center[0]) ** 2 + (xx - center[1]) ** 2
    f = (amplitude * np.exp(-r2 / (2.0 * sigma * sigma))).astype(np.float32)
    if within is not None:
        f = np.where(within, f, 0.0).astype(np.float32)
    return f


def _core(
    shape: tuple[int, int],
    center: tuple[int, int],
    diameter_px: float,
    valid: np.ndarray,
) -> np.ndarray:
    sigma = diameter_px / 4.0
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    return ((yy - center[0]) ** 2 + (xx - center[1]) ** 2 <= sigma * sigma) & valid


def survival(
    feature: np.ndarray,
    surface_change: np.ndarray,
    center: tuple[int, int],
    diameter_px: float,
    valid: np.ndarray,
) -> float:
    """Return the share of a feature left after calibration, over r <= sigma."""
    core = _core(feature.shape, center, diameter_px, valid & (feature != 0))
    if not core.any():
        return float("nan")
    return float(1.0 - surface_change[core].mean() / feature[core].mean())


def ideal_survival(diameter_km: float, kernel_sigma_km: float) -> float:
    """Centre survival under an ideal Gaussian smoother: 1 - sf^2 / (sf^2 + sk^2)."""
    sf2 = (diameter_km / 4.0) ** 2
    return 1.0 - sf2 / (sf2 + kernel_sigma_km**2)


def ring_of(segment: np.ndarray, ring_px: int) -> np.ndarray:
    """Pixels within `ring_px` of `segment`, outside it."""
    return ndi.binary_dilation(segment, iterations=max(int(ring_px), 1)) & ~segment


def coherent_clusters(
    coherence: np.ndarray, valid: np.ndarray, px_km: float
) -> list[np.ndarray]:
    """Find clusters above the coherence percentile, within `CLUSTER_KM2`."""
    c = np.where(valid, coherence, np.nan)
    if not np.isfinite(c).any():
        return []
    threshold = np.nanpercentile(c, CLUSTER_PERCENTILE)
    labels, _ = ndi.label(np.nan_to_num(c, nan=-np.inf) > threshold)
    sizes = np.bincount(labels.ravel()) * px_km**2
    sizes[0] = 0
    keep = np.flatnonzero((sizes >= CLUSTER_KM2[0]) & (sizes <= CLUSTER_KM2[1]))
    return [labels == i for i in keep]


def segment_anomalies(
    raw: np.ndarray, cal: np.ndarray, segment: np.ndarray, ring: np.ndarray
) -> tuple[float, float, float]:
    """Return raw, calibrated and added anomaly: segment median minus ring median."""
    ok = np.isfinite(raw) & np.isfinite(cal)
    seg, rg = segment & ok, ring & ok
    if not seg.any() or not rg.any():
        return float("nan"), float("nan"), float("nan")
    r = float(np.median(raw[seg]) - np.median(raw[rg]))
    c = float(np.median(cal[seg]) - np.median(cal[rg]))
    return r, c, c - r


def flags(raw_anomaly: float, cal_anomaly: float) -> dict[str, bool]:
    """Sign flip, injection into a flat feature, and unwrap-like stress case."""
    added = cal_anomaly - raw_anomaly
    return {
        "flip": bool(
            abs(raw_anomaly) >= FLIP_RAW_MIN
            and abs(cal_anomaly) >= FLIP_CAL_MIN
            and np.sign(cal_anomaly) != np.sign(raw_anomaly)
        ),
        "inject": bool(abs(raw_anomaly) < FLAT_MAX and abs(added) > INJECT_MIN),
        "stress": bool(abs(raw_anomaly) >= STRESS_MIN),
    }


def summarize_overshoot(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Summarize non-stress rows per segment kind.

    Flip fraction (of |raw| >= 1), injection fraction, median |added| and median
    added/raw.
    """
    out: dict[str, dict[str, float]] = {}
    kinds = sorted({r["kind"] for r in rows})
    for k in kinds:
        rr = [r for r in rows if r["kind"] == k and not r["stress"]]
        big = [r for r in rr if abs(r["raw"]) >= FLIP_RAW_MIN]
        out[k] = {
            "n": float(len(rr)),
            "flip": float(np.mean([r["flip"] for r in big])) if big else float("nan"),
            "inject": float(np.mean([r["inject"] for r in rr])) if rr else float("nan"),
            "median_abs_added": (
                float(np.median([abs(r["added"]) for r in rr])) if rr else float("nan")
            ),
            "median_added_over_raw": (
                float(np.median([r["added"] / r["raw"] for r in big]))
                if big
                else float("nan")
            ),
        }
    return out


def preservation_run(
    raw: np.ndarray,
    valid: np.ndarray,
    surface: Callable[[np.ndarray], np.ndarray],
    features: list[dict],
    base_surface: np.ndarray | None = None,
) -> list[float]:
    """Inject `features` together, calibrate once, return each feature's survival.

    Each feature is a dict with center, diameter_px, amplitude and optional within;
    `surface` maps a velocity field to its calibration surface.

    Features in one run must be far enough apart not to interact (about six kernel
    sigmas plus the diameter).
    """
    s0 = surface(raw) if base_surface is None else base_surface
    fields = [
        gaussian_feature(
            raw.shape, f["center"], f["diameter_px"], f["amplitude"], f.get("within")
        )
        for f in features
    ]
    s1 = surface(np.where(valid, raw + np.sum(fields, axis=0), np.nan))
    ds = s1 - s0
    return [
        survival(fld, ds, f["center"], f["diameter_px"], valid)
        for fld, f in zip(fields, features, strict=True)
    ]
