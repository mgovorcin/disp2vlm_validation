# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""VLM validation against independent GNSS (Venti plan T57).

A VLM run (opera_vlm) writes one product per target pair ``(T0, Tk)``, all
sharing ``T0``, with ``vertical``, ``vertical_std``, ``east``, ``mode``. For
every product and every GNSS station inside it:

- **pair residuals**: product (3 x 3 pixel median at the station) minus the
  GNSS displacement over the same span (median of the daily solutions within
  `half_window_days` of ``T0`` and of ``Tk``), vertical and east;
- **station rates**: the slope of the product's vertical series against time
  minus the slope of the GNSS up series at the same epochs; the gate is on
  these (owner target, 2026-10-11: 1-2 mm/yr);
- **sigma realism**: ``z = residual / vertical_std`` per span bin, coverage of
  ``|z| < 1.96`` and its robust spread.

Only independent GNSS (UNR daily, MIDAS), frozen per frame in the same cache
the DISP-CAL validation uses. Stations in deforming areas or event
footprints are reported but not gated (decision 0002).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .classes import load_polygons
from .gnss import load_or_fetch_gnss
from .metrics import velocity_stats
from .requirements import VLM_GATE, VlmGate

logger = logging.getLogger(__name__)

__all__ = [
    "VlmProduct",
    "VlmRunConfig",
    "evaluate_vlm",
    "list_vlm_products",
    "pair_residuals",
    "run_vlm",
    "sigma_realism",
    "station_rates",
]

MAD_SCALE = 1.4826


@dataclass(frozen=True)
class VlmProduct:
    """One VLM product and its time span."""

    path: Path
    t0: datetime
    t1: datetime

    @property
    def years(self) -> float:
        """Span in years."""
        return (self.t1 - self.t0).days / 365.25


def _text(value: Any) -> str:
    value = value[()] if hasattr(value, "shape") else value
    return value.decode() if isinstance(value, bytes) else str(value)


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.rstrip("Z"))


def list_vlm_products(folder: Path | str) -> list[VlmProduct]:
    """VLM products (``OPERA_*VLM*.nc``) of a run, by secondary date."""
    out = []
    for p in sorted(Path(folder).glob("OPERA_*VLM*.nc")):
        with h5py.File(p, "r") as f:
            ident = f["identification"]
            out.append(
                VlmProduct(
                    p,
                    _when(_text(ident["reference_datetime"])),
                    _when(_text(ident["secondary_datetime"])),
                )
            )
    if not out:
        msg = f"no VLM products in {folder}"
        raise FileNotFoundError(msg)
    return sorted(out, key=lambda v: v.t1)


def locate(path: Path, stations: pd.DataFrame) -> pd.DataFrame:
    """Rows/cols of `stations` (lon, lat) on a product grid; outside ones dropped."""
    from pyproj import Transformer

    with h5py.File(path, "r") as f:
        x, y = f["x"][()], f["y"][()]
        epsg = int(np.atleast_1d(f.attrs["epsg"])[0])
    xs, ys = Transformer.from_crs("EPSG:4326", epsg, always_xy=True).transform(
        stations["lon"].to_numpy(), stations["lat"].to_numpy()
    )
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    cols = np.rint((np.asarray(xs) - x[0]) / dx).astype(int)
    rows = np.rint((np.asarray(ys) - y[0]) / dy).astype(int)
    st = stations.assign(row=rows, col=cols)
    inside = (rows >= 0) & (rows < y.size) & (cols >= 0) & (cols < x.size)
    return st[inside]


