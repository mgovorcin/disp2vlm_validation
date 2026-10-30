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
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from disp2vlm_validation.cli import main
from disp2vlm_validation.demo import REF_PIXEL, make_demo_frame
from disp2vlm_validation.pipeline import RunConfig, raw_cache_key, run_validation
from disp2vlm_validation.report import load_traceability, write_summary
from disp2vlm_validation.stack import list_epochs

PIX = 2000.0


@pytest.fixture(scope="module")
def frame(tmp_path_factory):
    """DISP stack, CAL candidates (perfect, half, none), LOS, mask, GNSS cache."""
    return make_demo_frame(tmp_path_factory.mktemp("frame"))


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


def test_velocity_leaves_out_stations_without_overlap(frame, tmp_path):
    """Decision 0005: a GNSS record that misses the stack does not score it."""
    cache = tmp_path / "cache"
    shutil.copytree(frame / "cache", cache)
    midas = pd.read_csv(cache / "gnss_midas_enu.csv", index_col=0)
    midas.loc["G000", ["first", "last"]] = ["2005-01-01", "2012-01-01"]  # ended before
    midas.loc["G001", ["first", "last"]] = ["2030-01-01", "2033-01-01"]  # after
    midas.to_csv(cache / "gnss_midas_enu.csv")
    cfg = _cfg(frame, "perfect", "overlap")
    cfg = cfg.model_copy(
        update={"frame": cfg.frame.model_copy(update={"cache_dir": cache})}
    )
    m = run_validation(cfg)
    base = run_validation(_cfg(frame, "perfect", "overlap_base"))
    assert m["short_overlap_stations"] == ["G000", "G001"]
    assert m["velocity_los"]["calibrated"]["n"] == (
        base["velocity_los"]["calibrated"]["n"] - 2
    )
    assert base["short_overlap_stations"] == []
    st = pd.read_csv(frame / "runs" / "overlap" / "stations.csv", index_col=0)
    assert st.loc["G000", "overlap_years"] == 0.0  # stays in the station table
    page = (frame / "runs" / "overlap" / "report.html").read_text()
    assert "decision 0005" in page


def test_demo_cli_writes_a_frame_the_tutorial_runs(tmp_path, monkeypatch, capsys):
    """docs/tutorials/01: ``demo`` then ``run`` on its configs, as written there."""
    root = tmp_path / "demo"
    monkeypatch.setattr("sys.argv", ["disp2vlm-validate", "demo", str(root)])
    main()
    cfgs = root / "configs"
    assert {p.name for p in cfgs.iterdir()} == {
        "perfect.yaml",
        "half.yaml",
        "none.yaml",
        "gate.yaml",
    }
    verdicts = {}
    for cand in ("perfect", "half", "none"):  # perfect first: it is the baseline
        monkeypatch.setattr(
            "sys.argv",
            ["disp2vlm-validate", "run", "--config", str(cfgs / f"{cand}.yaml")],
        )
        main()
        m = json.loads((root / "runs" / cand / "metrics.json").read_text())
        verdicts[cand] = m["verdict"]
    assert verdicts == {"perfect": "PASS", "half": "FAIL", "none": "FAIL"}
