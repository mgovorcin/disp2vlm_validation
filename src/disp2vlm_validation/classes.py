# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Station classes and per-class metrics (PRD section 3.4; plan T22).

A station gets the first class that applies, in this order:

1. ``near_event``: inside an event area of the event GeoJSON;
2. ``defo_area``: inside a deforming area of the defo GeoJSON;
3. ``subsiding``: GNSS vertical rate below `subsiding_mm_yr`;
4. ``coastal``: within `coast_km` of the sea: a water body of the DISP water
   mask of at least `sea_min_km2` (bays and tidal channels joined to it
   count; ponds, lakes and rivers do not; ``sea_min_km2=0`` is any water);
5. ``stable``: everything else.

Metrics per class compare InSAR and GNSS velocities and, when sigmas are
given, report sigma realism: ``z = residual / sqrt(sigma_insar^2 +
sigma_gnss^2)`` should have std near 1 and ~95% of |z| below 1.96 (R-E4,
report only).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "CLASS_ORDER",
    "classify_stations",
    "load_polygons",
    "metrics_by_class",
    "normalized_residuals",
    "sea_mask",
]

CLASS_ORDER = ("near_event", "defo_area", "subsiding", "coastal", "stable")


def load_polygons(path: Path | str | None) -> list:
    """Shapely geometries of a GeoJSON FeatureCollection (EPSG:4326)."""
    if path is None:
        return []
    from shapely.geometry import shape

    data = json.loads(Path(path).read_text())
    return [shape(f["geometry"]) for f in data.get("features", [])]


def _inside(stations: pd.DataFrame, polygons: Sequence) -> np.ndarray:
    if not polygons:
        return np.zeros(len(stations), dtype=bool)
    from shapely import contains_xy, union_all

    return np.asarray(
        contains_xy(
            union_all(list(polygons)),
            stations["lon"].to_numpy(),
            stations["lat"].to_numpy(),
        ),
        dtype=bool,
    )


def sea_mask(land: np.ndarray, pixel_m: float, sea_min_km2: float) -> np.ndarray:
    """Water bodies of at least `sea_min_km2` (8-connected); all water if 0.

    On the four validation frames the seas are 900-15 000 km^2 (Gulf of
    Mexico, Galveston Bay, Pacific, Atlantic and Long Island Sound) while the
    largest inland water body is ~300 km^2 (Oklahoma City has ~20 000 small
    ones), so 500 km^2 separates them.
    """
    from scipy.ndimage import label

    water = ~np.asarray(land, dtype=bool)
    if sea_min_km2 <= 0 or not water.any():
        return water
    lab, n = label(water, structure=np.ones((3, 3), dtype=bool))
    area_km2 = np.bincount(lab.ravel(), minlength=n + 1) * (pixel_m / 1000.0) ** 2
    big = np.flatnonzero(area_km2 >= sea_min_km2)
    big = big[big > 0]
    return np.isin(lab, big)


def _distance_to_water_km(
    stations: pd.DataFrame,
    land: np.ndarray,
    pixel_m: float,
    sea_min_km2: float = 0.0,
) -> np.ndarray:
    from scipy.ndimage import distance_transform_edt

    water = sea_mask(land, pixel_m, sea_min_km2)
    if not water.any():
        return np.full(len(stations), np.inf)
    dist_px = distance_transform_edt(~water)
    return (
        dist_px[stations["row"].to_numpy(), stations["col"].to_numpy()]
        * pixel_m
        / 1000.0
    )


def classify_stations(
    stations: pd.DataFrame,
    *,
    defo_areas: Sequence = (),
    events: Sequence = (),
    land: np.ndarray | None = None,
    pixel_m: float = 30.0,
    subsiding_mm_yr: float = -3.0,
    coast_km: float = 10.0,
    sea_min_km2: float = 500.0,
) -> pd.Series:
    """Class of every station (see the module docstring for the order).

    `stations` needs ``lon, lat, vu_mm_yr`` and, for the coastal class,
    ``row, col`` on the grid of `land` (True = land).
    """
    cls = pd.Series("stable", index=stations.index, dtype=object)
    coastal = (
        _distance_to_water_km(stations, land, pixel_m, sea_min_km2) <= coast_km
        if land is not None
        else np.zeros(len(stations), dtype=bool)
    )
    subsiding = stations["vu_mm_yr"].to_numpy() < subsiding_mm_yr
    # assign from the lowest priority up, so the first class in CLASS_ORDER wins
    cls[coastal] = "coastal"
    cls[subsiding] = "subsiding"
    cls[_inside(stations, defo_areas)] = "defo_area"
    cls[_inside(stations, events)] = "near_event"
    return cls


def normalized_residuals(
    residual: np.ndarray,
    sigma_insar: np.ndarray | float,
    sigma_gnss: np.ndarray | float,
) -> np.ndarray:
    """``residual / sqrt(sigma_insar^2 + sigma_gnss^2)`` (NaN where sigma is 0)."""
    s = np.sqrt(
        np.asarray(sigma_insar, float) ** 2 + np.asarray(sigma_gnss, float) ** 2
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, np.asarray(residual, float) / s, np.nan)


def metrics_by_class(
    insar: np.ndarray,
    gnss: np.ndarray,
    classes: pd.Series,
    *,
    sigma_insar: np.ndarray | float | None = None,
    sigma_gnss: np.ndarray | float | None = None,
) -> pd.DataFrame:
    """``class, n, bias, median, rmse, corr, std_z, coverage95`` per class and ``all``.

    ``bias`` is the mean residual, ``median`` the median one.
    """
    insar = np.asarray(insar, float)
    gnss = np.asarray(gnss, float)
    ok = np.isfinite(insar) & np.isfinite(gnss)
    res = insar - gnss
    z = (
        normalized_residuals(res, sigma_insar, sigma_gnss)
        if sigma_insar is not None and sigma_gnss is not None
        else np.full(res.shape, np.nan)
    )
    labels = classes.to_numpy()
    rows = []
    for name in (*CLASS_ORDER, "all"):
        sel = ok & ((labels == name) if name != "all" else True)
        n = int(sel.sum())
        row = {"class": name, "n": n}
        if n >= 1:
            r = res[sel]
            row["bias"] = float(np.mean(r))
            row["median"] = float(np.median(r))
            row["rmse"] = float(np.sqrt(np.mean(r**2)))
        if n >= 3 and np.std(insar[sel]) > 0 and np.std(gnss[sel]) > 0:
            row["corr"] = float(np.corrcoef(insar[sel], gnss[sel])[0, 1])
        zs = z[sel]
        zs = zs[np.isfinite(zs)]
        if zs.size >= 3:
            row["std_z"] = float(np.std(zs, ddof=1))
            row["coverage95"] = float(np.mean(np.abs(zs) <= 1.96))
        rows.append(row)
    return pd.DataFrame(rows).set_index("class")
