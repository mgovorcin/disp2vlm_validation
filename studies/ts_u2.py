# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-U2 (TS-U1 phase 2, Venti plan T62): unwrapping offsets of water-separated regions.

An unwrapping error in one interferogram does not survive the DISP inversion
as a whole cycle: the inversion spreads it, so the affected region's
displacement shifts by a fraction of a cycle while the product's
`timeseries_inversion_residuals` rises over the whole region (owner,
2026-10-23). Disconnected land (islands, peninsulas, the far shore of a bay) is
where this happens: the unwrapper can put it on a different cycle in each
interferogram, or in each ministack.

Method (prototype; the owner keeps it out of the calibration, 2026-10-27):

1. **Regions**: water-separated land regions (water-mask watershed,
   `venti.unwrap.regions.segment_regions`). The reference is the region with
   the most valid DISP pixels (in SW Florida the largest region, the
   Everglades, has no DISP at all).
2. **Flag** (`region_flags`): a region is disconnected in an epoch when its
   median log10 |inversion residual| is >= `lift` orders above the reference.
3. **Slips** (`remove_slips`): on the region-minus-reference series (cycles),
   a slip is a `w`-epoch median step >= `step` cycles and >= 3 noise sigmas at
   a flagged epoch or one bordering a flagged run (the exit of a disconnected
   ministack). Each slip is removed by its own size; an opposite step >= `pair`
   within `pair_window` epochs is removed with it (a dip and its recovery).
   Gradual drift has no such steps and is left alone.

    python studies/ts_u2.py --stack STACK.npy --meta STACK.json \
        --disp-dir FRAME/disp_s1 --out OUT.json
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from pathlib import Path

import numpy as np

CYCLE_M = 0.02773  # Sentinel-1 lambda/2


def _med(a: np.ndarray) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(np.nanmedian(a)) if np.isfinite(a).any() else np.nan


def region_flags(
    region_logres: np.ndarray, reference_logres: np.ndarray, lift: float = 2.0
) -> np.ndarray:
    """Flag epochs where the region median log10 residual is >= `lift` over ref."""
    with np.errstate(invalid="ignore"):
        return (np.asarray(region_logres) - np.asarray(reference_logres)) >= lift


def remove_slips(
    rel: np.ndarray,
    flag: np.ndarray,
    *,
    w: int = 5,
    step: float = 0.5,
    pair: float = 0.25,
    pair_window: int = 60,
) -> tuple[np.ndarray, list[tuple[int, float]]]:
    """Return the correction (cycles, subtracted from `rel`) and the removed slips."""
    rel = np.asarray(rel, dtype=float)
    flag = np.asarray(flag, dtype=bool)
    n = rel.size
    elig = flag | np.r_[False, flag[:-1]] | np.r_[flag[1:], False]
    d = np.diff(rel)
    noise = 1.4826 * _med(np.abs(d - _med(d)))
    sig = 3.0 * noise / np.sqrt(w) if np.isfinite(noise) else step
    loc = np.full(n, np.nan)
    for i in range(w, n - w + 1):
        loc[i] = _med(rel[i : i + w]) - _med(rel[i - w : i])
    cand = [
        i
        for i in range(n)
        if elig[i] and np.isfinite(loc[i]) and abs(loc[i]) >= max(step, sig)
    ]
    chosen: list[int] = []
    for i in sorted(cand, key=lambda i: -abs(loc[i])):
        if all(abs(i - c) > w for c in chosen):
            chosen.append(i)
    paired: list[int] = []
    for c in sorted(chosen):
        for q in range(c + w, min(c + pair_window, n - w) + 1):
            if (
                np.isfinite(loc[q])
                and np.sign(loc[q]) == -np.sign(loc[c])
                and abs(loc[q]) >= pair
                and elig[q]
                and all(abs(q - x) > w for x in chosen + paired)
            ):
                paired.append(q)
                break
    cor = np.zeros(n)
    slips = []
    for i in sorted(chosen + paired):
        # the median window places a step within +-2 epochs: use the sharpest jump
        lo, hi = max(i - 2, 1), min(i + 3, n)
        j = lo + int(np.nanargmax(np.abs(rel[lo:hi] - rel[lo - 1 : hi - 1])))
        cor[j:] += loc[i]
        slips.append((j, float(loc[i])))
    return cor, slips


def main(argv: list[str] | None = None) -> None:
    """Flag and correct the water-separated regions of one frame's calibrated stack."""
    import h5py
    from scipy import ndimage
    from venti.unwrap.regions import segment_regions

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", type=Path, required=True)
    p.add_argument("--meta", type=Path, required=True)
    p.add_argument("--disp-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    stack = np.load(a.stack)
    meta = json.loads(a.meta.read_text())
    dates = np.array(meta["dates"], dtype="datetime64[D]")
    f = int(meta["factor"])
    n, ny, nx = stack.shape
    index = {str(d).replace("-", ""): k for k, d in enumerate(dates)}
    products = []
    for q in sorted(a.disp_dir.glob("*.nc")):
        m = re.search(r"_\d{8}T\d{6}Z_(\d{8})T", q.name)
        if m and m.group(1) in index:
            products.append((index[m.group(1)], q))
    products.sort()
    with h5py.File(products[-1][1], "r") as h:
        land = h["water_mask"][f // 2 : ny * f : f, f // 2 : nx * f : f].astype(bool)
    lab = segment_regions(land, erosion_iterations=1, min_region_area=50)
    valid = np.isfinite(stack[-1])
    counts = {int(k): int((valid & (lab == k)).sum()) for k in np.unique(lab) if k > 0}
    ref = max(counts, key=lambda k: counts[k])
    ids = [k for k in counts if k != ref]
    med_res = {k: np.full(n, np.nan) for k in [*ids, ref]}
    for i, q in products:
        with h5py.File(q, "r") as h:
            r = h["timeseries_inversion_residuals"][
                f // 2 : ny * f : f, f // 2 : nx * f : f
            ]
        logres = np.log10(np.abs(r.astype(np.float32)) + 1e-9)
        for k, series in med_res.items():
            series[i] = _med(logres[lab == k])
    rows: list[dict] = []
    for k in ids:
        m = lab == k
        near = (
            ndimage.binary_dilation(m, iterations=200)
            & (lab == ref)
            & ~ndimage.binary_dilation(m, iterations=3)
        )
        if near.sum() < 50:
            near = lab == ref
        rel = np.array([_med(stack[i][m]) - _med(stack[i][near]) for i in range(n)])
        flag = region_flags(med_res[k], med_res[ref])
        if not flag.any():
            continue
        _, slips = remove_slips(rel / CYCLE_M, flag)
        rows.append(
            {
                "region": k,
                "km2": round(float(m.sum()) * (30 * f) ** 2 / 1e6, 1),
                "flagged": int(flag.sum()),
                "n": n,
                "slips": [(str(dates[i]), round(s, 2)) for i, s in slips],
            }
        )
    a.out.write_text(json.dumps(rows, indent=1))
    for row in sorted(rows, key=lambda r: -r["km2"])[:10]:
        print(row)


if __name__ == "__main__":
    main()
