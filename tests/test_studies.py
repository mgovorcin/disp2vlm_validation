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
