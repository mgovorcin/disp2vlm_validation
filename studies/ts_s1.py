# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-S1: DISP noise below the calibration cutoff (Venti plan T43, R-E2).

DISP-CAL removes wavelengths longer than ~50 km; what is left between two
points closer than that is DISP's own noise, which the product tells users to
add (a 10 mm placeholder today). Per frame, from a ``disp2vlm-validate run``:

1. double differences of (calibrated DISP - GNSS) LOS series for every
   station pair: ``rmse^2`` = var(DISP differential) + var(GNSS, station 1)
   + var(GNSS, station 2);
2. GNSS noise per station from the daily scatter (1.4826 MAD of first
   differences / sqrt 2), subtracted;
3. the DISP structure function ``S(d) = sqrt(median var)`` in distance bins,
   and the model ``S^2 = nugget^2 + c d^alpha`` fitted below `max_km`;
4. a proxy check: per station, the DISP residual scatter against the mean
   temporal coherence of its pixel (Spearman).

S(d) is the per-epoch noise of the displacement difference between two
points d apart; for one point against a perfect reference divide by sqrt 2.
The station series are 7 x 7 pixel medians, so S is the noise of a
~210 m average, a lower bound for a single 30 m pixel.

    python studies/ts_s1.py RUN_DIR GNSS_CACHE COHERENCE_TIF --frame F08882 --out OUT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from disp2vlm_validation.gnss import gnss_los_series
from disp2vlm_validation.metrics import double_differences

MAD_SCALE = 1.4826
BINS_KM = (0.5, 1, 2, 5, 10, 20, 35, 50, 100, 200, 400)


def gnss_daily_sigma(daily: pd.DataFrame, stations: pd.DataFrame) -> pd.Series:
    """White-noise sigma (mm, LOS) of each station's daily series."""
    d = daily[daily["station"].isin(stations.index)].copy()
    lv = stations.loc[d["station"], ["los_e", "los_n", "los_u"]].to_numpy()
    d["los"] = (lv * d[["east", "north", "up"]].to_numpy()).sum(axis=1) * 1000.0
    wide = d.pivot_table(index="date", columns="station", values="los").sort_index()
    dif = wide.diff()
    return (dif - dif.median()).abs().median() * MAD_SCALE / np.sqrt(2)


def disp_pair_variance(pairs: pd.DataFrame, sigma_gnss: pd.Series) -> pd.DataFrame:
    """Add ``var_disp = rmse^2 - sigma_g1^2 - sigma_g2^2`` to the DD pair table."""
    out = pairs.copy()
    g1 = out["station1"].map(sigma_gnss) ** 2
    g2 = out["station2"].map(sigma_gnss) ** 2
    out["var_gnss"] = g1 + g2
    out["var_disp"] = out["rmse"] ** 2 - out["var_gnss"]
    return out


def structure_function(pairs: pd.DataFrame, bins_km=BINS_KM) -> pd.DataFrame:
    """Median DISP differential variance per distance bin -> S(d) (mm)."""
    cut = pd.cut(pairs["distance_km"], bins_km)
    rows = []
    for b, g in pairs.groupby(cut, observed=True):
        v = float(np.median(g["var_disp"]))
        rows.append(
            {
                "bin_km": str(b),
                "distance_km": float(np.sqrt(b.left * b.right)),
                "n_pairs": len(g),
                "var_disp_mm2": v,
                "S_mm": float(np.sqrt(max(v, 0.0))),
                "median_var_gnss_mm2": float(np.median(g["var_gnss"])),
            }
        )
    return pd.DataFrame(rows)


def fit_model(
    sf: pd.DataFrame, max_km: float = 50.0, min_pairs: int = 20
) -> dict[str, float]:
    """``S^2 = nugget^2 + c d^alpha`` on bins below `max_km` (weighted by n).

    Bins with fewer than `min_pairs` pairs are left out: a handful of very
    close pairs (often co-located monuments) otherwise sets the nugget.
    """
    from scipy.optimize import curve_fit

    d = sf[(sf["distance_km"] <= max_km) & (sf["n_pairs"] >= min_pairs)]
    if len(d) < 3:
        return {"nugget_mm": np.nan, "c": np.nan, "alpha": np.nan, "n_bins": len(d)}

    def model(x, n2, c, a):
        return n2 + c * x**a

    p, _ = curve_fit(
        model,
        d["distance_km"],
        d["var_disp_mm2"],
        p0=(10.0, 1.0, 0.7),
        bounds=([0, 0, 0.05], [1e4, 1e4, 2.0]),
        sigma=1 / np.sqrt(d["n_pairs"]),
    )
    return {
        "nugget_mm": float(np.sqrt(p[0])),
        "c": float(p[1]),
        "alpha": float(p[2]),
        "n_bins": len(d),
        "S_at_10km_mm": float(np.sqrt(model(10.0, *p))),
        "S_at_50km_mm": float(np.sqrt(model(max_km, *p))),
    }


