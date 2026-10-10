# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""End-to-end run on a synthetic frame: stack, GNSS cache, gate, reports (T24, T25).

The frame is 40 x 60 pixels of 2 km. Truth: a vertical velocity gradient
seen with a vertical look. DISP adds a random per-date ramp (the
long-wavelength error); a perfect DISP-CAL is exactly that ramp. GNSS is
read from a pre-filled cache, so nothing touches the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from disp2vlm_validation.cli import main
from disp2vlm_validation.pipeline import RunConfig, raw_cache_key, run_validation
from disp2vlm_validation.report import load_traceability, write_summary
from disp2vlm_validation.stack import list_epochs

NY, NX, PIX = 40, 60, 2000.0
CRS = "EPSG:32615"
X0, Y0 = 300_000.0, 3_400_000.0
REF_PIXEL = (20, 30)


def _name(kind: str, ref: datetime, sec: datetime) -> str:
    dates = f"{ref:%Y%m%dT%H%M%S}Z_{sec:%Y%m%dT%H%M%S}Z"
    return f"OPERA_{kind}_IW_F99999_VV_{dates}_v1.0_20261009T000000Z.nc"


def _h5(path: Path, **layers: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        for k, v in layers.items():
            f[k] = v


def _tif(path: Path, data: np.ndarray) -> None:
    data = np.atleast_3d(data.T).T if data.ndim == 2 else data
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=NY,
        width=NX,
        count=data.shape[0],
        dtype="float32",
        crs=CRS,
        transform=from_origin(X0, Y0, PIX, PIX),
    ) as ds:
        ds.write(data.astype(np.float32))


@pytest.fixture(scope="module")
def frame(tmp_path_factory):
    """DISP stack, CAL candidates (perfect, half, none), LOS, mask, GNSS cache."""
    root = tmp_path_factory.mktemp("frame")
    rng = np.random.default_rng(1)
    _, xx = np.mgrid[0:NY, 0:NX]
    x_km = (xx - NX / 2) * PIX / 1000.0
    vel = (-5.0 + 10.0 * xx / NX) / 1000.0  # m/yr, a 10 mm/yr gradient
    t0 = datetime(2020, 1, 1)
    dates = [t0 + timedelta(days=12 * i) for i in range(21)]
    ramp = {d: rng.normal(0, 0.2, 1)[0] * x_km / 1000.0 for d in dates}  # 0.2 mm/km
    ramp[dates[0]] = np.zeros_like(x_km)
    blocks = [(dates[0], dates[1:11]), (dates[10], dates[11:])]
    for ref, secs in blocks:
        for sec in secs:
            yrs = (sec - ref).days / 365.25
            dramp = ramp[sec] - ramp[ref]
            disp = vel * yrs + dramp + rng.normal(0, 0.0005, (NY, NX))
            _h5(
                root / "disp" / _name("L3_DISP-S1", ref, sec),
                displacement=disp,
                temporal_coherence=np.full((NY, NX), 0.9, np.float32),
            )
            tag = f"{ref:%Y%m%d}_{sec:%Y%m%d}"
            for cand, frac in (("perfect", 1.0), ("half", 0.5), ("none", 0.0)):
                d = root / cand / "products" / tag
                _h5(
                    d / _name("L4_DISP-CAL-S1", ref, sec),
                    calibration=(frac * dramp).astype(np.float32),
                )
                (d / ".done").touch()
    _tif(root / "water_mask.tif", np.ones((NY, NX)))
    _tif(
        root / "los.tif",
        np.stack([np.zeros((NY, NX)), np.zeros((NY, NX)), np.ones((NY, NX))]),
    )

    # 16 stations on a jittered grid, away from the edges
    rows, cols = np.meshgrid([6, 15, 24, 33], [8, 22, 37, 51], indexing="ij")
    from pyproj import Transformer

    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    midas, daily = {}, []
    for i, (r, c) in enumerate(zip(rows.ravel(), cols.ravel(), strict=True)):
        sid = f"G{i:03d}"
        lon, lat = to_ll.transform(X0 + (c + 0.5) * PIX, Y0 - (r + 0.5) * PIX)
        vu = vel[r, c] * 1000.0
        midas[sid] = {
            "lon": lon,
            "lat": lat,
            "ve_mm_yr": 0.0,
            "vn_mm_yr": 0.0,
            "vu_mm_yr": vu,
            "sigma_ve_mm_yr": 0.3,
            "sigma_vn_mm_yr": 0.3,
            "sigma_vu_mm_yr": 0.5,
        }
        for d in dates:
            up = vu / 1000.0 * (d - t0).days / 365.25 + rng.normal(0, 0.001)
            daily.append(
                {"station": sid, "date": d, "east": 0.0, "north": 0.0, "up": up}
            )
    gnss = root / "cache"
    gnss.mkdir()
    pd.DataFrame.from_dict(midas, orient="index").rename_axis("station").to_csv(
        gnss / "gnss_midas_enu.csv"
    )
    pd.DataFrame(daily).to_csv(gnss / "gnss_enu_daily.csv.gz", index=False)
    return root


def _cfg(
    root: Path, cand: str, out: str, baseline: str | None = None, **kw
) -> RunConfig:
    return RunConfig(
        label=cand,
        frame={
            "frame": "F99999",
            "disp_dir": root / "disp",
            "water_mask": root / "water_mask.tif",
            "los_file": root / "los.tif",
            "cache_dir": root / "cache",
            "ref_pixel": REF_PIXEL,
            "pixel_m": PIX,
        },
        candidate_dir=root / cand,
        out_dir=root / "runs" / out,
        baseline_dir=root / "runs" / baseline if baseline else None,
        min_common_dates=15,
        sill_min_km=30.0,
        n_boot=200,
        workers=0,
        **kw,
    )


