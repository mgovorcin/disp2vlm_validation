# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-E4: sigma realism of the DISP-CAL product (PRD R-E4, Venti plan T50.2).

TS-G1 checked the grid part of sigma_CAL against held-out stations. This
checks the product a user receives. For every DISP pair and every GNSS
station outside deforming areas and event footprints:

    r = calibrated pair displacement at the station - GNSS pair displacement
    z = r / sqrt(sigma_CAL^2 + sigma_DISP^2 + sigma_GNSS^2 [+ sigma_0^2])

- calibrated pair: from the validation run's chained station series (7 x 7
  pixel medians), series(sec) - series(ref) within the pair's block;
- sigma_CAL: the product's `calibration_std` at the station (3 x 3 median);
- sigma_DISP: DISP noise below the calibration cutoff per point and pair,
  the term R-E2 tells users to add (TS-S1: 3.9-6.8 mm);
- sigma_GNSS: the station's daily white-noise sigma (TS-S1 estimator)
  through the +-3-day medians of both dates;
- sigma_0: the opt-in non-secular term (TS-G1: 2.6-4.9 mm), reported as a
  variant.

R-E4 (reported, not gated): std(z) in [0.8, 1.25] and 95% coverage in
[90%, 98%].

    python studies/ts_e4.py RUN_DIR CAL_DIR DISP_DIR GNSS_CACHE --frame F08882 \
        --sigma-disp-mm 6.8 --out OUT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd

from disp2vlm_validation.stack import list_epochs

MAD_SCALE = 1.4826
#: efficiency of a median of n daily values vs their mean (large n)
MEDIAN_EFF = 1.2533
GATED_OUT = ("defo_area", "near_event")


def pair_table(series: pd.DataFrame, pairs: list[tuple[pd.Timestamp, pd.Timestamp]]):
    """Per (ref, sec): series(sec) - series(ref), stations as columns."""
    rows = {
        (r, s): series.loc[s] - series.loc[r]
        for r, s in pairs
        if r in series.index and s in series.index
    }
    out = pd.DataFrame(rows).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["ref", "sec"])
    return out


def gnss_pair_table(wide: pd.DataFrame, pairs, half_window_days: int = 3):
    """GNSS LOS displacement per pair from +-`half_window_days` medians."""
    w = pd.Timedelta(days=half_window_days)
    rows = {
        (r, s): wide.loc[s - w : s + w].median() - wide.loc[r - w : r + w].median()
        for r, s in pairs
    }
    out = pd.DataFrame(rows).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["ref", "sec"])
    return out


def sigma_gnss_pair(sigma_daily: pd.Series, half_window_days: int = 3) -> pd.Series:
    """Sigma of a difference of two +-window medians of daily white noise."""
    n = 2 * half_window_days + 1
    return sigma_daily * MEDIAN_EFF * np.sqrt(2.0 / n)


def sample_std(cal_files: dict, stations: pd.DataFrame) -> pd.DataFrame:
    """`calibration_std` (mm) per (ref, sec) at each station (3 x 3 median)."""
    r, c = stations["row"].to_numpy(), stations["col"].to_numpy()
    rows = {}
    for key, path in cal_files.items():
        with h5py.File(path, "r") as f:
            d = f["calibration_std"]
            ny, nx = d.shape[-2:]
            vals = []
            for i, j in zip(r, c, strict=True):
                w = d[0, max(i - 1, 0) : min(i + 2, ny), max(j - 1, 0) : min(j + 2, nx)]
                vals.append(np.nanmedian(w) if np.isfinite(w).any() else np.nan)
        rows[key] = np.asarray(vals) * 1000.0
    out = pd.DataFrame(rows, index=stations.index).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["ref", "sec"])
    return out


def realism(z: np.ndarray) -> dict[str, float]:
    """std(z), robust std(z) and |z| < 1.96 coverage; R-E4 verdict."""
    z = np.asarray(z, float)
    z = z[np.isfinite(z)]
    if z.size == 0:
        return {"n": 0}
    std = float(np.std(z))
    rstd = float(MAD_SCALE * np.median(np.abs(z - np.median(z))))
    cov = float(np.mean(np.abs(z) < 1.96))
    return {
        "n": int(z.size),
        "std_z": std,
        "robust_std_z": rstd,
        "coverage95": cov,
        "meets_R_E4": bool(0.8 <= rstd <= 1.25 and 0.90 <= cov <= 0.98),
    }


