# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Velocity bias vs MIDAS, split by reference-date block (Venti plan T38.4).

A DISP-S1 stack is a chain of reference-date blocks; within a block every
product is relative to the block's reference date, so the in-block rate at
a station comes from the products alone, with no chaining. Comparing

* the InSAR - GNSS drift accumulated inside each block (their sum) with
* the bias of the rate fitted to the chained series

tells whether a frame-wide velocity bias sits in the products themselves
(the block drifts add up to it) or comes from linking the blocks (they do
not). The per-block drifts also show any seasonal pattern.

Reads a ``disp2vlm-validate run`` output (``stations.csv``,
``station_series_mm.csv``), the frame's GNSS cache and the DISP directory
(for the block structure). Writes ``bias_by_block.csv`` and prints a table.

    python studies/bias_by_block.py RUN_DIR DISP_DIR GNSS_CACHE [--classes stable]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from disp2vlm_validation.gnss import gnss_los_series
from disp2vlm_validation.stack import decimal_year, list_epochs


def _slope(t: np.ndarray, y: np.ndarray, min_points: int) -> float:
    ok = np.isfinite(y)
    if ok.sum() < min_points or np.ptp(t[ok]) < 0.1:
        return np.nan
    return float(np.polyfit(t[ok], y[ok], 1)[0])


def bias_by_block(
    run_dir: Path,
    disp_dir: Path,
    gnss_cache: Path,
    classes: list[str] | None = None,
    min_points: int = 5,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Per-block and chained bias (mm/yr, median over stations)."""
    st = pd.read_csv(run_dir / "stations.csv", index_col=0)
    if classes:
        st = st[st["class"].isin(classes)]
    ser = pd.read_csv(run_dir / "station_series_mm.csv", index_col=0, parse_dates=True)
    ser = ser[[s for s in st.index if s in ser.columns]]
    st = st.loc[ser.columns]
    daily = pd.read_csv(gnss_cache / "gnss_enu_daily.csv.gz", parse_dates=["date"])
    gps = gnss_los_series(daily, st, ser.index)
    t = np.array([decimal_year(d.to_pydatetime()) for d in ser.index])

    # residual InSAR - GNSS per station, both zeroed at the start; a centred
    # 3-epoch median takes out single-day GNSS noise at the block edges
    gps = gps - gps.iloc[:5].mean()
    res = ser - gps
    res = (res - res.iloc[0]).rolling(3, center=True, min_periods=1).median()

    epochs = list_epochs(disp_dir)
    refs = sorted({e.ref for e in epochs})
    edges = [pd.Timestamp(r).normalize() for r in refs] + [ser.index[-1]]
    rows = []
    for ref, a, b in zip(refs, edges[:-1], edges[1:], strict=True):
        inside = (ser.index >= a) & (ser.index <= b)
        tb = t[inside]
        rates = [
            _slope(tb, ser[s].to_numpy()[inside], min_points)
            - _slope(tb, gps[s].to_numpy()[inside], min_points)
            for s in ser.columns
        ]
        rates = [x for x in rates if np.isfinite(x)]
        inc = (res.loc[b] - res.loc[a]).dropna()
        rows.append(
            {
                "reference_date": pd.Timestamp(ref).date(),
                "end_date": b.date(),
                "n_epochs": int(inside.sum()) - 1,
                "n_stations": len(inc),
                "rate_bias_mm_yr": float(np.median(rates)) if rates else np.nan,
                "drift_mm": float(inc.median()) if len(inc) else np.nan,
            }
        )
    blocks = pd.DataFrame(rows)
    full = [_slope(t, res[s].to_numpy(), min_points) for s in res.columns]
    full = [x for x in full if np.isfinite(x)]
    span = float(np.ptp(t))
    summary = {
        "chained_bias_mm_yr": float(np.median(full)) if full else np.nan,
        "block_drift_sum_mm": float(blocks["drift_mm"].sum()),
        "block_drift_rate_mm_yr": float(blocks["drift_mm"].sum() / span),
        "block_rate_bias_median_mm_yr": float(blocks["rate_bias_mm_yr"].median()),
        "n_stations": len(full),
    }
    return blocks, summary


def main() -> None:
    """Command line."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("disp_dir", type=Path)
    p.add_argument("gnss_cache", type=Path)
    p.add_argument("--classes", nargs="*", help="station classes, e.g. stable")
    a = p.parse_args()
    blocks, summary = bias_by_block(a.run_dir, a.disp_dir, a.gnss_cache, a.classes)
    suffix = "_" + "-".join(a.classes) if a.classes else ""
    blocks.to_csv(a.run_dir / f"bias_by_block{suffix}.csv", index=False)
    print(blocks.round(2).to_string(index=False))
    for k, v in summary.items():
        print(f"{k:34s} {v:.2f}" if isinstance(v, float) else f"{k:34s} {v}")


if __name__ == "__main__":
    main()
