# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""One frame's end-to-end validation run (plan T21-T25).

``run_validation(config)`` streams the stack once: the calibrated velocity
(DISP - CAL, chained) and the station series; the raw velocity, mean
coherence and raw station series are independent of the calibration and are
cached per stack. It then compares with MIDAS by station class, computes the
double-difference sills (raw, calibrated, baseline) with paired bootstrap
CIs, applies the gate and writes the outputs (`report.write_outputs`).

Compatibility with the trade study (``e2e_validation/validate_stack.py``):
the raw cache uses the same key and file names, and the outputs the same
names, so trade-study ``validation/`` folders serve as baselines.
"""

from __future__ import annotations

import hashlib
import json
import logging
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
import yaml
from pydantic import BaseModel, Field

from .classes import classify_stations, load_polygons, metrics_by_class
from .gate import GateInputs, evaluate, golden_epoch_check, load_gate
from .gnss import (
    StationSampler,
    gnss_los_series,
    load_or_fetch_gnss,
    split_held_out,
    station_pixels,
)
from .metrics import double_differences, velocity_stats
from .stack import Epoch, VelocityFit, list_epochs, stream_epochs

__all__ = ["FrameInputs", "RunConfig", "load_run_config", "run_validation"]

logger = logging.getLogger(__name__)

VELOCITY_TIF = "calibrated_velocity_mm_yr.tif"
SERIES_CSV = "station_series_mm.csv"


class FrameInputs(BaseModel):
    """Everything about a frame that does not depend on the candidate."""

    frame: str
    disp_dir: Path
    water_mask: Path = Field(description="GeoTIFF on the DISP grid, 1 = land")
    los_file: Path = Field(description="3-band LOS ENU GeoTIFF on the DISP grid")
    cache_dir: Path
    ref_pixel: tuple[int, int] | None = Field(
        default=None,
        description="raw velocity reference; default: the last DISP product's",
    )
    exclude_stations: list[str] = Field(default_factory=list)
    held_out_fraction: float = 0.0
    defo_geojson: Path | None = None
    event_geojson: Path | None = None
    pixel_m: float = 30.0

    model_config = {"extra": "forbid"}


class GoldenCheck(BaseModel):
    """Golden-epoch check: the candidate's product for `tag` vs the golden."""

    golden_product: Path
    tag: str = Field(description="<ref>_<sec> dates, e.g. 20220111_20220722")
    executable: str = "cal-disp"

    model_config = {"extra": "forbid"}


class RunConfig(BaseModel):
    """One validation run of one candidate on one frame."""

    label: str
    frame: FrameInputs
    candidate_dir: Path = Field(description="DISP-CAL products of the candidate")
    out_dir: Path
    baseline_dir: Path | None = Field(
        default=None, description="validation output folder of the baseline run"
    )
    gate: Path | None = None
    golden: GoldenCheck | None = None
    window: int = 7
    min_window_pixels: int = 10
    min_epochs: int = 5
    coh_threshold: float = 0.5
    min_common_dates: int = 30
    sill_min_km: float = 50.0
    near_max_km: float = 10.0
    n_boot: int = 1000
    seed: int = 0
    workers: int = 6
    allow_partial: bool = False
    min_span_years: float = 2.0

    model_config = {"extra": "forbid"}


def load_run_config(path: Path | str) -> RunConfig:
    """`RunConfig` from YAML."""
    return RunConfig(**yaml.safe_load(Path(path).read_text()))


def _read_tif(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1).astype(np.float32)


def _write_tif(path: Path, data: np.ndarray, profile: dict, desc: str) -> None:
    prof = dict(
        profile,
        count=1,
        dtype="float32",
        nodata=np.nan,
        compress="deflate",
        tiled=True,
        blockxsize=512,
        blockysize=512,
        driver="GTiff",
    )
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(data.astype(np.float32), 1)
        ds.set_band_description(1, desc)


