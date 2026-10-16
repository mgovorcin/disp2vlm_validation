# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
r"""TS-E4 addendum: sigma realism where sigma_CAL is extrapolated (2026-10-15).

Since cal-disp v0.5.0, sigma_CAL has a value wherever the calibration has one
(Venti ``uncertainty.extrapolate_sigma``): where the loclin fit had too
little weight, the nearest fitted value grows with the distance. This splits
the TS-E4 station-pairs of a frame into those whose sigma_CAL was fitted and
those that are extrapolated (no sigma in a product written without the
option), and reports the realism of each.

    python studies/ts_e4_extrapolated.py RUN_DIR CAL_DIR DISP_DIR GNSS_CACHE \\
        OLD_CAL_DIR --frame F08882 --sigma-disp-mm 10 --out OUT
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ts_e4 import realism, run, sample_std

from disp2vlm_validation.stack import list_epochs


def mark_extrapolated(long: pd.DataFrame, old_sigma: pd.DataFrame) -> pd.Series:
    """Mark the (ref, sec, station) rows without sigma in the older product.

    `old_sigma` is `ts_e4.sample_std` of products written without
    extrapolation (pairs as rows, stations as columns).
    """
    old = old_sigma.stack(future_stack=True).reindex(long.index)
    return pd.Series(old.isna().to_numpy(), index=long.index, name="extrapolated")


def split_realism(
    long: pd.DataFrame, extrapolated: pd.Series, sigma_disp_mm: float
) -> dict[str, Any]:
    """Realism of the full user budget for fitted and extrapolated rows."""
    full = np.sqrt(long.sigma_cal**2 + sigma_disp_mm**2 + long.sigma_gnss**2)
    out: dict[str, Any] = {}
    for name, m in (("fitted", ~extrapolated), ("extrapolated", extrapolated)):
        sub = long[m]
        out[name] = {
            "station_pairs": int(m.sum()),
            "stations": int(sub.index.get_level_values(2).nunique()),
            "median_sigma_cal_mm": float(sub.sigma_cal.median()),
            "median_abs_residual_mm": float(sub.r.abs().median()),
            "full_budget": realism((long.r / full)[m]),
        }
    return out


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("run_dir", "cal_dir", "disp_dir", "gnss_cache", "old_cal_dir"):
        p.add_argument(name, type=Path)
    p.add_argument("--frame", required=True)
    p.add_argument("--sigma-disp-mm", type=float, default=10.0)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    long, _ = run(a.run_dir, a.cal_dir, a.disp_dir, a.gnss_cache, a.sigma_disp_mm)
    st = pd.read_csv(a.run_dir / "stations.csv", index_col=0)
    st = st.loc[long.index.get_level_values(2).unique()]
    st[["row", "col"]] = st[["row", "col"]].astype(int)
    old_files = {
        (pd.Timestamp(e.ref).normalize(), pd.Timestamp(e.sec).normalize()): e.cal
        for e in list_epochs(a.disp_dir, a.old_cal_dir, allow_partial=True)
        if e.cal is not None
    }
    ext = mark_extrapolated(long, sample_std(old_files, st))
    summary = {"frame": a.frame, **split_realism(long, ext, a.sigma_disp_mm)}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
