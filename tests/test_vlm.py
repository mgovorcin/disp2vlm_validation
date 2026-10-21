# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""VLM validation (Venti plan T57) on synthetic products with known truth."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer

from disp2vlm_validation.requirements import VlmGate
from disp2vlm_validation.vlm import (
    VlmRunConfig,
    evaluate_vlm,
    list_vlm_products,
    pair_residuals,
    run_vlm,
    station_rates,
)

EPSG = 32615
NY = NX = 60
PIX = 500.0
X0, Y0 = 300_000.0, 3_400_000.0
T0 = datetime(2020, 1, 1)


def _write_product(path: Path, t1: datetime, up_m: np.ndarray, sigma_m: float) -> None:
    x = X0 + PIX * (np.arange(NX) + 0.5)
    y = Y0 - PIX * (np.arange(NY) + 0.5)
    with h5py.File(path, "w") as f:
        f.attrs["epsg"] = EPSG
        f["x"], f["y"] = x, y
        f["vertical"] = up_m.astype(np.float32)
        f["vertical_std"] = np.full((NY, NX), sigma_m, np.float32)
        f["east"] = np.zeros((NY, NX), np.float32)
        f["mode"] = np.ones((NY, NX), np.uint8)
        f["identification/reference_datetime"] = T0.strftime("%Y-%m-%dT%H:%M:%SZ")
        f["identification/secondary_datetime"] = t1.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def run(tmp_path):
    """30 stations with known up rates; VLM = truth (+ an optional rate bias)."""

    def make(n_stations: int = 30, bias_mm_yr: float = 0.0, noise_mm: float = 1.0):
        rng = np.random.default_rng(4)
        rows = rng.integers(3, NY - 3, n_stations)
        cols = rng.integers(3, NX - 3, n_stations)
        to_ll = Transformer.from_crs(EPSG, 4326, always_xy=True)
        lon, lat = to_ll.transform(X0 + PIX * (cols + 0.5), Y0 - PIX * (rows + 0.5))
        rate = rng.normal(-3, 4, n_stations)  # mm/yr
        ids = [f"S{i:03d}" for i in range(n_stations)]
        midas = pd.DataFrame(
            {"lon": lon, "lat": lat, "vu_mm_yr": rate},
            index=pd.Index(ids, name="station"),
        )
        dates = [T0 + timedelta(days=d) for d in range(0, 6 * 365, 3)]
        daily = pd.DataFrame(
            [
                {
                    "station": s,
                    "date": d,
                    "east": 0.0,
                    "north": 0.0,
                    "up": rate[i] * (d - T0).days / 365.25 / 1e3,
                }
                for i, s in enumerate(ids)
                for d in dates
            ]
        )
        cache = tmp_path / "cache"
        cache.mkdir(exist_ok=True)
        midas.to_csv(cache / "gnss_midas_enu.csv")
        daily.to_csv(cache / "gnss_enu_daily.csv.gz", index=False)
        out = tmp_path / "products"
        out.mkdir(exist_ok=True)
        for k in range(1, 11):
            t1 = T0 + timedelta(days=180 * k)
            yrs = (t1 - T0).days / 365.25
            up = np.zeros((NY, NX))
            # each station sits on a 3x3 block of its own rate
            for r, c, v in zip(rows, cols, rate, strict=True):
                up[r - 1 : r + 2, c - 1 : c + 2] = (v + bias_mm_yr) * yrs
            up = up + rng.normal(0, noise_mm, up.shape)
            _write_product(
                out / f"OPERA_L4_VLM-S1_F99999_{k:02d}.nc", t1, up / 1e3, noise_mm / 1e3
            )
        return VlmRunConfig(
            label="test", frame="F99999", products_dir=out, cache_dir=cache,
            out_dir=tmp_path / "vlm",
        ), midas  # fmt: skip

    return make


def test_rates_recovered_and_gate_passes(run):
    cfg, _ = run()
    m = run_vlm(cfg)
    s = m["vertical_rate"]["gated_both_looks"]
    assert m["verdict"] == "PASS" and m["n_products"] == 10 and s["n"] == 30
    assert abs(s["median"]) < 0.3 and s["nmad"] < 0.5
    assert m["within_2_mm_yr"] == 1.0
    cov = [b["coverage_1.96"] for b in m["sigma_realism"]]
    assert min(cov) > 0.8  # sigma = the noise used
    saved = json.loads((cfg.out_dir / "metrics_vlm.json").read_text())
    assert saved["verdict"] == "PASS"
    assert (cfg.out_dir / "station_rates.csv").exists()


