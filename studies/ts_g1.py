# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-G1: fidelity of the UNR grid at independent stations, and k per frame.

Venti plan T39, PRD section 7.2. No InSAR: the UNR constant grid is sampled
the way DISP-CAL samples it (`venti.gnss.sampling.sample_gnss_enu`, then the
per-pixel LOS projection) and compared, at each MIDAS station of the frame,
with the station's own LOS rate:

    r = v_grid - v_station,   z = r / sqrt((k sigma_grid)^2 + sigma_station^2)

k is the inflation of the grid sigma in sigma_CAL (R-E1). It is fitted on a
**held-out** station subset (`split_held_out`, so stations that set k never
validate it) such that std(z) = 1, and checked on the remaining stations.
Both a plain (std) and a robust (1.4826 MAD) k are reported: a few islands or
bad records can dominate the plain one.

The sampling needs Venti (run with cal-disp's env and ``PYTHONPATH`` set to
this repo's ``src``); the statistics below do not.

    python studies/ts_g1.py --frame F08882 --stations RUN/stations.csv \
        --midas CACHE/gnss_midas_enu.csv --los LOS.tif \
        --grid-lookup GNSS/grid_latlon_lookup_v0.3.txt --station-dir GNSS \
        --out studies/TS-G1/F08882
"""

from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

from disp2vlm_validation.gnss import split_held_out

MAD_SCALE = 1.4826
EARTH_KM = 6371.0
DISTANCE_BINS_KM = (0.0, 5.0, 10.0, 20.0, 40.0, np.inf)


def _spread(z: np.ndarray, robust: bool) -> float:
    z = z[np.isfinite(z)]
    if robust:
        return float(MAD_SCALE * np.median(np.abs(z - np.median(z))))
    return float(np.std(z, ddof=1))


def z_scores(
    r: np.ndarray, sigma_grid: np.ndarray, sigma_station: np.ndarray, k: float
) -> np.ndarray:
    """``r / sqrt((k sigma_grid)^2 + sigma_station^2)``."""
    s = np.sqrt((k * np.asarray(sigma_grid)) ** 2 + np.asarray(sigma_station) ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, np.asarray(r) / s, np.nan)


def fit_k(
    r: np.ndarray,
    sigma_grid: np.ndarray,
    sigma_station: np.ndarray,
    *,
    robust: bool = False,
    k_max: float = 100.0,
) -> float:
    """Smallest k >= 0 with spread(z) = 1 (bisection; spread falls as k grows).

    Returns 0 when the station sigma alone already explains the residuals,
    and `k_max` when even that does not.
    """

    def excess(k: float) -> float:
        return _spread(z_scores(r, sigma_grid, sigma_station, k), robust) - 1.0

    if excess(0.0) <= 0:
        return 0.0
    if excess(k_max) > 0:
        return k_max
    lo, hi = 0.0, k_max
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if excess(mid) > 0 else (lo, mid)
    return 0.5 * (lo + hi)


def nearest_km(
    lon: np.ndarray,
    lat: np.ndarray,
    lon2: np.ndarray,
    lat2: np.ndarray,
    exclude_self: bool = False,
) -> np.ndarray:
    """Great-circle distance from each point to the nearest of the second set."""
    p1 = np.radians(np.c_[lat, lon])[:, None, :]
    p2 = np.radians(np.c_[lat2, lon2])[None, :, :]
    d = p2 - p1
    a = (
        np.sin(d[..., 0] / 2) ** 2
        + np.cos(p1[..., 0]) * np.cos(p2[..., 0]) * np.sin(d[..., 1] / 2) ** 2
    )
    km = 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    if exclude_self:
        km = np.where(km < 1e-6, np.inf, km)
    return km.min(axis=1)


def summarize(df: pd.DataFrame, k: float) -> dict[str, float]:
    """Bias, RMSE, NMAD of r and z statistics at `k` for one station set."""
    r = df["r"].to_numpy()
    z = z_scores(r, df["sigma_grid"].to_numpy(), df["sigma_station"].to_numpy(), k)
    zf = z[np.isfinite(z)]
    return {
        "n": len(df),
        "bias": float(np.mean(r)),
        "rmse": float(np.sqrt(np.mean(r**2))),
        "nmad": _spread(r - np.median(r), robust=True),
        "median_sigma_grid": float(np.median(df["sigma_grid"])),
        "std_z": _spread(zf, robust=False) if zf.size > 2 else np.nan,
        "coverage95": float(np.mean(np.abs(zf) <= 1.96)) if zf.size else np.nan,
    }


def analyze(df: pd.DataFrame, held_out_fraction: float = 0.3) -> dict:
    """K on held-out stations, checked on the others; residuals by station spacing.

    `df` needs ``r, sigma_grid, sigma_station, nearest_station_km``, indexed by
    station id.
    """
    split = split_held_out(df.index.unique(), held_out_fraction=held_out_fraction)
    fit, val = df.loc[split.held_out], df.loc[split.validation]
    out: dict = {"n_fit": len(fit), "n_validation": len(val)}
    for robust in (False, True):
        name = "k_robust" if robust else "k_std"
        k = fit_k(fit["r"], fit["sigma_grid"], fit["sigma_station"], robust=robust)
        out[name] = k
        out[f"validation_at_{name}"] = summarize(val, k)
    out["all_at_k1"] = summarize(df, 1.0)
    bins = pd.cut(df["nearest_station_km"], DISTANCE_BINS_KM, right=False)
    out["by_spacing"] = [
        {
            "nearest_station_km": str(b),
            "n": len(g),
            "bias": float(g["r"].mean()) if len(g) else np.nan,
            "rmse": float(np.sqrt((g["r"] ** 2).mean())) if len(g) else np.nan,
            "median_sigma_grid": float(g["sigma_grid"].median()) if len(g) else np.nan,
        }
        for b, g in df.groupby(bins, observed=False)
    ]
    return out


DT_BINS_YEARS = (0.0, 0.1, 0.25, 0.5, 1.0, np.inf)


def pair_residuals(
    daily_los: pd.DataFrame,
    grid: pd.DataFrame,
    pairs: list[tuple[pd.Timestamp, pd.Timestamp]],
    half_window_days: int = 3,
) -> pd.DataFrame:
    """Pair-level residuals: grid rate x dt minus the station displacement.

    `daily_los` is dates x stations (mm, LOS). A station's position at a date
    is the median of the daily values within +-`half_window_days`; its
    sigma is the daily scatter (NMAD of first differences / sqrt 2) over the
    number of days in the window, for both dates. `grid` needs
    ``grid_los_mm_yr, sigma_grid`` per station (mm/yr). Rows are indexed by
    station, one per (station, pair) with both dates covered.
    """
    d = daily_los.sort_index()
    sigma_daily = (
        (d.diff().sub(d.diff().median())).abs().median() * MAD_SCALE / np.sqrt(2)
    )
    win = pd.Timedelta(days=half_window_days)
    rows = []
    for ref, sec in pairs:
        a = d.loc[ref - win : ref + win]
        b = d.loc[sec - win : sec + win]
        disp = b.median() - a.median()
        n_a, n_b = a.notna().sum(), b.notna().sum()
        dt = (sec - ref).days / 365.25
        sig = sigma_daily * np.sqrt(1 / n_a.clip(lower=1) + 1 / n_b.clip(lower=1))
        for st in grid.index.intersection(disp.dropna().index):
            rows.append(
                {
                    "station": st,
                    "ref": ref.date(),
                    "sec": sec.date(),
                    "dt_years": dt,
                    "r": grid.at[st, "grid_los_mm_yr"] * dt - disp[st],
                    "sigma_grid": grid.at[st, "sigma_grid"] * dt,
                    "sigma_station": sig[st],
                }
            )
    return pd.DataFrame(rows).set_index("station")


FIT_DT_BINS_YEARS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 1.0, np.inf)


def fit_additive(df: pd.DataFrame) -> tuple[float, float]:
    """``(sigma0, k)`` of ``var(r) = sigma0^2 + (k sigma_grid)^2 + sigma_station^2``.

    Least squares over dt bins of the robust residual variance (1.4826 MAD)^2
    minus the mean station variance, against the mean grid variance: a
    multiplicative k alone cannot fit pair residuals, which barely depend on
    dt (seasonal and other non-secular station motion).
    """
    g = df.groupby(
        pd.cut(df["dt_years"], FIT_DT_BINS_YEARS, right=False), observed=True
    )
    rv = g["r"].apply(lambda x: _spread(x.to_numpy(), robust=True) ** 2)
    sv = g["sigma_station"].apply(lambda x: float(np.mean(x**2)))
    gv = g["sigma_grid"].apply(lambda x: float(np.mean(x**2)))
    a = np.c_[np.ones(len(rv)), gv.to_numpy()]
    (c0, c1), *_ = np.linalg.lstsq(a, (rv - sv).to_numpy(), rcond=None)
    return float(np.sqrt(max(c0, 0.0))), float(np.sqrt(max(c1, 0.0)))


def z_additive(df: pd.DataFrame, sigma0: float, k: float) -> np.ndarray:
    """Z under the additive model."""
    s = np.sqrt(sigma0**2 + (k * df["sigma_grid"]) ** 2 + df["sigma_station"] ** 2)
    return (df["r"] / s).to_numpy()


def analyze_pairs(df: pd.DataFrame, held_out_fraction: float = 0.3) -> dict:
    """Fit k (overall, per dt bin) and the additive (sigma0, k) model.

    Fitted on held-out stations (all their pairs), checked on the others.
    """
    split = split_held_out(df.index.unique(), held_out_fraction=held_out_fraction)
    fit, val = df.loc[split.held_out], df.loc[split.validation]
    out: dict = {"n_pairs_fit": len(fit), "n_pairs_validation": len(val)}
    for robust in (False, True):
        name = "k_robust" if robust else "k_std"
        k = fit_k(fit["r"], fit["sigma_grid"], fit["sigma_station"], robust=robust)
        out[name] = k
        out[f"validation_at_{name}"] = summarize(val, k)
    rows = []
    for b, g in fit.groupby(
        pd.cut(fit["dt_years"], DT_BINS_YEARS, right=False), observed=True
    ):
        v = val[(val["dt_years"] >= b.left) & (val["dt_years"] < b.right)]
        k = fit_k(g["r"], g["sigma_grid"], g["sigma_station"])
        rows.append(
            {
                "dt_years": str(b),
                "n_fit": len(g),
                "k_std": k,
                "k_robust": fit_k(
                    g["r"], g["sigma_grid"], g["sigma_station"], robust=True
                ),
                "rmse_mm": float(np.sqrt((g["r"] ** 2).mean())),
                "validation_std_z": summarize(v, k)["std_z"] if len(v) > 2 else np.nan,
            }
        )
    out["by_dt"] = rows
    s0, k = fit_additive(fit)
    out["additive"] = {"sigma0_mm": s0, "k": k, "by_dt": []}
    for b, v in val.groupby(
        pd.cut(val["dt_years"], DT_BINS_YEARS, right=False), observed=True
    ):
        z = z_additive(v, s0, k)
        out["additive"]["by_dt"].append(
            {
                "dt_years": str(b),
                "n": len(v),
                "std_z": _spread(z, robust=False),
                "robust_std_z": _spread(z, robust=True),
                "coverage95": float(np.mean(np.abs(z) <= 1.96)),
            }
        )
    z = z_additive(val, s0, k)
    out["additive"]["validation"] = {
        "std_z": _spread(z, robust=False),
        "robust_std_z": _spread(z, robust=True),
        "coverage95": float(np.mean(np.abs(z) <= 1.96)),
    }
    return out


# ---------------------------------------------------------------- sampling


def sample_grid_at_stations(
    stations: pd.DataFrame,
    los_file: Path,
    grid_lookup: Path,
    station_dir: Path,
    *,
    buffer_m: float = 0.0,
    step_m: float = 500.0,
) -> pd.DataFrame:
    """Grid LOS rate and sigma at each station (needs Venti).

    The grid is sampled as DISP-CAL does (`sample_gnss_enu`), on a coarse
    `step_m` grid over the frame (the RBF field is smooth at that scale), and
    projected onto each station's own LOS vector.
    """
    import rasterio
    from pyproj import Transformer
    from venti.gnss.sampling import GnssGridConfig, sample_gnss_enu

    with rasterio.open(los_file) as ds:
        b, crs = ds.bounds, ds.crs
    x = np.arange(b.left + step_m / 2, b.right, step_m)
    y = np.arange(b.top - step_m / 2, b.bottom, -step_m)
    cfg = GnssGridConfig(
        grid_lookup=grid_lookup,
        station_dir=station_dir,
        utm_epsg=crs.to_epsg(),
        buffer_meters=buffer_m,
    )
    field = sample_gnss_enu(cfg, (x, y))
    sx, sy = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(
        stations["lon"].to_numpy(), stations["lat"].to_numpy()
    )
    col = np.clip(np.rint((sx - x[0]) / step_m).astype(int), 0, x.size - 1)
    row = np.clip(np.rint((y[0] - sy) / step_m).astype(int), 0, y.size - 1)
    e, n, u = (stations[f"los_{c}"].to_numpy() for c in "enu")

    def at(a: np.ndarray) -> np.ndarray:
        return a[row, col]

    out = pd.DataFrame(index=stations.index)
    out["grid_los_mm_yr"] = e * at(field.ve) + n * at(field.vn) + u * at(field.vu)
    out["sigma_grid"] = np.sqrt(
        (e * at(field.sigma_ve)) ** 2
        + (n * at(field.sigma_vn)) ** 2
        + (u * at(field.sigma_vu)) ** 2
    )
    out["grid_vu_mm_yr"] = at(field.vu)
    out["nearest_node_km"] = nearest_km(
        stations["lon"].to_numpy(),
        stations["lat"].to_numpy(),
        field.nodes["lon"].to_numpy(),
        field.nodes["lat"].to_numpy(),
    )
    out.attrs["n_nodes"] = len(field.nodes)
    out.attrs["provenance_digest"] = field.provenance.digest
    return out


def main() -> None:
    """Command line."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--frame", required=True)
    p.add_argument(
        "--stations", type=Path, required=True, help="disp2vlm-validate stations.csv"
    )
    p.add_argument(
        "--midas", type=Path, required=True, help="frame GNSS cache gnss_midas_enu.csv"
    )
    p.add_argument("--los", type=Path, required=True)
    p.add_argument("--grid-lookup", type=Path, required=True)
    p.add_argument("--station-dir", type=Path, required=True)
    p.add_argument("--buffer-m", type=float, default=0.0)
    p.add_argument("--held-out-fraction", type=float, default=0.3)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--daily", type=Path, help="gnss_enu_daily.csv.gz: also run the pair level"
    )
    p.add_argument("--disp-dir", type=Path, help="DISP stack: its (ref, sec) pairs")
    a = p.parse_args()

    st = pd.read_csv(a.stations, index_col=0)
    midas = pd.read_csv(a.midas, index_col=0)
    g = sample_grid_at_stations(
        st, a.los, a.grid_lookup, a.station_dir, buffer_m=a.buffer_m
    )
    e, n, u = (st[f"los_{c}"] for c in "enu")
    df = pd.DataFrame(
        {
            "class": st["class"],
            "station_los_mm_yr": st["gps_los_mm_yr"],
            "grid_los_mm_yr": g["grid_los_mm_yr"],
            "r": g["grid_los_mm_yr"] - st["gps_los_mm_yr"],
            "r_vu": g["grid_vu_mm_yr"] - st["vu_mm_yr"],
            "sigma_grid": g["sigma_grid"],
            "sigma_station": np.sqrt(
                (e * st["sigma_ve_mm_yr"]) ** 2
                + (n * st["sigma_vn_mm_yr"]) ** 2
                + (u * st["sigma_vu_mm_yr"]) ** 2
            ),
            "nearest_station_km": nearest_km(
                st["lon"].to_numpy(),
                st["lat"].to_numpy(),
                midas["lon"].to_numpy(),
                midas["lat"].to_numpy(),
                exclude_self=True,
            ),
            "nearest_node_km": g["nearest_node_km"],
        }
    ).dropna(subset=["r", "sigma_grid"])
    res = analyze(df, a.held_out_fraction)
    res.update(
        frame=a.frame,
        n_nodes=g.attrs["n_nodes"],
        grid_digest=g.attrs["provenance_digest"],
        buffer_m=a.buffer_m,
    )
    a.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out / "stations_ts_g1.csv")
    (a.out / "ts_g1.json").write_text(json.dumps(res, indent=1, default=float))
    print(
        json.dumps(
            {k: v for k, v in res.items() if k != "by_spacing"}, indent=1, default=float
        )
    )
    print(pd.DataFrame(res["by_spacing"]).round(2).to_string(index=False))

    if a.daily and a.disp_dir:
        from disp2vlm_validation.stack import list_epochs

        pairs = [
            (pd.Timestamp(e.ref).normalize(), pd.Timestamp(e.sec).normalize())
            for e in list_epochs(a.disp_dir)
        ]
        daily = pd.read_csv(a.daily, parse_dates=["date"])
        daily = daily[daily["station"].isin(df.index)]
        lv = st.loc[daily["station"], ["los_e", "los_n", "los_u"]].to_numpy()
        daily["los"] = (lv * daily[["east", "north", "up"]].to_numpy()).sum(
            axis=1
        ) * 1000.0
        wide = daily.pivot_table(index="date", columns="station", values="los")
        pr = pair_residuals(wide, df[["grid_los_mm_yr", "sigma_grid"]], pairs)
        pres = analyze_pairs(pr, a.held_out_fraction)
        pr.to_csv(a.out / "pairs_ts_g1.csv.gz")
        (a.out / "ts_g1_pairs.json").write_text(
            json.dumps(pres, indent=1, default=float)
        )
        print(
            "pair level:",
            json.dumps(
                {k: v for k, v in pres.items() if k != "by_dt"}, indent=1, default=float
            ),
        )
        print(pd.DataFrame(pres["by_dt"]).round(2).to_string(index=False))
        ad = pres["additive"]
        print(
            f"additive: sigma0 = {ad['sigma0_mm']:.2f} mm, k = {ad['k']:.2f};"
            f" validation {ad['validation']}"
        )
        print(pd.DataFrame(ad["by_dt"]).round(2).to_string(index=False))


