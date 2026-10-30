# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""T46.3: edge-case assertions for the defo-area and event databases.

Two benchmark conditions (PRD section 2.7) that the gate does not cover:

1. **Central Valley** (`outside_station_change`): remove-restore re-fits the
   surface without the deforming areas. Stations far from them must not move:
   max |change| of the calibrated LOS velocity < `max_change` (0.5 mm/yr)
   at stations >= `min_distance_km` from every area. Closer stations may move,
   since the surface no longer carries the area's subsidence into them.
2. **Ridgecrest** (`step_across_rupture`, `identical`): for pairs spanning the
   event the calibration carries no coseismic step, |jump across the trace|
   < `max_step` (2 mm) in strips beside the rupture; pairs that do
   not span the event are bit-identical with and without the event database.

Inputs are products and validation runs made elsewhere (no cal-disp import).

    python studies/edge_cases.py cv --without RUN_A --with RUN_B \
        --areas defo_area_db.geojson --out cv.json
    python studies/edge_cases.py ridgecrest --with-event DIR_A --without-event DIR_B \
        --events event_db.geojson --event-id ridgecrest_2019_mw71 --out rc.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

EQUAL_AREA = CRS.from_epsg(6933)  # metres, for distances on any frame


def _to_metric(geom):
    tr = Transformer.from_crs(4326, EQUAL_AREA, always_xy=True).transform
    return shp_transform(tr, geom)


def outside_station_change(
    without: pd.DataFrame,
    with_areas: pd.DataFrame,
    areas: list,
    *,
    column: str = "med::calibrated",
    min_distance_km: float = 25.0,
    max_change: float = 0.5,
) -> dict:
    """Velocity change at stations away from the deforming areas.

    Parameters
    ----------
    without, with_areas : pd.DataFrame
        ``stations.csv`` of the runs without and with the area database,
        indexed by station, with ``lon``, ``lat`` and `column` (mm/yr).
    areas : list
        Shapely geometries of the deforming areas (lon/lat).
    column : str
        Calibrated velocity column.
    min_distance_km : float
        Stations at least this far from every area are asserted.
    max_change : float
        Bound on max |change| there (mm/yr).

    Returns
    -------
    dict
        ``passed``, ``max_abs_change``, ``n_asserted`` and a per-band table.

    """
    m = without[["lon", "lat", column]].join(
        with_areas[[column]], rsuffix="_with", how="inner"
    )
    m = m.dropna()
    union = _to_metric(unary_union(areas))
    pts = [_to_metric(Point(x, y)) for x, y in zip(m["lon"], m["lat"], strict=True)]
    m["inside"] = [union.contains(p) for p in pts]
    m["distance_km"] = [union.distance(p) / 1000.0 for p in pts]
    m["change"] = m[f"{column}_with"] - m[column]
    far = m[~m["inside"] & (m["distance_km"] >= min_distance_km)]
    bands = []
    for lo, hi in [(0, 10), (10, min_distance_km), (min_distance_km, math.inf)]:
        s = m[~m["inside"] & (m["distance_km"] >= lo) & (m["distance_km"] < hi)]
        bands.append(
            {
                "from_km": lo,
                "to_km": None if math.isinf(hi) else hi,
                "n": len(s),
                "max_abs_change": float(s["change"].abs().max()) if len(s) else None,
                "median_abs_change": (
                    float(s["change"].abs().median()) if len(s) else None
                ),
            }
        )
    worst = float(far["change"].abs().max()) if len(far) else math.nan
    return {
        "passed": bool(len(far) > 0 and worst < max_change),
        "max_abs_change": worst,
        "n_asserted": len(far),
        "n_inside": int(m["inside"].sum()),
        "min_distance_km": min_distance_km,
        "max_change": max_change,
        "bands": bands,
        "stations": m.round(3).reset_index().to_dict(orient="records"),
    }


def rupture_line(event: dict) -> LineString:
    """Rupture trace (lon/lat) through the epicentre along strike, length L."""
    p = event["properties"] if "properties" in event else event
    lon, lat = p["epicentre"]
    half = p["rupture_length_km"] * 500.0
    th = math.radians(p["strike_deg"])
    dx, dy = half * math.sin(th), half * math.cos(th)
    k = 1.0 / 111_320.0
    return LineString(
        [
            (lon - dx * k / math.cos(math.radians(lat)), lat - dy * k),
            (lon + dx * k / math.cos(math.radians(lat)), lat + dy * k),
        ]
    )