def run(
    run_dir: Path,
    cal_dir: Path,
    disp_dir: Path,
    gnss_cache: Path,
    sigma_disp_mm: float,
    *,
    sigma0_mm: float = 3.5,
) -> tuple[pd.DataFrame, dict]:
    """Per-pair residuals and the realism of four sigma budgets."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from ts_s1 import gnss_daily_sigma  # the TS-S1 estimator

    st = pd.read_csv(run_dir / "stations.csv", index_col=0)
    st = st[~st["class"].isin(GATED_OUT)]
    series = pd.read_csv(
        run_dir / "station_series_mm.csv", index_col=0, parse_dates=True
    )
    st = st.loc[[s for s in st.index if s in series.columns]]
    epochs = list_epochs(disp_dir, cal_dir)
    pairs = [
        (pd.Timestamp(e.ref).normalize(), pd.Timestamp(e.sec).normalize())
        for e in epochs
    ]
    cal = pair_table(series[st.index], pairs)
    daily = pd.read_csv(gnss_cache / "gnss_enu_daily.csv.gz", parse_dates=["date"])
    daily = daily[daily["station"].isin(st.index)]
    lv = st.loc[daily["station"], ["los_e", "los_n", "los_u"]].to_numpy()
    daily = daily.assign(
        los=(lv * daily[["east", "north", "up"]].to_numpy()).sum(axis=1) * 1000.0
    )
    wide = daily.pivot_table(index="date", columns="station", values="los").sort_index()
    gnss = gnss_pair_table(wide, list(cal.index)).reindex(
        index=cal.index, columns=cal.columns
    )
    s_g = sigma_gnss_pair(gnss_daily_sigma(daily, st)).reindex(st.index)
    files = {
        (pd.Timestamp(e.ref).normalize(), pd.Timestamp(e.sec).normalize()): e.cal
        for e in epochs
        if e.cal is not None
    }
    s_cal = sample_std(files, st).reindex(index=cal.index, columns=cal.columns)

    long = pd.DataFrame(
        {
            "r": (cal - gnss).stack(future_stack=True),
            "sigma_cal": s_cal.stack(future_stack=True),
        }
    )
    long["sigma_gnss"] = s_g.reindex(long.index.get_level_values(2)).to_numpy()
    long["dt_years"] = [(s - r).days / 365.25 for r, s, _ in long.index]
    long = long.dropna(subset=["r", "sigma_cal"])
    budgets = {
        "sigma_CAL only": np.sqrt(long.sigma_cal**2),
        "+ sigma_DISP": np.sqrt(long.sigma_cal**2 + sigma_disp_mm**2),
        "+ sigma_DISP + sigma_GNSS": np.sqrt(
            long.sigma_cal**2 + sigma_disp_mm**2 + long.sigma_gnss**2
        ),
        "+ sigma_DISP + sigma_GNSS + sigma_0": np.sqrt(
            long.sigma_cal**2 + sigma_disp_mm**2 + long.sigma_gnss**2 + sigma0_mm**2
        ),
    }
    summary: dict[str, Any] = {name: realism(long.r / s) for name, s in budgets.items()}
    summary["by_span_full_budget"] = {
        f"{lo}-{hi} yr": realism(
            (long.r / budgets["+ sigma_DISP + sigma_GNSS"])[
                (long.dt_years >= lo) & (long.dt_years < hi)
            ]
        )
        for lo, hi in ((0, 0.25), (0.25, 1), (1, 3), (3, 10))
    }
    summary["median_sigma_cal_mm"] = float(long.sigma_cal.median())
    summary["median_sigma_gnss_mm"] = float(long.sigma_gnss.median())
    summary["sigma_disp_mm"] = sigma_disp_mm
    summary["sigma0_mm"] = sigma0_mm
    summary["n_stations"] = len(st)
    return long, summary


def main() -> None:
    """Command line."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("run_dir", "cal_dir", "disp_dir", "gnss_cache"):
        p.add_argument(name, type=Path)
    p.add_argument("--frame", required=True)
    p.add_argument("--sigma-disp-mm", type=float, default=7.0)
    p.add_argument("--sigma0-mm", type=float, default=3.5)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    long, summary = run(
        a.run_dir,
        a.cal_dir,
        a.disp_dir,
        a.gnss_cache,
        a.sigma_disp_mm,
        sigma0_mm=a.sigma0_mm,
    )
    a.out.mkdir(parents=True, exist_ok=True)
    long.to_csv(a.out / "pairs_ts_e4.csv.gz")
    (a.out / "ts_e4.json").write_text(
        json.dumps({"frame": a.frame, **summary}, indent=1)
    )
    print(json.dumps({"frame": a.frame, **summary}, indent=1))


if __name__ == "__main__":
    main()