def _sample(f: h5py.File, layer: str, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """3 x 3 NaN-median around each pixel (read window by window, not the frame)."""
    d = f[layer]
    ny, nx = d.shape
    out = np.full(rows.size, np.nan)
    for i, (r, c) in enumerate(zip(rows, cols, strict=True)):
        w = d[max(r - 1, 0) : min(r + 2, ny), max(c - 1, 0) : min(c + 2, nx)].astype(
            float
        )
        if layer == "mode":
            out[i] = d[r, c]
        elif np.isfinite(w).any():
            out[i] = np.nanmedian(w)
    return out


def _span(wide: pd.DataFrame, t0: datetime, t1: datetime, half: pd.Timedelta):
    return (
        wide.loc[t1 - half : t1 + half].median()
        - wide.loc[t0 - half : t0 + half].median()
    )


def pair_residuals(
    products: list[VlmProduct],
    stations: pd.DataFrame,
    daily: pd.DataFrame,
    half_window_days: int = 3,
) -> pd.DataFrame:
    """Per (product, station): VLM and GNSS vertical/east displacement (mm)."""
    st = locate(products[0].path, stations)
    d = daily[daily["station"].isin(st.index)]
    wide = {
        c: d.pivot_table(index="date", columns="station", values=c).sort_index() * 1e3
        for c in ("up", "east")
    }
    half = pd.Timedelta(days=half_window_days)
    r, c = st["row"].to_numpy(), st["col"].to_numpy()
    rows = []
    for p in products:
        with h5py.File(p.path, "r") as f:
            vals = {
                k: _sample(f, k, r, c) for k in ("vertical", "vertical_std", "east")
            }
            mode = _sample(f, "mode", r, c)
        gu = _span(wide["up"], p.t0, p.t1, half).reindex(st.index)
        ge = _span(wide["east"], p.t0, p.t1, half).reindex(st.index)
        rows.append(
            pd.DataFrame(
                {
                    "station": st.index,
                    "t1": p.t1.date(),
                    "years": p.years,
                    "mode": mode.astype(int),
                    "vlm_up": vals["vertical"] * 1e3,
                    "sigma_up": vals["vertical_std"] * 1e3,
                    "gnss_up": gu.to_numpy(),
                    "vlm_east": vals["east"] * 1e3,
                    "gnss_east": ge.to_numpy(),
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    out["r_up"] = out["vlm_up"] - out["gnss_up"]
    out["r_east"] = out["vlm_east"] - out["gnss_east"]
    out["z_up"] = out["r_up"] / out["sigma_up"]
    return out


def station_rates(
    res: pd.DataFrame, min_pairs: int = 5, min_span_years: float = 2.5
) -> pd.DataFrame:
    """Vertical rate of VLM and of GNSS up per station, same epochs (mm/yr)."""
    rows = []
    for s, g in res.dropna(subset=["vlm_up", "gnss_up"]).groupby("station"):
        if len(g) < min_pairs or g["years"].max() - g["years"].min() < min_span_years:
            continue
        rows.append(
            {
                "station": s,
                "n_pairs": len(g),
                "mode": int(g["mode"].mode().iloc[0]),
                "vlm_rate": float(np.polyfit(g["years"], g["vlm_up"], 1)[0]),
                "gnss_rate": float(np.polyfit(g["years"], g["gnss_up"], 1)[0]),
            }
        )
    cols = ["station", "n_pairs", "mode", "vlm_rate", "gnss_rate"]
    return pd.DataFrame(rows, columns=cols).set_index("station")


def sigma_realism(res: pd.DataFrame) -> list[dict[str, float]]:
    """Coverage of |z| < 1.96 and robust spread of z per whole-year span bin."""
    out = []
    ok = res.dropna(subset=["z_up"])
    for yrs, g in ok.groupby(ok["years"].round(0)):
        z = g["z_up"].to_numpy()
        out.append(
            {
                "span_years": float(yrs),
                "n": int(z.size),
                "coverage_1.96": float(np.mean(np.abs(z) < 1.96)),
                "nmad_z": float(MAD_SCALE * np.median(np.abs(z - np.median(z)))),
            }
        )
    return out


def evaluate_vlm(stats: dict[str, Any], gate: VlmGate = VLM_GATE) -> list[str]:
    """FAIL reasons of the VLM gate on the gated station-rate statistics."""
    reasons = []
    n = stats.get("n", 0)
    if n < gate.min_stations:
        return [f"{n} gated stations with rates (< {gate.min_stations}): not assessed"]
    if abs(stats["median"]) > gate.rate_abs_median_max_mm_yr:
        reasons.append(
            f"|median| vertical rate {abs(stats['median']):.2f} mm/yr >"
            f" {gate.rate_abs_median_max_mm_yr:g}"
        )
    if stats["nmad"] > gate.rate_nmad_max_mm_yr:
        reasons.append(
            f"vertical rate NMAD {stats['nmad']:.2f} mm/yr >"
            f" {gate.rate_nmad_max_mm_yr:g}"
        )
    return reasons


class VlmRunConfig(BaseModel):
    """One VLM validation run (``vlm.yaml``)."""

    label: str
    frame: str
    products_dir: Path = Field(description="Folder of the run's VLM products")
    cache_dir: Path = Field(description="Frozen GNSS cache of the frame")
    out_dir: Path
    defo_geojson: Path | None = None
    event_geojson: Path | None = None
    exclude_stations: list[str] = Field(default_factory=list)
    half_window_days: int = 3
    min_pairs: int = 5
    min_span_years: float = 2.5
    min_gnss_span_years: float = 2.0

    model_config = {"extra": "forbid"}


def run_vlm(cfg: VlmRunConfig) -> dict[str, Any]:
    """Validate one VLM run; write ``metrics_vlm.json`` and the residual tables."""
    from shapely import contains_xy, union_all

    products = list_vlm_products(cfg.products_dir)
    with h5py.File(products[0].path, "r") as f:
        x, y = f["x"][()], f["y"][()]
        epsg = int(np.atleast_1d(f.attrs["epsg"])[0])
    from pyproj import Transformer

    lon, lat = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True).transform(
        [x.min(), x.max(), x.min(), x.max()], [y.min(), y.min(), y.max(), y.max()]
    )
    bbox = (min(lon), min(lat), max(lon), max(lat))
    midas, daily = load_or_fetch_gnss(
        cfg.cache_dir, bbox, min_span_years=cfg.min_gnss_span_years
    )
    stations = midas.drop(index=[s for s in cfg.exclude_stations if s in midas.index])
    res = pair_residuals(products, stations, daily, cfg.half_window_days)
    rates = station_rates(res, cfg.min_pairs, cfg.min_span_years)

    polys = load_polygons(cfg.defo_geojson) + load_polygons(cfg.event_geojson)
    st = stations.reindex(rates.index)
    rates["in_area"] = (
        contains_xy(union_all(polys), st["lon"].to_numpy(), st["lat"].to_numpy())
        if polys
        else False
    )
    gated = rates[(rates["mode"] == 1) & ~rates["in_area"]]
    # r2 of a constant series (e.g. no east motion) is undefined, not an error
    with np.errstate(invalid="ignore", divide="ignore"):
        return _metrics(cfg, products, res, rates, gated)


def _metrics(
    cfg: VlmRunConfig,
    products: list[VlmProduct],
    res: pd.DataFrame,
    rates: pd.DataFrame,
    gated: pd.DataFrame,
) -> dict[str, Any]:
    rate_stats = {
        "gated_both_looks": velocity_stats(gated["vlm_rate"], gated["gnss_rate"]),
        "all": velocity_stats(rates["vlm_rate"], rates["gnss_rate"]),
        **{
            f"mode_{m}": velocity_stats(g["vlm_rate"], g["gnss_rate"])
            for m, g in rates.groupby("mode")
        },
    }
    reasons = evaluate_vlm(rate_stats["gated_both_looks"])
    d = rates["vlm_rate"] - rates["gnss_rate"]
    metrics = {
        "label": cfg.label,
        "frame": cfg.frame,
        "n_products": len(products),
        "reference_datetime": products[0].t0.isoformat(),
        "n_stations": int(res["station"].nunique()),
        "vertical_rate": rate_stats,
        "within_2_mm_yr": (
            float(np.mean(np.abs(d[gated.index]) <= 2.0)) if len(gated) else None
        ),
        "pair_vertical": velocity_stats(res["vlm_up"], res["gnss_up"]),
        "pair_east_both_looks": velocity_stats(
            res.loc[res["mode"] == 1, "vlm_east"],
            res.loc[res["mode"] == 1, "gnss_east"],
        ),
        "sigma_realism": sigma_realism(res),
        "gate": asdict(VLM_GATE),
        "verdict": "PASS" if not reasons else "FAIL",
        "verdict_reasons": reasons,
    }
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(cfg.out_dir / "pair_residuals.csv", index=False)
    rates.to_csv(cfg.out_dir / "station_rates.csv")
    (cfg.out_dir / "metrics_vlm.json").write_text(
        json.dumps(metrics, indent=1, default=str)
    )
    logger.info("%s %s: %s %s", cfg.frame, cfg.label, metrics["verdict"], reasons)
    return metrics