if __name__ == "__main__":
    main()


def plot_frames(root: Path, frames: list[str], out: Path) -> None:
    """Figures across frames: residual maps, RMSE vs spacing, z histograms."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from disp2vlm_validation.report import COLORS, INK_2

    out.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, len(frames), figsize=(4.2 * len(frames), 4.0))
    for ax, fr in zip(np.atleast_1d(axes), frames, strict=True):
        df = pd.read_csv(root / fr / "stations_ts_g1.csv", index_col=0)
        lonlat = pd.read_csv(
            root.parent / "t38" / "runs" / fr / "v05-loclin" / "stations.csv",
            index_col=0,
        ).loc[df.index, ["lon", "lat"]]
        sc = ax.scatter(
            lonlat["lon"],
            lonlat["lat"],
            c=df["r"],
            cmap="RdBu_r",
            vmin=-5,
            vmax=5,
            s=36,
            edgecolor=INK_2,
            linewidth=0.4,
        )
        ax.set_title(f"{fr}: grid - station LOS (mm/yr)", fontsize=10)
        ax.set_aspect(1 / np.cos(np.radians(lonlat["lat"].mean())))
        ax.tick_params(labelsize=8)
    fig.colorbar(sc, ax=axes, shrink=0.8, label="mm/yr")
    fig.savefig(out / "residual_maps.png", dpi=130)
    plt.close(fig)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    for i, fr in enumerate(frames):
        res = json.loads((root / fr / "ts_g1.json").read_text())
        sp = pd.DataFrame(res["by_spacing"])
        x = np.arange(len(sp)) + (i - 1.5) * 0.18
        a1.bar(
            x,
            sp["rmse"],
            width=0.18,
            label=fr,
            color=list(COLORS.values())[i % 3] if i < 3 else INK_2,
        )
        a1.set_xticks(
            np.arange(len(sp)),
            [f"{lo:g}-{hi:g}" for lo, hi in pairwise(DISTANCE_BINS_KM)],
            fontsize=8,
        )
        pr = pd.read_csv(root / fr / "pairs_ts_g1.csv.gz", index_col=0)
        ad = json.loads((root / fr / "ts_g1_pairs.json").read_text())["additive"]
        z = z_additive(pr, ad["sigma0_mm"], ad["k"])
        a2.hist(
            np.clip(z, -6, 6),
            bins=60,
            histtype="step",
            density=True,
            lw=1.6,
            label=fr,
            color=list(COLORS.values())[i % 3] if i < 3 else INK_2,
        )
    zz = np.linspace(-6, 6, 200)
    a2.plot(
        zz,
        np.exp(-(zz**2) / 2) / np.sqrt(2 * np.pi),
        color=INK_2,
        ls=":",
        label="N(0, 1)",
    )
    a1.set_xlabel("distance to the nearest other station (km)")
    a1.set_ylabel("velocity RMSE, grid - station (mm/yr)")
    a2.set_xlabel("pair z, additive model (clipped at 6)")
    a1.legend(frameon=False, fontsize=8)
    a2.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "rmse_spacing_z.png", dpi=130)
    plt.close(fig)
