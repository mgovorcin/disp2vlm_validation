# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-U2 (TS-U1 phase 2, Venti plan T62.1): labels for inland unwrap errors.

TS-U1 phase 1 had 2 labelled error blocks (the PRD bar needs >= 100). This
study labels candidate inland errors on a whole calibrated stack:

1. **persistent whole-cycle step**: on the chained calibrated displacement
   (DISP - CAL, downsampled), after removing each cell's rate (median of the
   epoch-to-epoch rates, so a step does not bias it), the median level over
   `long_window` epochs after epoch i minus the median over `long_window`
   before is within `tol` cycles of a non-zero integer k, the short-window step
   agrees, and the level does not revert in the next `long_window` epochs
   (seasonal signal of a cycle or more reverts; an unwrap error persists);
2. connected cells with the same k and a step epoch within +-2 form a region;
3. **inversion residual**: the region's median |timeseries_inversion_residuals|
   in the product of the step epoch, divided by the frame median. Coherent
   signal (soil moisture, atmosphere) does not raise it; an unwrap
   inconsistency does.

    python studies/ts_u2.py --stack STACK.npy --meta STACK.json \
        --disp-dir FRAME/disp_s1 --out-dir OUT

``STACK.npy`` is (epochs, rows, cols) in metres on a regular grid that is
``factor`` times coarser than the DISP grid; ``STACK.json`` gives ``dates``
and ``factor``.
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from pathlib import Path

import numpy as np
from scipy import ndimage

CYCLE_M = 0.02773  # Sentinel-1 lambda/2


def _median(a: np.ndarray, i0: int, i1: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmedian(a[max(i0, 0) : max(i1, 0)], axis=0)


def remove_rate(stack: np.ndarray, t_years: np.ndarray) -> np.ndarray:
    """Remove each cell's rate, the median of its epoch-to-epoch rates."""
    t = np.asarray(t_years, dtype=float)
    dt = np.diff(t)[:, None, None]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rate = np.nanmedian(np.diff(stack, axis=0) / dt, axis=0)
    return (stack - rate[None] * (t - t[0])[:, None, None]).astype(np.float32)


def detect_steps(
    stack: np.ndarray,
    t_years: np.ndarray,
    *,
    short_window: int = 5,
    long_window: int = 15,
    tol: float = 0.2,
    revert_tol: float = 0.25,
    cycle: float = CYCLE_M,
) -> tuple[np.ndarray, np.ndarray]:
    """Per cell: the cycle count k and epoch index of its largest persistent step."""
    s = remove_rate(stack, t_years) / cycle
    n, w, L = s.shape[0], short_window, long_window
    kmap = np.zeros(s.shape[1:], dtype=np.int8)
    emap = np.full(s.shape[1:], -1, dtype=np.int32)
    best = np.zeros(s.shape[1:], dtype=np.float32)
    for i in range(L, n - 2 * L + 1):
        before, after = _median(s, i - L, i), _median(s, i, i + L)
        later = _median(s, i + L, i + 2 * L)
        short = _median(s, i, i + w) - _median(s, i - w, i)
        step = after - before
        k = np.rint(step)
        with np.errstate(invalid="ignore"):
            ok = (
                (np.abs(k) >= 1)
                & (np.abs(step - k) < tol)
                & (np.abs(short - k) < 0.35)
                & (np.abs(later - after) < revert_tol)
            )
            better = ok & (np.abs(step) > best)
        kmap[better] = k[better]
        emap[better] = i
        best[better] = np.abs(step[better])
    return kmap, emap


def step_regions(
    kmap: np.ndarray, emap: np.ndarray, min_cells: int = 5, epoch_slack: int = 2
) -> list[dict]:
    """Group connected cells with the same k and a step epoch within `epoch_slack`."""
    rows = []
    for kv in np.unique(kmap[kmap != 0]):
        lab, n = ndimage.label(kmap == kv, structure=np.ones((3, 3)))
        for r in range(1, n + 1):
            m = lab == r
            if m.sum() < min_cells:
                continue
            e0 = int(np.median(emap[m]))
            m &= np.abs(emap - e0) <= epoch_slack
            if m.sum() < min_cells:
                continue
            ys, xs = np.nonzero(m)
            rows.append(
                {
                    "k": int(kv),
                    "epoch": e0,
                    "cells": int(m.sum()),
                    "row": float(ys.mean()),
                    "col": float(xs.mean()),
                    "bbox": [
                        int(ys.min()),
                        int(ys.max()),
                        int(xs.min()),
                        int(xs.max()),
                    ],
                }
            )
    return rows


def region_mask(r: dict, kmap: np.ndarray, emap: np.ndarray, slack: int = 2):
    """Cells of region `r` (its bbox, its k, its epoch +- `slack`)."""
    b = r["bbox"]
    m = np.zeros(kmap.shape, dtype=bool)
    m[b[0] : b[1] + 1, b[2] : b[3] + 1] = True
    return m & (kmap == r["k"]) & (np.abs(emap - r["epoch"]) <= slack)


def residual_ratio(residual: np.ndarray, mask: np.ndarray) -> float | None:
    """Median |residual| in `mask` over the frame median (None if undefined)."""
    a = np.abs(np.asarray(residual, dtype=float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base = np.nanmedian(a)
        inside = np.nanmedian(a[mask]) if mask.any() else np.nan
    if not np.isfinite(base) or base <= 0 or not np.isfinite(inside):
        return None
    return float(inside / base)


def main(argv: list[str] | None = None) -> None:
    """Label the stack and score each region by its inversion residual."""
    import h5py

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--stack", type=Path, required=True)
    p.add_argument("--meta", type=Path, required=True)
    p.add_argument("--disp-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args(argv)
    stack = np.load(a.stack)
    meta = json.loads(a.meta.read_text())
    dates = np.array(meta["dates"], dtype="datetime64[D]")
    f = int(meta["factor"])
    t = (dates - dates[0]).astype(float) / 365.25
    kmap, emap = detect_steps(stack, t)
    rows = step_regions(kmap, emap)
    by_sec = {}
    for q in sorted(a.disp_dir.glob("*.nc")):
        m = re.search(r"_\d{8}T\d{6}Z_(\d{8})T", q.name)
        if m:
            by_sec[m.group(1)] = q
    ny, nx = kmap.shape
    for date in sorted({str(dates[r["epoch"]]) for r in rows}):
        fn = by_sec.get(date.replace("-", ""))
        res = None
        if fn is not None:
            with h5py.File(fn, "r") as h:
                res = h["timeseries_inversion_residuals"][
                    f // 2 : ny * f : f, f // 2 : nx * f : f
                ]
        for r in (r for r in rows if str(dates[r["epoch"]]) == date):
            r["date"] = date
            r["resid_ratio"] = (
                None if res is None else residual_ratio(res, region_mask(r, kmap, emap))
            )
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "regions.json").write_text(json.dumps(rows, indent=1))
    for thr in (3, 10, 30):
        sel = [r for r in rows if (r.get("resid_ratio") or 0) >= thr]
        print(
            f"residual ratio >= {thr}: {len(sel)} regions,"
            f" {sum(r['cells'] >= 20 for r in sel)} of >= 20 cells"
        )


if __name__ == "__main__":
    main()