def step_across_rupture(
    cal: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    crs: CRS,
    rupture: LineString,
    *,
    near_km: float = 1.0,
    far_km: float = 5.0,
) -> float:
    """Jump of the calibration across the rupture trace.

    Pixels in two strips along the rupture's length, `near_km` to `far_km`
    from the trace on either side, are fitted with
    ``cal = c0 + c1 * across + jump * (across > 0)``: the linear term takes
    the smooth surface's slope across the trace (a plain median difference
    of the strips grows with their separation, about 0.5-1 mm/km on
    Ridgecrest), so `jump` is the discontinuity alone. Units are those of `cal`.
    """
    tr = Transformer.from_crs(4326, crs, always_xy=True).transform
    line = shp_transform(tr, rupture)
    (x0, y0), (x1, y1) = line.coords
    ux, uy = (x1 - x0) / line.length, (y1 - y0) / line.length
    xx, yy = np.meshgrid(x, y)
    along = (xx - x0) * ux + (yy - y0) * uy
    across = (xx - x0) * -uy + (yy - y0) * ux  # signed distance (m)
    on = (along >= 0) & (along <= line.length)
    a = np.abs(across)
    strip = on & (a >= near_km * 1000) & (a <= far_km * 1000) & np.isfinite(cal)
    d = across[strip] / 1000.0
    v = cal[strip]
    if not (d > 0).any() or not (d < 0).any():
        return math.nan
    g = np.column_stack([np.ones_like(d), d, (d > 0).astype(float)])
    coef, *_ = np.linalg.lstsq(g, v, rcond=None)
    return float(coef[2])


def identical(a: np.ndarray, b: np.ndarray) -> bool:
    """Bit-identical, NaN in the same places."""
    return bool(np.array_equal(a, b, equal_nan=True))


def spans(pair: str, t0: datetime) -> bool:
    """Whether a ``YYYYMMDD_YYYYMMDD`` pair brackets `t0` (by date)."""
    ref, sec = (datetime.strptime(d, "%Y%m%d") for d in pair.split("_"))
    return ref.date() < t0.date() <= sec.date()


def _read_cal(product_dir: Path):
    import xarray as xr

    nc = sorted(product_dir.glob("*.nc"))[0]
    with xr.open_dataset(nc) as ds:
        cal = ds["calibration"].isel(time=0).values.astype(np.float64)
        crs = CRS.from_wkt(ds["spatial_ref"].attrs["crs_wkt"])
        return cal, ds["x"].values, ds["y"].values, crs


def _cli_cv(a: argparse.Namespace) -> dict:
    feats = json.loads(Path(a.areas).read_text())["features"]
    res = outside_station_change(
        pd.read_csv(Path(a.without) / "stations.csv", index_col="station"),
        pd.read_csv(Path(a.with_) / "stations.csv", index_col="station"),
        [shape(f["geometry"]) for f in feats],
        min_distance_km=a.min_distance_km,
    )
    return res


def _cli_ridgecrest(a: argparse.Namespace) -> dict:
    feats = json.loads(Path(a.events).read_text())["features"]
    ev = next(f for f in feats if f["properties"]["id"] == a.event_id)
    t0 = datetime.fromisoformat(ev["properties"]["t0"])
    t_first = min(datetime.fromisoformat(f["properties"]["t0"]) for f in feats)
    line = rupture_line(ev)
    rows = []
    for d in sorted(Path(a.with_event).iterdir()):
        other = Path(a.without_event) / d.name
        if not other.is_dir():
            continue
        cal_w, x, y, crs = _read_cal(d)
        cal_n, *_ = _read_cal(other)
        span = spans(d.name, t_first) or spans(d.name, t0)
        row: dict[str, object] = {"pair": d.name, "spans_event": span}
        if span:
            step = 1000 * step_across_rupture(cal_w, x, y, crs, line)
            row["step_mm_with_event_db"] = step
            row["step_mm_without_event_db"] = 1000 * step_across_rupture(
                cal_n, x, y, crs, line
            )
            row["passed"] = abs(step) < a.max_step_mm
        else:
            row["identical"] = identical(cal_w, cal_n)
            row["max_abs_diff_mm"] = float(np.nanmax(np.abs(cal_w - cal_n)) * 1000)
            row["passed"] = row["identical"]
        rows.append(row)
    return {"passed": all(r["passed"] for r in rows), "pairs": rows}


def main() -> None:
    """Run the `cv` or `ridgecrest` check and write its JSON."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    cv = sub.add_parser("cv")
    cv.add_argument("--without", required=True, help="validation run dir, no area DB")
    cv.add_argument("--with", dest="with_", required=True, help="run dir, area DB")
    cv.add_argument("--areas", required=True)
    cv.add_argument("--min-distance-km", type=float, default=25.0)
    cv.add_argument("--out", required=True)
    rc = sub.add_parser("ridgecrest")
    rc.add_argument("--with-event", required=True, help="products dir, event DB")
    rc.add_argument("--without-event", required=True, help="products dir, no event DB")
    rc.add_argument("--events", required=True)
    rc.add_argument("--event-id", default="ridgecrest_2019_mw71")
    rc.add_argument("--max-step-mm", type=float, default=2.0)
    rc.add_argument("--out", required=True)
    a = p.parse_args()
    res = _cli_cv(a) if a.cmd == "cv" else _cli_ridgecrest(a)
    Path(a.out).write_text(json.dumps(res, indent=2, default=str))
    print(
        json.dumps(
            {
                k: v
                for k, v in res.items()
                if k in ("passed", "max_abs_change", "n_asserted", "bands")
            },
            indent=2,
        )
    )
    if a.cmd == "ridgecrest":
        for r in res["pairs"]:
            print(r)


if __name__ == "__main__":
    main()
