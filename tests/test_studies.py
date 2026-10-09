# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Study scripts under ``studies/`` (Venti plan T38.4)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

STUDIES = Path(__file__).parents[1] / "studies"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, STUDIES / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_bias_by_block_splits_a_secular_drift_over_blocks(tmp_path):
    """InSAR = GNSS + 3 mm/yr drift + noise: every block carries its share and
    the block drifts add up to the chained bias."""
    bias_by_block = _load("bias_by_block").bias_by_block
    rng = np.random.default_rng(0)
    t0 = datetime(2020, 1, 1)
    dates = [t0 + timedelta(days=12 * i) for i in range(61)]
    disp = tmp_path / "disp"
    disp.mkdir()
    for ref_i in (0, 20, 40):  # three blocks of 20 epochs, chained on their last date
        for k in range(ref_i + 1, ref_i + 21):
            ref, sec = dates[ref_i], dates[k]
            pair = f"{ref:%Y%m%dT%H%M%S}Z_{sec:%Y%m%dT%H%M%S}Z"
            name = f"OPERA_L3_DISP-S1_IW_F99999_VV_{pair}_v1.0_20261009T000000Z.nc"
            (disp / name).touch()
    stations = [f"S{i}" for i in range(20)]
    yrs = np.array([(d - t0).days / 365.25 for d in dates])
    st = pd.DataFrame(
        {"los_e": 0.0, "los_n": 0.0, "los_u": 1.0, "class": "stable"}, index=stations
    )
    rate = rng.normal(0, 5, len(stations))  # mm/yr, LOS = up
    gps_mm = yrs[:, None] * rate[None, :]
    insar = gps_mm + 3.0 * yrs[:, None] + rng.normal(0, 1, gps_mm.shape)
    run = tmp_path / "run"
    run.mkdir()
    st.to_csv(run / "stations.csv")
    pd.DataFrame(insar, index=pd.DatetimeIndex(dates), columns=stations).to_csv(
        run / "station_series_mm.csv"
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    pd.DataFrame(
        [
            {
                "station": s,
                "date": d,
                "east": 0.0,
                "north": 0.0,
                "up": gps_mm[i, j] / 1000,
            }
            for i, d in enumerate(dates)
            for j, s in enumerate(stations)
        ]
    ).to_csv(cache / "gnss_enu_daily.csv.gz", index=False)

    blocks, summary = bias_by_block(run, disp, cache)
    assert len(blocks) == 3 and (blocks["n_stations"] == 20).all()
    assert summary["chained_bias_mm_yr"] == pytest.approx(3.0, abs=0.3)
    assert summary["block_drift_rate_mm_yr"] == pytest.approx(3.0, abs=0.5)
    # each block (240 days) carries about 3 * 240 / 365 mm
    np.testing.assert_allclose(blocks["drift_mm"], 3.0 * 240 / 365.25, atol=1.0)
    assert bias_by_block(run, disp, cache, classes=["subsiding"])[1]["n_stations"] == 0


def test_ts_g1_k_and_additive_fits():
    """k recovers a known grid-sigma inflation; the additive model recovers sigma0."""
    ts = _load("ts_g1")
    rng = np.random.default_rng(1)
    n = 4000
    sg = rng.uniform(0.2, 1.0, n)
    ss = np.full(n, 0.3)
    r = rng.normal(0, np.sqrt((2.5 * sg) ** 2 + ss**2))
    assert ts.fit_k(r, sg, ss) == pytest.approx(2.5, rel=0.05)
    assert ts.fit_k(r, sg, ss, robust=True) == pytest.approx(2.5, rel=0.08)
    assert ts.fit_k(np.zeros(5), np.ones(5), np.ones(5)) == 0.0

    dt = rng.uniform(0.03, 1.0, n)
    pairs = pd.DataFrame(
        {"dt_years": dt, "sigma_grid": 0.5 * dt, "sigma_station": 1.0},
        index=[f"S{i % 50}" for i in range(n)],
    )
    pairs["r"] = rng.normal(0, np.sqrt(3.0**2 + (2.0 * pairs.sigma_grid) ** 2 + 1.0))
    s0, k = ts.fit_additive(pairs)
    assert s0 == pytest.approx(3.0, rel=0.1)
    z = ts.z_additive(pairs, s0, k)
    assert np.std(z) == pytest.approx(1.0, abs=0.05)
    out = ts.analyze_pairs(pairs)
    assert out["additive"]["validation"]["coverage95"] == pytest.approx(0.95, abs=0.02)

    lon = np.array([0.0, 0.1, 1.0])
    lat = np.zeros(3)
    d = ts.nearest_km(lon, lat, lon, lat, exclude_self=True)
    np.testing.assert_allclose(d[:2], 11.12, rtol=0.01)


def test_ts_s1_removes_gnss_noise_and_pools_pairs():
    """Known DISP and GNSS noise: the GNSS part is removed, S is recovered."""
    ts = _load("ts_s1")
    rng = np.random.default_rng(2)
    dates = pd.date_range("2020-01-01", periods=400, freq="D")
    st = pd.DataFrame({"los_e": 0.0, "los_n": 0.0, "los_u": 1.0}, index=["A", "B"])
    daily = pd.DataFrame(
        [
            {
                "station": s,
                "date": d,
                "east": 0.0,
                "north": 0.0,
                "up": rng.normal(0, 0.003),
            }
            for s in st.index
            for d in dates
        ]
    )
    sig = ts.gnss_daily_sigma(daily, st)
    np.testing.assert_allclose(sig, 3.0, rtol=0.1)  # mm

    n = 300
    dist = rng.uniform(1, 60, n)
    pairs = pd.DataFrame(
        {
            "station1": "A",
            "station2": "B",
            "distance_km": dist,
            "rmse": np.sqrt(8.0**2 + 2 * 3.0**2) * np.ones(n),
        }
    )
    pv = ts.disp_pair_variance(pairs, pd.Series({"A": 3.0, "B": 3.0}))
    np.testing.assert_allclose(pv["var_disp"], 64.0)
    pooled = ts.pooled_s(pv)
    assert pooled["S_mm"] == pytest.approx(8.0)
    assert pooled["S_point_mm"] == pytest.approx(8.0 / np.sqrt(2))
    sf = ts.structure_function(pv)
    assert (sf["S_mm"].round(6) == 8.0).all() and sf["n_pairs"].sum() == n
    assert np.isnan(ts.fit_model(sf.iloc[:2])["nugget_mm"])  # too few bins