def product_reference_point(disp_file: Path) -> tuple[int, int]:
    """``corrections/reference_point`` (row, col) of a DISP product."""
    import h5py

    with h5py.File(disp_file) as h:
        rp = h["corrections/reference_point"].attrs
        return int(rp["rows"][0]), int(rp["cols"][0])


def raw_cache_key(
    epochs: list[Epoch], cfg: RunConfig, ref_pixel: tuple[int, int]
) -> str:
    """Key of the raw part; identical to the trade study's ``stack_signature``."""
    h = hashlib.sha1()
    for e in epochs:
        h.update(e.disp.name.encode())
    h.update(
        f"{tuple(ref_pixel)}{cfg.min_epochs}{cfg.frame.water_mask}{cfg.window}"
        f"{cfg.min_window_pixels}".encode()
    )
    return h.hexdigest()[:12]


def config_hash(cfg: RunConfig, epochs: list[Epoch]) -> str:
    """Content hash of a run: package version, config, input manifest (T25.2)."""
    h = hashlib.sha256()
    h.update(version("disp2vlm-validation").encode())
    h.update(cfg.model_dump_json(exclude={"out_dir", "workers"}).encode())
    for e in epochs:
        for p in (e.disp, e.cal):
            if p is not None:
                st = p.stat()
                h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def run_validation(  # noqa: PLR0912, PLR0915
    cfg: RunConfig, *, use_cache: bool = True
) -> dict[str, Any]:
    """Validate one candidate on one frame; return the metrics (also written)."""
    from .report import write_outputs

    fr = cfg.frame
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    epochs = list_epochs(
        fr.disp_dir, cfg.candidate_dir, allow_partial=cfg.allow_partial
    )
    run_hash = config_hash(cfg, epochs)
    metrics_path = out / "metrics.json"
    if use_cache and metrics_path.exists():
        old = json.loads(metrics_path.read_text())
        if old.get("config_hash") == run_hash:
            logger.info("cached: %s (config hash %s)", metrics_path, run_hash)
            return old
    with rasterio.open(fr.los_file) as ds:
        profile, los = ds.profile, ds.read().astype(np.float32)
    shape = los.shape[1:]
    land = _read_tif(fr.water_mask).astype(bool)
    if land.shape != shape:
        msg = f"water mask {land.shape} is not on the LOS grid {shape}"
        raise ValueError(msg)
    all_epochs = list_epochs(fr.disp_dir)
    ref_pixel: tuple[int, int] = (
        (int(fr.ref_pixel[0]), int(fr.ref_pixel[1]))
        if fr.ref_pixel
        else product_reference_point(all_epochs[-1].disp)
    )
    logger.info(
        "%s: %d epochs, %d reference-date blocks; raw reference pixel %s",
        fr.frame,
        len(epochs),
        len({e.ref for e in epochs}),
        ref_pixel,
    )

    # GNSS (frozen per frame)
    from rasterio.warp import transform_bounds

    bbox = transform_bounds(
        profile["crs"],
        "EPSG:4326",
        *rasterio.transform.array_bounds(*shape, profile["transform"]),
    )
    midas_df, daily = load_or_fetch_gnss(
        fr.cache_dir, bbox, min_span_years=cfg.min_span_years
    )
    st_all = station_pixels(midas_df, profile["crs"], profile["transform"], los)
    split = split_held_out(
        st_all.index,
        exclude=fr.exclude_stations,
        held_out_fraction=fr.held_out_fraction,
    )
    st = st_all.loc[split.validation].copy()
    sampler = StationSampler(st, shape, land, cfg.window, cfg.min_window_pixels)

    # raw part: cached per stack (independent of the candidate)
    partial = len(epochs) != len(all_epochs)
    cache = (
        out / "_partial_raw"
        if partial
        else Path(fr.cache_dir) / f"stack_{raw_cache_key(all_epochs, cfg, ref_pixel)}"
    )
    cache.mkdir(parents=True, exist_ok=True)
    raw_tif = cache / "raw_velocity_mm_yr.tif"
    coh_tif = cache / "mean_temporal_coherence.tif"
    raw_csv = cache / "raw_station_series_mm.csv"
    need_raw = partial or not all(p.exists() for p in (raw_tif, coh_tif, raw_csv))
    if not need_raw:
        raw_ser_cached = pd.read_csv(raw_csv, index_col=0, parse_dates=True)
        need_raw = not set(st.index) <= set(raw_ser_cached.columns)

    first_ref = pd.Timestamp(min(e.ref for e in epochs)).normalize()
    dates = pd.DatetimeIndex(
        [first_ref] + [pd.Timestamp(e.sec).normalize() for e in epochs]
    )
    t0 = float(np.mean([e.t for e in epochs]))
    fit_cal = VelocityFit(shape, t0)
    fit_raw = VelocityFit(shape, t0) if need_raw else None
    coh_sum = np.zeros(shape) if need_raw else None
    ser_cal = np.zeros((len(dates), len(st)))
    ser_raw = np.zeros((len(dates), len(st))) if need_raw else None
    logger.info(
        "streaming epochs (raw part %s)",
        "computed" if need_raw else f"cached in {cache}",
    )
    for i, (e, (cal_disp, raw, coh)) in enumerate(
        stream_epochs(epochs, ref_pixel if need_raw else None, cfg.workers), 1
    ):
        assert cal_disp is not None
        ser_cal[i] = sampler(fit_cal.add(e.ref, e.t, cal_disp, land)) * 1000.0
        if need_raw:
            assert fit_raw is not None and raw is not None and coh is not None
            ser_raw[i] = sampler(fit_raw.add(e.ref, e.t, raw, land)) * 1000.0  # type: ignore[index]
            np.add(coh_sum, coh, out=coh_sum, where=np.isfinite(coh))
        if i % 25 == 0 or i == len(epochs):
            logger.info("  %d/%d epochs", i, len(epochs))
    if need_raw:
        assert fit_raw is not None and coh_sum is not None
        _write_tif(coh_tif, coh_sum / len(epochs), profile, "mean temporal coherence")
        _write_tif(
            raw_tif,
            np.where(land, fit_raw.velocity_mm_yr(cfg.min_epochs), np.nan),
            profile,
            f"raw LOS velocity (mm/yr), referenced to pixel {ref_pixel}",
        )
        pd.DataFrame(ser_raw, index=dates, columns=st.index).to_csv(raw_csv)
        del fit_raw
    raw_ser = pd.read_csv(raw_csv, index_col=0, parse_dates=True).reindex(index=dates)[
        st.index
    ]
    cal_ser = pd.DataFrame(ser_cal, index=dates, columns=st.index)
    cal_ser.to_csv(out / SERIES_CSV)
    keep = land & (_read_tif(coh_tif) >= cfg.coh_threshold)
    vel_raw = np.where(keep, _read_tif(raw_tif), np.nan).astype(np.float32)
    vel_cal = np.where(keep, fit_cal.velocity_mm_yr(cfg.min_epochs), np.nan).astype(
        np.float32
    )
    del fit_cal
    _write_tif(out / VELOCITY_TIF, vel_cal, profile, "calibrated LOS velocity (mm/yr)")

    # variants: candidate, raw, baseline
    variants = {"calibrated": vel_cal, "raw": vel_raw}
    series = {"calibrated": cal_ser, "raw": raw_ser}
    if cfg.baseline_dir is not None:
        b = Path(cfg.baseline_dir)
        if not ((b / VELOCITY_TIF).exists() and (b / SERIES_CSV).exists()):
            msg = f"baseline {b} has no {VELOCITY_TIF} / {SERIES_CSV}"
            raise FileNotFoundError(msg)
        variants["baseline"] = _read_tif(b / VELOCITY_TIF)
        series["baseline"] = pd.read_csv(
            b / SERIES_CSV, index_col=0, parse_dates=True
        ).reindex(index=dates, columns=st.index)
    for name, vel in variants.items():
        st[f"pix::{name}"] = vel[st["row"].to_numpy(), st["col"].to_numpy()].astype(
            float
        )
        st[f"med::{name}"] = sampler(vel)

    st["class"] = classify_stations(
        st,
        defo_areas=load_polygons(fr.defo_geojson),
        events=load_polygons(fr.event_geojson),
        land=land,
        pixel_m=fr.pixel_m,
    )
    common = st[np.all(np.isfinite(st[[f"pix::{n}" for n in variants]]), axis=1)]
    velocity = {
        name: velocity_stats(
            common[f"pix::{name}"].to_numpy(), common["gps_los_mm_yr"].to_numpy()
        )
        for name in variants
    }
    by_class = metrics_by_class(
        common["pix::calibrated"].to_numpy(),
        common["gps_los_mm_yr"].to_numpy(),
        common["class"],
        sigma_insar=None,
        sigma_gnss=None,
    )

    gps_ser = gnss_los_series(daily, st, dates)
    coords = {s: (float(st.at[s, "lon"]), float(st.at[s, "lat"])) for s in st.index}
    dd = double_differences(
        series,
        gps_ser,
        coords,
        min_common_dates=cfg.min_common_dates,
        sill_min_km=cfg.sill_min_km,
        near_max_km=cfg.near_max_km,
        n_boot=cfg.n_boot,
        seed=cfg.seed,
    )

    golden_ok, golden_out = None, "not run"
    if cfg.golden is not None:
        match = [e for e in epochs if e.tag == cfg.golden.tag]
        if match and match[0].cal is not None:
            golden_ok, golden_out = golden_epoch_check(
                cfg.golden.golden_product,
                match[0].cal,
                executable=cfg.golden.executable,
            )
        else:
            golden_out = f"no candidate product for {cfg.golden.tag}"

    has_base = "baseline" in series
    gate_inputs = GateInputs(
        sill_candidate=dd.sills["calibrated"].sill,
        sill_raw=dd.sills["raw"].sill,
        velocity_candidate=velocity["calibrated"],
        sill_baseline=dd.sills["baseline"].sill if has_base else None,
        sill_change_vs_baseline_ci=(
            dd.change_pct("calibrated", "baseline")[1] if has_base else None
        ),
        velocity_baseline=velocity["baseline"] if has_base else None,
        golden_epoch_ok=golden_ok,
        class_metrics=by_class.to_dict(orient="index"),
    )
    result = evaluate(gate_inputs, load_gate(cfg.gate))

    metrics: dict[str, Any] = {
        "label": cfg.label,
        "frame": fr.frame,
        "config_hash": run_hash,
        "package_version": version("disp2vlm-validation"),
        "n_epochs": len(epochs),
        "partial": partial,
        "reference_pixel": list(ref_pixel),
        "n_gnss_stations": len(st),
        "excluded_stations": split.excluded,
        "held_out_stations": split.held_out,
        "velocity_los": velocity,
        "velocity_by_class": by_class.reset_index().to_dict(orient="records"),
        "double_difference": {
            name: {k: v for k, v in vars(s).items() if k != "draws"}
            for name, s in dd.sills.items()
        },
        "sill_change_vs_raw": dict(
            zip(("pct", "ci95"), dd.change_pct("calibrated", "raw"), strict=True)
        ),
        "sill_change_vs_baseline": (
            dict(
                zip(
                    ("pct", "ci95"),
                    dd.change_pct("calibrated", "baseline"),
                    strict=True,
                )
            )
            if has_base
            else None
        ),
        "golden_epoch_check": golden_out,
        "verdict": result.verdict,
        "verdict_reasons": result.reasons,
        "notes": result.notes,
        "deltas": result.deltas,
        "sill_min_km": cfg.sill_min_km,
    }
    write_outputs(metrics, st, dd, out)
    metrics_path.write_text(json.dumps(metrics, indent=1, default=str))
    logger.info("%s %s: %s", fr.frame, cfg.label, result.verdict)
    return metrics
