# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Independent GNSS: UNR daily stations, MIDAS rates, LOS projection, sampling.

Only daily station positions and their MIDAS rates are used, never the UNR
gridded field the calibration is fitted to (``GATE.independent_gnss_only``).
Ported from ``trade studies/e2e_validation/validate_stack.py`` (plan T21.2,
T21.3).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "StationSampler",
    "StationSplit",
    "fetch_gnss",
    "gnss_los_series",
    "load_or_fetch_gnss",
    "split_held_out",
    "station_pixels",
]

DAYS_PER_YEAR = 365.25


def fetch_gnss(
    bbox: Sequence[float], min_span_years: float = 2.0, max_workers: int = 8
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """UNR stations in `bbox` (W, S, E, N): MIDAS ENU rates and daily ENU series.

    Returns
    -------
    midas : DataFrame
        Index ``station``; ``lon, lat, v{e,n,u}_mm_yr, sigma_v{e,n,u}_mm_yr,
        n_gps_epochs, span_years, first, last`` (IGS20).
    daily : DataFrame
        ``station, date, east, north, up`` in metres, zeroed by the mean.

    """
    from geepers.gps_sources.unr import UnrSource
    from geepers.midas import midas

    gps = UnrSource().timeseries_many(
        bbox=tuple(bbox), frame="ENU", zero_by="mean", max_workers=max_workers
    )
    rows = {}
    for sid, group in gps.groupby("id"):
        d = group.sort_values("date")
        span = (d["date"].max() - d["date"].min()).days / DAYS_PER_YEAR
        if len(d) < 2 or span < min_span_years:
            continue
        t = (d["date"] - d["date"].iloc[0]).dt.total_seconds().to_numpy() / 86400.0
        t = t / DAYS_PER_YEAR
        row = {"lon": float(d["lon"].iloc[0]), "lat": float(d["lat"].iloc[0])}
        for comp, k in (("east", "e"), ("north", "n"), ("up", "u")):
            r = midas(t, d[comp].to_numpy())
            row[f"v{k}_mm_yr"] = r.velocity * 1000.0
            row[f"sigma_v{k}_mm_yr"] = r.velocity_uncertainty * 1000.0
        if all(np.isfinite(row[f"v{k}_mm_yr"]) for k in "enu"):
            row.update(
                n_gps_epochs=len(d),
                span_years=span,
                first=d["date"].min().date(),
                last=d["date"].max().date(),
            )
            rows[sid] = row
    midas_df = pd.DataFrame.from_dict(rows, orient="index").rename_axis("station")
    daily = pd.DataFrame(gps[["id", "date", "east", "north", "up"]]).rename(
        columns={"id": "station"}
    )
    return midas_df, daily[daily["station"].isin(midas_df.index)]


def load_or_fetch_gnss(
    cache_dir: Path | str,
    bbox: Sequence[float],
    *,
    min_span_years: float = 2.0,
    refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MIDAS and daily GNSS, frozen in `cache_dir` on first use.

    Every run of a frame is then compared with the same GNSS numbers; the
    trade-study cache layout (``gnss_midas_enu.csv``,
    ``gnss_enu_daily.csv.gz``) is read as is.
    """
    cache = Path(cache_dir)
    midas_csv = cache / "gnss_midas_enu.csv"
    daily_csv = cache / "gnss_enu_daily.csv.gz"
    if refresh or not (midas_csv.exists() and daily_csv.exists()):
        cache.mkdir(parents=True, exist_ok=True)
        midas_df, daily = fetch_gnss(bbox, min_span_years)
        midas_df.to_csv(midas_csv)
        daily.to_csv(daily_csv, index=False)
    return (
        pd.read_csv(midas_csv, index_col=0),
        pd.read_csv(daily_csv, parse_dates=["date"]),
    )


def station_pixels(
    stations: pd.DataFrame, crs: object, transform: object, los: np.ndarray
) -> pd.DataFrame:
    """Locate stations on the DISP grid and project MIDAS rates onto the LOS.

    `los` is the 3-band ``(east, north, up)`` LOS unit-vector stack of the
    DISP-S1-STATIC product on the same grid. Stations outside the frame or
    without a look are dropped. Adds ``row, col, los_{e,n,u},
    gps_hz_los_mm_yr, gps_los_mm_yr``.
    """
    import rasterio.transform
    from pyproj import Transformer

    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = to_xy.transform(stations["lon"].to_numpy(), stations["lat"].to_numpy())
    rows, cols = rasterio.transform.rowcol(transform, xs, ys)
    st = stations.copy()
    st["row"], st["col"] = np.asarray(rows), np.asarray(cols)
    ny, nx = los.shape[1:]
    inside = (st["row"] >= 0) & (st["row"] < ny) & (st["col"] >= 0) & (st["col"] < nx)
    st = st[inside].copy()
    for k, b in zip("enu", range(3), strict=True):
        st[f"los_{k}"] = los[b, st["row"].to_numpy(), st["col"].to_numpy()]
    st = st[np.isfinite(st["los_u"]) & (st["los_u"] != 0)].copy()
    st["gps_hz_los_mm_yr"] = st["los_e"] * st["ve_mm_yr"] + st["los_n"] * st["vn_mm_yr"]
    st["gps_los_mm_yr"] = st["gps_hz_los_mm_yr"] + st["los_u"] * st["vu_mm_yr"]
    return st


def gnss_los_series(
    daily: pd.DataFrame, stations: pd.DataFrame, dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """GNSS LOS displacement (mm) at the acquisition dates: dates x stations."""
    d = daily[daily["station"].isin(stations.index)].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    e, n, u = (d["station"].map(stations[f"los_{k}"]) for k in "enu")
    d["los"] = (e * d["east"] + n * d["north"] + u * d["up"]) * 1000.0
    wide = d.pivot_table(index="date", columns="station", values="los", aggfunc="mean")
    return wide.reindex(index=dates, columns=stations.index)


class StationSampler:
    """Median of the valid (land, finite) pixels in a window around each station."""

    def __init__(
        self,
        stations: pd.DataFrame,
        shape: tuple[int, int],
        land: np.ndarray,
        window: int = 7,
        min_pixels: int = 10,
    ) -> None:
        h = window // 2
        ny, nx = shape
        self.stations = list(stations.index)
        self.windows = [
            (
                slice(max(r - h, 0), min(r + h + 1, ny)),
                slice(max(c - h, 0), min(c + h + 1, nx)),
            )
            for r, c in zip(stations["row"], stations["col"], strict=True)
        ]
        self.land = [land[w] for w in self.windows]
        self.min_pixels = min_pixels

    def __call__(self, arr: np.ndarray) -> np.ndarray:
        """One value per station; NaN with fewer than `min_pixels` valid pixels."""
        out = np.full(len(self.windows), np.nan)
        for i, (w, land) in enumerate(zip(self.windows, self.land, strict=True)):
            v = arr[w][land]
            v = v[np.isfinite(v)]
            if v.size >= self.min_pixels:
                out[i] = np.median(v)
        return out


@dataclass(frozen=True)
class StationSplit:
    """Validation stations and the held-out ones (for fitting, e.g. TS-G1's k)."""

    validation: list[str]
    held_out: list[str]
    excluded: list[str]


def split_held_out(
    stations: Iterable[str],
    *,
    exclude: Iterable[str] = (),
    held_out_fraction: float = 0.0,
    seed: str = "disp2vlm",
) -> StationSplit:
    """Split stations into validation and held-out sets, deterministically.

    `exclude` (config, not code: e.g. ``UH01``, a bad record) never enters
    either set. The held-out choice hashes each station id with `seed`, so it
    is stable across runs and machines and independent of the station order:
    stations used to fit parameters (TS-G1) can never enter validation.
    """
    if not 0.0 <= held_out_fraction < 1.0:
        msg = "held_out_fraction must be in [0, 1)"
        raise ValueError(msg)
    excluded = sorted(set(exclude))
    validation: list[str] = []
    held: list[str] = []
    for s in stations:
        if s in excluded:
            continue
        h = int(hashlib.sha256(f"{seed}:{s}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        (held if h < held_out_fraction else validation).append(s)
    return StationSplit(sorted(validation), sorted(held), excluded)