def test_rate_bias_fails_the_gate(run):
    cfg, _ = run(bias_mm_yr=2.5)
    m = run_vlm(cfg)
    assert m["verdict"] == "FAIL"
    assert any("median" in r for r in m["verdict_reasons"])


def test_too_few_stations_not_assessed():
    reasons = evaluate_vlm({"n": 5}, VlmGate())
    assert reasons and "not assessed" in reasons[0]


def test_stations_in_deforming_areas_are_not_gated(run, tmp_path):
    cfg, midas = run()
    lon, lat = midas.iloc[0][["lon", "lat"]]
    d = 0.003
    ring = [
        [lon - d, lat - d],
        [lon + d, lat - d],
        [lon + d, lat + d],
        [lon - d, lat + d],
    ]
    geo = tmp_path / "defo.geojson"
    geo.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {},
                     "geometry": {"type": "Polygon", "coordinates": [ring + ring[:1]]}}
                ],
            }
        )
    )  # fmt: skip
    m = run_vlm(cfg.model_copy(update={"defo_geojson": geo}))
    assert m["vertical_rate"]["gated_both_looks"]["n"] == 29
    assert m["vertical_rate"]["all"]["n"] == 30


def test_pair_residuals_and_rates_tables(run):
    cfg, midas = run(noise_mm=0.0)
    products = list_vlm_products(cfg.products_dir)
    daily = pd.read_csv(cfg.cache_dir / "gnss_enu_daily.csv.gz", parse_dates=["date"])
    res = pair_residuals(products, midas, daily)
    assert len(res) == 10 * 30
    np.testing.assert_allclose(res["r_up"], 0.0, atol=0.05)  # float32 + +-3 day medians
    rates = station_rates(res)
    np.testing.assert_allclose(rates["vlm_rate"], rates["gnss_rate"], atol=0.02)
    np.testing.assert_allclose(
        rates["gnss_rate"], midas.loc[rates.index, "vu_mm_yr"], atol=0.02
    )


def test_window_fit_rejects_a_short_gnss_excursion_at_t0():
    """A 4 mm network-wide jump for one week at T0 biases every pair through
    the 7-day median; the +-48-day linear fit (the VLM's own smoothing) is
    barely moved by it."""
    from disp2vlm_validation.vlm import _span

    days = pd.date_range("2016-01-01", "2020-01-01", freq="D")
    t0, t1 = datetime(2016, 7, 31), datetime(2019, 7, 31)
    rate = 2.0 / 365.25  # mm/day
    base = np.arange(days.size) * rate
    wide = pd.DataFrame({s: base for s in ("A", "B", "C")}, index=days)
    near_t0 = (days >= t0 - timedelta(days=3)) & (days <= t0 + timedelta(days=3))
    wide.loc[near_t0] += 4.0
    true = (t1 - t0).days * rate
    med = _span(wide, t0, t1, pd.Timedelta(days=3))
    fit = _span(wide, t0, t1, pd.Timedelta(days=48), "window_fit")
    np.testing.assert_allclose(med, true - 4.0, atol=1e-6)
    assert np.abs(fit - true).max() < 0.5


def test_pair_common_mode_reports_a_shared_offset():
    from disp2vlm_validation.vlm import pair_common_mode

    rng = np.random.default_rng(0)
    rows = []
    for t in pd.date_range("2017-01-01", periods=6, freq="180D"):
        for s in range(50):
            r_up = 5.0 + rng.normal(0, 3.0)
            rows.append(
                {"t1": t.date(), "station": f"S{s}", "r_up": r_up, "sigma_up": 3.0}
            )
    cm = pair_common_mode(pd.DataFrame(rows))
    assert cm["n_pairs"] == 6
    assert cm["mean_mm"] == pytest.approx(5.0, abs=1.0)
    # without the shared 5 mm the residuals are N(0, sigma): ~68% within 1 sigma
    assert 0.6 < cm["coverage_1_demeaned"] < 0.76
    assert pair_common_mode(pd.DataFrame(columns=["t1", "r_up", "sigma_up"])) == {
        "n_pairs": 0
    }


def test_vlm_config_default_keeps_the_median():
    cfg = VlmRunConfig(label="x", frame="F1", products_dir=Path("."),
                       cache_dir=Path("."), out_dir=Path("."))  # fmt: skip
    assert cfg.gnss_epoch_estimate == "median"
    assert cfg.half_window_days == 3
