# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""The ported e2e core: stack, GNSS and metrics (Venti plan T21)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest
from rasterio.transform import from_origin

from disp2vlm_validation.gnss import (
    StationSampler,
    gnss_los_series,
    split_held_out,
    station_pixels,
)
from disp2vlm_validation.metrics import (
    bootstrap_sills,
    double_differences,
    velocity_stats,
    weighted_median,
)
from disp2vlm_validation.stack import (
    VelocityFit,
    apply_calibration,
    list_epochs,
    parse_dates,
    read_epoch,
    stream_epochs,
)

SHAPE = (20, 30)


def _name(
    kind: str, ref: datetime, sec: datetime, prod: str = "20251027T005420Z"
) -> str:
    dates = f"{ref:%Y%m%dT%H%M%S}Z_{sec:%Y%m%dT%H%M%S}Z"
    return f"OPERA_{kind}_IW_F08882_VV_{dates}_v1.0_{prod}.nc"


def _write(path: Path, **layers: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        for k, v in layers.items():
            f[k] = v
    return path


def make_stack(
    tmp_path: Path, n_blocks=2, per_block=4, rate=0.02, with_cal=True, layout="e2e"
):
    """Two reference-date blocks; true motion `rate` m/yr everywhere; CAL = 1 cm."""
    t0 = datetime(2020, 1, 1)
    epochs = []
    for b in range(n_blocks):
        ref = t0 + timedelta(days=48 * per_block * b)
        for k in range(1, per_block + 1):
            sec = ref + timedelta(days=48 * k)
            yrs = (sec - ref).days / 365.25
            disp = np.full(SHAPE, rate * yrs, dtype=np.float64)
            coh = np.full(SHAPE, 0.9, dtype=np.float32)
            _write(
                tmp_path / "disp" / _name("L3_DISP-S1", ref, sec),
                displacement=disp,
                temporal_coherence=coh,
            )
            if with_cal:
                tag = f"{ref:%Y%m%d}_{sec:%Y%m%d}"
                d = tmp_path / "cal" / ("products/" + tag if layout == "e2e" else "")
                _write(
                    d / _name("L4_DISP-CAL-S1", ref, sec, "20261009T000000Z"),
                    calibration=np.full(SHAPE, 0.01, dtype=np.float32),
                )
                if layout == "e2e":
                    (d / ".done").touch()
            epochs.append((ref, sec))
    return epochs


class TestStack:
    def test_epochs_are_matched_with_their_cal_products(self, tmp_path):
        make_stack(tmp_path)
        epochs = list_epochs(tmp_path / "disp", tmp_path / "cal")
        assert len(epochs) == 8
        assert all(e.cal is not None and e.cal.parent.name == e.tag for e in epochs)
        assert [e.sec for e in epochs] == sorted(e.sec for e in epochs)
        assert parse_dates(epochs[0].disp.name) == (epochs[0].ref, epochs[0].sec)
        calibrated = apply_calibration(epochs[0])
        np.testing.assert_allclose(calibrated, 0.02 * 48 / 365.25 - 0.01, rtol=1e-5)

    def test_flat_layout_partial_and_unfinished(self, tmp_path):
        make_stack(tmp_path, layout="flat")
        assert len(list_epochs(tmp_path / "disp", tmp_path / "cal")) == 8
        next((tmp_path / "cal").glob("*.nc")).unlink()
        with pytest.raises(FileNotFoundError, match="no DISP-CAL product"):
            list_epochs(tmp_path / "disp", tmp_path / "cal")
        assert (
            len(list_epochs(tmp_path / "disp", tmp_path / "cal", allow_partial=True))
            == 7
        )
        with pytest.raises(FileNotFoundError, match="no OPERA_L3"):
            list_epochs(tmp_path / "nothing")

    def test_e2e_layout_skips_products_without_done_marker(self, tmp_path):
        make_stack(tmp_path)
        next((tmp_path / "cal" / "products").rglob(".done")).unlink()
        assert (
            len(list_epochs(tmp_path / "disp", tmp_path / "cal", allow_partial=True))
            == 7
        )

    def test_chained_velocity_across_blocks(self, tmp_path):
        """Cumulative displacement is chained across reference-date blocks."""
        make_stack(tmp_path, rate=0.02)
        epochs = list_epochs(tmp_path / "disp", tmp_path / "cal")
        fit_raw = VelocityFit(SHAPE, t0=np.mean([e.t for e in epochs]))
        fit_cal = VelocityFit(SHAPE, t0=np.mean([e.t for e in epochs]))
        mask = np.ones(SHAPE, bool)
        for e, (cal, raw, coh) in stream_epochs(epochs, ref_pixel=(0, 0), workers=0):
            assert coh is not None and raw is not None
            fit_raw.add(e.ref, e.t, read_epoch(e)[0] + 0.01, mask)  # DISP itself
            fit_cal.add(e.ref, e.t, cal, mask)
        np.testing.assert_allclose(fit_raw.velocity_mm_yr(), 20.0, rtol=1e-4)
        # the constant 1 cm CAL of every pair shifts each block once when chained
        assert np.isfinite(fit_cal.velocity_mm_yr()).all()
        assert not np.allclose(fit_cal.velocity_mm_yr(), 20.0, rtol=1e-3)
        # too few epochs -> NaN
        assert np.isnan(VelocityFit(SHAPE, 0.0).velocity_mm_yr(min_epochs=5)).all()


class TestGnss:
    def test_station_pixels_project_rates_onto_the_los(self):
        st = pd.DataFrame(
            {
                "lon": [-95.0, -95.0, 10.0],
                "lat": [29.5, 29.5, 45.0],
                "ve_mm_yr": [-10.0, 0.0, 1.0],
                "vn_mm_yr": [2.0, 0.0, 1.0],
                "vu_mm_yr": [-5.0, 3.0, 1.0],
            },
            index=pd.Index(["A", "B", "OUT"], name="station"),
        )
        from pyproj import Transformer

        x, y = Transformer.from_crs(
            "EPSG:4326", "EPSG:32615", always_xy=True
        ).transform(-95.0, 29.5)
        transform = from_origin(x - 150, y + 150, 30, 30)
        los = np.stack(
            [np.full(SHAPE, -0.6), np.full(SHAPE, -0.1), np.full(SHAPE, 0.75)]
        )
        out = station_pixels(st, "EPSG:32615", transform, los)
        assert list(out.index) == ["A", "B"]
        assert (out["row"] == 5).all() and (out["col"] == 5).all()
        np.testing.assert_allclose(
            out.loc["A", "gps_los_mm_yr"], -0.6 * -10 - 0.1 * 2 + 0.75 * -5
        )
        np.testing.assert_allclose(out.loc["B", "gps_hz_los_mm_yr"], 0.0)

    def test_gnss_los_series_and_sampler(self):
        st = pd.DataFrame(
            {
                "row": [2, 10],
                "col": [2, 20],
                "los_e": [0.0, 0.0],
                "los_n": [0.0, 0.0],
                "los_u": [1.0, 0.5],
            },
            index=["A", "B"],
        )
        dates = pd.DatetimeIndex(["2020-01-01", "2020-01-13"])
        daily = pd.DataFrame(
            {
                "station": ["A", "A", "B"],
                "date": pd.to_datetime(["2020-01-01", "2020-01-13", "2020-01-13"]),
                "east": [0, 0, 0],
                "north": [0, 0, 0],
                "up": [0.001, 0.002, 0.004],
            }
        )
        ser = gnss_los_series(daily, st, dates)
        assert ser.loc["2020-01-13", "B"] == pytest.approx(2.0)
        assert np.isnan(ser.loc["2020-01-01", "B"])
        land = np.ones(SHAPE, bool)
        land[0:6, 0:6] = False  # station A's whole window is water
        arr = np.arange(np.prod(SHAPE), dtype=float).reshape(SHAPE)
        s = StationSampler(st, SHAPE, land, window=7, min_pixels=10)(arr)
        assert np.isnan(s[0])  # no land pixel around A
        assert s[1] == pytest.approx(np.median(arr[7:14, 17:24]))

    def test_held_out_split_is_deterministic_and_disjoint(self):
        ids = [f"S{i:03d}" for i in range(200)]
        a = split_held_out(ids, exclude=["S000", "UH01"], held_out_fraction=0.2)
        b = split_held_out(reversed(ids), exclude=["S000"], held_out_fraction=0.2)
        assert a.validation == b.validation and a.held_out == b.held_out
        assert not set(a.validation) & set(a.held_out)
        assert "S000" not in a.validation + a.held_out
        assert 20 < len(a.held_out) < 60
        assert split_held_out(ids).held_out == []
        with pytest.raises(ValueError, match="held_out_fraction"):
            split_held_out(ids, held_out_fraction=1.0)


def _line_stations(n=12, spacing_km=10.0):
    lons = -95.0 + np.arange(n) * spacing_km / 96.0  # ~96 km per degree at 30N
    return {f"S{i:02d}": (lon, 30.0) for i, lon in enumerate(lons)}


class TestMetrics:
    def test_raw_ramp_raises_the_sill_and_calibration_removes_it(self):
        """InSAR = GNSS + per-date random ramp (long-wavelength error) + noise.
        The ramp raises gamma with distance; the calibrated variant has none."""
        rng = np.random.default_rng(0)
        coords = _line_stations()
        stations = list(coords)
        dates = pd.date_range("2020-01-01", periods=60, freq="12D")
        x = np.array([coords[s][0] for s in stations]) * 96.0  # km
        gps = pd.DataFrame(
            rng.normal(0, 3, (len(dates), len(stations))).cumsum(0),
            index=dates,
            columns=stations,
        )
        noise = rng.normal(0, 2.0, gps.shape)
        ramp = rng.normal(0, 0.3, (len(dates), 1)) * (x - x.mean())[None, :]  # mm
        raw = gps + ramp + noise
        cal = gps + noise
        dd = double_differences(
            {"raw": raw, "calibrated": cal},
            gps,
            coords,
            min_common_dates=30,
            sill_min_km=50.0,
            n_boot=300,
        )
        r, c = dd.sills["raw"], dd.sills["calibrated"]
        assert r.sill > 5 * c.sill
        assert r.ci_lo <= r.sill <= r.ci_hi and c.ci_lo <= c.sill <= c.ci_hi
        # white noise of 2 mm per station: relative series noise var 8, gamma ~ 4
        assert 2.0 < c.sill < 6.0
        d, (_lo, hi) = dd.change_pct("calibrated", "raw")
        assert d < -80 and hi < 0  # a significant drop
        assert r.n_pairs == len(stations) * (len(stations) - 1) // 2
        assert not dd.semivariograms["raw"].empty

    def test_bootstrap_and_weighted_median(self):
        assert (
            weighted_median(np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 1.0])) == 2.0
        )
        assert (
            weighted_median(np.array([1.0, 2.0, 3.0]), np.array([0.0, 0.0, 5.0])) == 3.0
        )
        assert np.isnan(weighted_median(np.array([1.0]), np.array([0.0])))
        pairs = pd.DataFrame(
            {
                "station1": ["A", "A", "B"],
                "station2": ["B", "C", "C"],
                "distance_km": [60.0, 120.0, 5.0],
                "rmse": [2.0, 4.0, 1.0],
            }
        )
        out = bootstrap_sills({"x": pairs}, n_boot=0)
        assert out["x"].sill == pytest.approx(np.median([2.0, 8.0]))
        assert out["x"].near_gamma == pytest.approx(0.5)
        assert np.isnan(out["x"].ci_lo)

    def test_velocity_stats(self):
        gps = np.array([1.0, 2.0, 3.0, np.nan])
        ins = np.array([2.0, 3.0, 4.0, 5.0])
        s = velocity_stats(ins, gps)
        assert (
            s["n"] == 3
            and s["bias"] == pytest.approx(1.0)
            and s["rmse"] == pytest.approx(1.0)
        )
        assert s["r2"] == pytest.approx(1.0)
        assert velocity_stats(ins[:1], gps[:1]) == {"n": 1}