def test_pipeline_gate_reports_and_cache(frame):
    base = run_validation(_cfg(frame, "perfect", "baseline"))
    dd = base["double_difference"]
    assert base["verdict"] == "PASS" and base["n_gnss_stations"] == 16
    assert dd["calibrated"]["sill"] < 0.2 * dd["raw"]["sill"]
    assert base["sill_change_vs_raw"]["ci95"][1] < 0
    assert abs(base["velocity_los"]["calibrated"]["bias"]) < 0.5
    assert base["velocity_los"]["calibrated"]["rmse"] < 1.0

    out = frame / "runs" / "baseline"
    for f in (
        "metrics.json",
        "report.html",
        "stations.csv",
        "sill_draws.npz",
        "calibrated_velocity_mm_yr.tif",
        "station_series_mm.csv",
        "figures/semivariogram.svg",
        "figures/velocity_scatter.svg",
        "figures/class_rmse.svg",
    ):
        assert (out / f).exists(), f
    page = (out / "report.html").read_text()
    assert "PASS" in page and all(e["id"] in page for e in load_traceability())
    key = raw_cache_key(
        list_epochs(frame / "disp"), _cfg(frame, "perfect", "x"), REF_PIXEL
    )
    assert (frame / "cache" / f"stack_{key}" / "raw_velocity_mm_yr.tif").exists()

    # cache: an unchanged run returns the stored metrics without recomputing
    (out / "report.html").unlink()
    again = run_validation(_cfg(frame, "perfect", "baseline"))
    assert (
        again["config_hash"] == base["config_hash"]
        and not (out / "report.html").exists()
    )

    # the same candidate against itself as baseline: zero change, PASS
    same = run_validation(_cfg(frame, "perfect", "same", baseline="baseline"))
    assert same["verdict"] == "PASS"
    assert same["sill_change_vs_baseline"]["pct"] == pytest.approx(0.0, abs=1e-6)

    # half the ramp removed: below raw, but well above the baseline -> FAIL
    half = run_validation(_cfg(frame, "half", "half", baseline="baseline"))
    assert (
        half["double_difference"]["calibrated"]["sill"]
        < half["double_difference"]["raw"]["sill"]
    )
    assert half["verdict"] == "FAIL"
    assert any("DD sill up" in r for r in half["verdict_reasons"])

    # no calibration at all: the sill is not reduced -> FAIL on GATE-1
    none = run_validation(_cfg(frame, "none", "none"))
    assert none["verdict"] == "FAIL"
    assert any("not reduced by calibration" in r for r in none["verdict_reasons"])

    summary = write_summary(
        [frame / "runs" / d for d in ("same", "half", "none")],
        frame / "runs" / "release_summary.html",
    )
    text = summary.read_text()
    assert text.count("FAIL") >= 2 and "GATE-1" in text and "F99999" in text


def test_cli_run_and_summary(frame, tmp_path, monkeypatch, capsys):
    cfg = _cfg(frame, "perfect", "cli")
    path = tmp_path / "run.yaml"
    path.write_text(json.dumps(json.loads(cfg.model_dump_json())))  # JSON is YAML
    monkeypatch.setattr("sys.argv", ["disp2vlm-validate", "run", "--config", str(path)])
    main()
    assert (
        json.loads((frame / "runs" / "cli" / "metrics.json").read_text())["verdict"]
        == "PASS"
    )
    out = tmp_path / "summary.html"
    monkeypatch.setattr(
        "sys.argv",
        [
            "disp2vlm-validate",
            "summary",
            str(frame / "runs" / "cli"),
            "--out",
            str(out),
        ],
    )
    main()
    assert out.exists() and "PASS" in capsys.readouterr().out


def test_velocity_gate_leaves_out_deforming_areas(frame, tmp_path):
    """Decision 0002: stations in a deforming area are reported, not gated."""
    midas = pd.read_csv(frame / "cache" / "gnss_midas_enu.csv", index_col=0)
    lon, lat = midas.loc["G000", ["lon", "lat"]]
    d = 0.01
    ring = [
        [lon - d, lat - d],
        [lon + d, lat - d],
        [lon + d, lat + d],
        [lon - d, lat + d],
    ]
    defo = tmp_path / "defo.geojson"
    defo.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "a"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [ring + ring[:1]],
                        },
                    }
                ],
            }
        )
    )
    cfg = _cfg(frame, "perfect", "gate_defo")
    cfg = cfg.model_copy(
        update={"frame": cfg.frame.model_copy(update={"defo_geojson": defo})}
    )
    m = run_validation(cfg)
    gate = m["velocity_los_gate"]
    assert gate["excluded_classes"] == ["defo_area", "near_event"]
    assert gate["n_excluded"] == 1
    assert gate["calibrated"]["n"] == m["velocity_los"]["calibrated"]["n"] - 1
    raw = m["velocity_by_class_raw"]
    assert np.isfinite(raw["offset_removed_mm_yr"])
    assert {r["class"] for r in raw["classes"]} >= {"defo_area", "all"}
    page = (frame / "runs" / "gate_defo" / "report.html").read_text()
    assert "Stations the velocity rules use" in page and "1 left out" in page

    yaml_path = tmp_path / "gate.yaml"
    yaml_path.write_text("velocity_excluded_classes: []\n")
    m_all = run_validation(
        cfg.model_copy(update={"gate": yaml_path, "out_dir": tmp_path / "all"})
    )
    assert m_all["velocity_los_gate"]["n_excluded"] == 0