def pooled_s(pairs: pd.DataFrame, lo_km: float = 10.0, hi_km: float = 50.0) -> dict:
    """Model-free S over all pairs in (`lo_km`, `hi_km`]: sqrt(median var_disp)."""
    sel = pairs[(pairs["distance_km"] > lo_km) & (pairs["distance_km"] <= hi_km)]
    v = float(np.median(sel["var_disp"])) if len(sel) else np.nan
    return {
        "range_km": [lo_km, hi_km],
        "n_pairs": len(sel),
        "S_mm": float(np.sqrt(max(v, 0.0))) if len(sel) else np.nan,
        "S_point_mm": float(np.sqrt(max(v, 0.0) / 2)) if len(sel) else np.nan,
    }


def station_scatter(
    insar: pd.DataFrame, gps: pd.DataFrame, sigma_gnss: pd.Series
) -> pd.Series:
    """Per station: temporal std of (DISP - GNSS), GNSS noise removed (mm)."""
    r = insar - gps
    var = r.var() - sigma_gnss.reindex(r.columns) ** 2
    return np.sqrt(var.clip(lower=0))


def run(
    run_dir: Path, gnss_cache: Path, coherence_tif: Path, min_common_dates: int = 30
):
    """All of the above for one frame."""
    import rasterio

    st = pd.read_csv(run_dir / "stations.csv", index_col=0)
    ser = pd.read_csv(run_dir / "station_series_mm.csv", index_col=0, parse_dates=True)
    st = st.loc[[s for s in ser.columns if s in st.index]]
    ser = ser[st.index]
    daily = pd.read_csv(gnss_cache / "gnss_enu_daily.csv.gz", parse_dates=["date"])
    gps = gnss_los_series(daily, st, ser.index)
    sig_g = gnss_daily_sigma(daily, st)
    coords = {s: (float(st.at[s, "lon"]), float(st.at[s, "lat"])) for s in st.index}
    dd = double_differences(
        {"calibrated": ser}, gps, coords, min_common_dates=min_common_dates, n_boot=0
    )
    pairs = disp_pair_variance(dd.pairs["calibrated"], sig_g)
    sf = structure_function(pairs)
    with rasterio.open(coherence_tif) as ds:
        coh = ds.read(1)
    per_station = pd.DataFrame(
        {
            "scatter_mm": station_scatter(ser, gps, sig_g),
            "sigma_gnss_mm": sig_g.reindex(st.index),
            "coherence": coh[st["row"].to_numpy(), st["col"].to_numpy()],
            "class": st["class"],
        }
    ).dropna(subset=["scatter_mm", "coherence"])
    rho = per_station[["scatter_mm", "coherence"]].corr(method="spearman").iloc[0, 1]
    return pairs, sf, fit_model(sf), per_station, float(rho)


def main() -> None:
    """Command line."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("gnss_cache", type=Path)
    p.add_argument("coherence_tif", type=Path)
    p.add_argument("--frame", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    pairs, sf, model, per_station, rho = run(a.run_dir, a.gnss_cache, a.coherence_tif)
    a.out.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(a.out / "pairs_ts_s1.csv.gz", index=False)
    sf.to_csv(a.out / "structure_function.csv", index=False)
    per_station.to_csv(a.out / "stations_ts_s1.csv")
    summary = {
        "frame": a.frame,
        "model": model,
        "pooled_10_50km": pooled_s(pairs),
        "spearman_scatter_vs_coherence": rho,
        "n_pairs": len(pairs),
        "n_stations": len(per_station),
        "median_sigma_gnss_mm": float(per_station["sigma_gnss_mm"].median()),
        "median_station_scatter_mm": float(per_station["scatter_mm"].median()),
    }
    (a.out / "ts_s1.json").write_text(json.dumps(summary, indent=1))
    print(sf.round(2).to_string(index=False))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()


def plot_structure_functions(root: Path, frames: list[str], out: Path) -> None:
    """S(d) per frame (bins with >= 20 pairs), log distance axis."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator, ScalarFormatter

    from disp2vlm_validation.report import COLORS, INK_2

    colors = [*COLORS.values(), INK_2]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for fr, color in zip(frames, colors, strict=False):
        sf = pd.read_csv(root / fr / "structure_function.csv")
        sf = sf[sf["n_pairs"] >= 20]
        ax.plot(sf["distance_km"], sf["S_mm"], "-o", lw=2, ms=6, color=color, label=fr)
    ax.axvline(50, color=INK_2, lw=1, ls=":")
    ax.axhline(10, color=INK_2, lw=1, ls="--")
    ax.annotate("10 mm placeholder", (1.6, 10.2), color=INK_2, fontsize=8)
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([2, 5, 10, 20, 50, 100, 200]))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel("station separation (km)")
    ax.set_ylabel("S(d): DISP differential noise per epoch (mm)")
    ax.set_ylim(0, None)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "structure_functions.png", dpi=130)
    plt.close(fig)
