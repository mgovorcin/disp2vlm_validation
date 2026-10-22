# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Station classes, per-class metrics and the release gate (Venti plan T22, T23)."""

from __future__ import annotations

import json
import os
import stat

import numpy as np
import pandas as pd
import pytest

from disp2vlm_validation.classes import (
    CLASS_ORDER,
    classify_stations,
    load_polygons,
    metrics_by_class,
    normalized_residuals,
    sea_mask,
)
from disp2vlm_validation.gate import (
    GateConfig,
    GateInputs,
    evaluate,
    golden_epoch_check,
    load_gate,
)


def _box(lon0, lat0, lon1, lat1):
    return {
        "type": "Polygon",
        "coordinates": [
            [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
        ],
    }


class TestClasses:
    def test_priority_and_each_class(self, tmp_path):
        st = pd.DataFrame(
            {
                "lon": [-95.5, -95.5, -95.0, -94.0, -93.0, -93.0],
                "lat": [29.5, 29.5, 29.0, 29.0, 29.0, 29.0],
                "vu_mm_yr": [-10.0, -10.0, -10.0, 0.0, 0.0, -1.0],
                "row": [50, 50, 50, 50, 5, 90],
                "col": [50, 50, 50, 50, 50, 20],
            },
            index=["EV", "EV2", "SUB", "COAST", "STAB", "STAB2"],
        )
        st.loc["COAST", ["row", "col"]] = (95, 95)  # next to the water column
        events = tmp_path / "events.geojson"
        events.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {},
                            "geometry": _box(-95.6, 29.4, -95.4, 29.6),
                        }
                    ],
                }
            )
        )
        defo = [*load_polygons(None)]
        land = np.ones((100, 100), bool)
        land[:, 98:] = False
        cls = classify_stations(
            st,
            events=load_polygons(events),
            defo_areas=defo,
            land=land,
            pixel_m=100.0,
            coast_km=1.0,
            sea_min_km2=0.0,  # this tiny strip counts as water here
        )
        assert (
            cls["EV"] == "near_event" and cls["EV2"] == "near_event"
        )  # beats subsiding
        assert cls["SUB"] == "subsiding"
        assert cls["COAST"] == "coastal"  # 3 px * 100 m from water
        assert (
            cls["STAB"] == "stable" and cls["STAB2"] == "stable"
        )  # -1 mm/yr not subsiding
        # a defo area outranks subsiding, an event outranks the defo area
        from shapely.geometry import box

        cls2 = classify_stations(
            st, defo_areas=[box(-95.2, 28.8, -94.8, 29.2)], land=land, pixel_m=100.0
        )
        assert cls2["SUB"] == "defo_area"
        assert set(cls2) <= set(CLASS_ORDER)

    def test_coastal_means_the_sea_not_ponds(self):
        """Decision 0001: a pond next to a station does not make it coastal;
        a large water body (sea, joined bay) does."""
        land = np.ones((400, 400), bool)
        land[:, 300:] = False  # sea: 400 x 100 px of 100 m = 400 km2
        land[100:103, 100:103] = False  # pond, 0.09 km2
        st = pd.DataFrame(
            {
                "lon": 0.0,
                "lat": 0.0,
                "vu_mm_yr": 0.0,
                "row": [101, 200],
                "col": [105, 250],
            },
            index=["NEAR_POND", "NEAR_SEA"],
        )
        cls = classify_stations(
            st, land=land, pixel_m=100.0, coast_km=10.0, sea_min_km2=300.0
        )
        assert cls["NEAR_POND"] == "stable" and cls["NEAR_SEA"] == "coastal"
        any_water = classify_stations(
            st, land=land, pixel_m=100.0, coast_km=10.0, sea_min_km2=0.0
        )
        assert any_water["NEAR_POND"] == "coastal"
        assert sea_mask(land, 100.0, 300.0)[:, 300:].all()
        assert not sea_mask(land, 100.0, 300.0)[100:103, 100:103].any()

    def test_metrics_by_class_and_sigma_realism(self):
        rng = np.random.default_rng(0)
        n = 400
        gnss = rng.normal(0, 5, n)
        sig_i, sig_g = 1.0, 0.5
        insar = gnss + rng.normal(0, np.hypot(sig_i, sig_g), n) + 0.3
        classes = pd.Series(np.where(np.arange(n) < 300, "stable", "coastal"))
        m = metrics_by_class(insar, gnss, classes, sigma_insar=sig_i, sigma_gnss=sig_g)
        assert m.loc["all", "n"] == n and m.loc["stable", "n"] == 300
        assert m.loc["all", "bias"] == pytest.approx(0.3, abs=0.15)
        assert 0.9 < m.loc["all", "std_z"] < 1.1
        assert 0.92 < m.loc["all", "coverage95"] < 0.98
        assert m.loc["subsiding", "n"] == 0
        no_sigma = metrics_by_class(insar, gnss, classes)
        assert "std_z" not in no_sigma.columns or np.isnan(
            no_sigma.loc["all"].get("std_z", np.nan)
        )
        z = normalized_residuals(np.array([2.0, 1.0]), np.array([1.0, 0.0]), 0.0)
        assert z[0] == pytest.approx(2.0) and np.isnan(z[1])


BASE = {"bias": 1.0, "median": 1.0, "rmse": 2.0}


def _inputs(**kw):
    d = dict(
        sill_candidate=80.0,
        sill_raw=250.0,
        velocity_candidate={"bias": 1.1, "median": 1.1, "rmse": 2.1},
        sill_baseline=82.0,
        sill_change_vs_baseline_ci=(-8.0, 4.0),
        velocity_baseline=BASE,
    )
    d.update(kw)
    return GateInputs(**d)


class TestGate:
    def test_pass(self):
        r = evaluate(_inputs())
        assert r.passed and r.verdict == "PASS" and r.reasons == []
        assert r.deltas["sill_change_vs_raw_pct"] == pytest.approx(-68.0)

    def test_sill_not_below_raw(self):
        r = evaluate(_inputs(sill_candidate=260.0, sill_baseline=None))
        assert not r.passed and "not reduced by calibration" in r.reasons[0]

    def test_sill_rise_must_be_large_and_significant(self):
        # +10% but the CI includes 0: not significant -> pass
        assert evaluate(
            _inputs(sill_candidate=90.2, sill_change_vs_baseline_ci=(-2.0, 20.0))
        ).passed
        # +10% and significant -> fail
        r = evaluate(
            _inputs(sill_candidate=90.2, sill_change_vs_baseline_ci=(3.0, 20.0))
        )
        assert not r.passed and "DD sill up +10.0%" in r.reasons[0]
        # +4% significant but under the 5% limit -> pass
        assert evaluate(
            _inputs(sill_candidate=85.3, sill_change_vs_baseline_ci=(1.0, 8.0))
        ).passed

    def test_velocity_rules(self):
        r = evaluate(
            _inputs(velocity_candidate={"bias": 1.0, "median": 1.0, "rmse": 2.3})
        )
        assert not r.passed and "RMSE up +0.30" in r.reasons[0]
        r = evaluate(
            _inputs(velocity_candidate={"bias": -1.25, "median": -1.25, "rmse": 2.0})
        )
        assert not r.passed and "|median bias| up +0.25" in r.reasons[0]

    def test_median_bias_is_not_moved_by_fixed_outliers(self):
        """Decision 0001: fixing negative outliers on a positively biased frame
        raises |mean| (TS-U1 on F08882: +1.14 -> +1.37) but not the median."""
        base = {"bias": 1.14, "median": 0.95, "rmse": 4.79}
        cand = {"bias": 1.37, "median": 0.95, "rmse": 4.31}
        r = evaluate(_inputs(velocity_baseline=base, velocity_candidate=cand))
        assert r.passed and r.deltas["bias_statistic"] == "median"
        assert r.deltas["velocity_abs_bias_change_mm_yr"] == pytest.approx(0.0)
        mean_gate = GateConfig(bias_statistic="mean")
        r = evaluate(
            _inputs(velocity_baseline=base, velocity_candidate=cand), mean_gate
        )
        assert not r.passed and "|bias| up +0.23" in r.reasons[0]
        with pytest.raises(KeyError, match="median"):
            evaluate(
                _inputs(
                    velocity_baseline={"bias": 1.0, "rmse": 2.0},
                    velocity_candidate={"bias": 1.0, "rmse": 2.0},
                )
            )

    def test_golden_epoch_and_reported_targets(self):
        r = evaluate(_inputs(golden_epoch_ok=False))
        assert not r.passed and r.reasons == ["golden-epoch check failed"]
        gate = GateConfig(
            per_class_targets={
                "subsiding": {"max_abs_bias_mm_yr": 1.0, "max_rmse_mm_yr": 2.0}
            }
        )
        r = evaluate(
            _inputs(
                class_metrics={
                    "subsiding": {"n": 5, "bias": 1.5, "median": 1.5, "rmse": 3.0}
                }
            ),
            gate,
        )
        assert r.passed  # targets are reported, not gating
        assert any("subsiding: |median bias|" in n for n in r.notes)
        assert any("subsiding: RMSE" in n for n in r.notes)
        assert any("release target" in n for n in r.notes)  # |bias| 1.1 > 1.0

    def test_gating_class_target_fails_the_run(self):
        """Decision 0002: a frame's benchmark condition (Houston) gates."""
        gate = GateConfig(
            per_class_targets={
                "defo_area": {
                    "max_abs_bias_mm_yr": 1.0,
                    "max_rmse_mm_yr": 2.0,
                    "gating": True,
                }
            }
        )
        bad = {"defo_area": {"n": 40, "bias": 0.5, "median": 0.5, "rmse": 3.1}}
        r = evaluate(_inputs(class_metrics=bad), gate)
        assert not r.passed
        assert r.reasons == ["defo_area (benchmark condition): RMSE 3.10 > 2 mm/yr"]
        good = {"defo_area": {"n": 40, "bias": 0.5, "median": 0.5, "rmse": 1.9}}
        assert evaluate(_inputs(class_metrics=good), gate).passed

    def test_class_rmse_must_drop_vs_raw(self):
        """Owner 2026-10-10: the class RMSE must drop from raw (offset removed)."""
        gate = GateConfig(
            per_class_targets={
                "defo_area": {"rmse_must_drop_vs_raw": True, "gating": True}
            }
        )
        cal = {"defo_area": {"n": 82, "bias": 0.9, "median": 0.9, "rmse": 4.87}}
        raw = {"defo_area": {"n": 82, "bias": 0.1, "median": 0.1, "rmse": 3.00}}
        r = evaluate(_inputs(class_metrics=cal, class_metrics_raw=raw), gate)
        assert not r.passed
        assert r.reasons == [
            "defo_area (benchmark condition): RMSE 4.87 not below raw 3.00 mm/yr"
            " (offset removed)"
        ]
        raw["defo_area"]["rmse"] = 6.0
        assert evaluate(_inputs(class_metrics=cal, class_metrics_raw=raw), gate).passed
        # no raw metrics for the class: nothing to compare
        assert evaluate(_inputs(class_metrics=cal), gate).passed

    def test_rmse_limit_includes_the_reference_error(self):
        """Decision 0002 amendment: RMSE <= sqrt(raw^2 + reference^2)."""
        target = {
            "rmse_must_drop_vs_raw": True,
            "reference_rmse_mm_yr": 1.82,
            "gating": True,
        }
        gate = GateConfig(per_class_targets={"defo_area": target})
        raw = {"defo_area": {"n": 56, "bias": 0.4, "median": 0.4, "rmse": 1.74}}
        ok = {"defo_area": {"n": 56, "bias": 0.8, "median": 0.8, "rmse": 2.42}}
        bad = {"defo_area": {"n": 56, "bias": 0.8, "median": 0.8, "rmse": 2.60}}
        assert evaluate(_inputs(class_metrics=ok, class_metrics_raw=raw), gate).passed
        r = evaluate(_inputs(class_metrics=bad, class_metrics_raw=raw), gate)
        assert (
            not r.passed
            and "sqrt(raw 1.74^2 + reference 1.82^2) = 2.52" in r.reasons[0]
        )

    def test_houston_gate_file(self):
        from pathlib import Path

        path = Path(__file__).parents[1] / "configs" / "benchmark" / "gate_F08882.yaml"
        g = load_gate(path)
        assert all(t.gating for t in g.per_class_targets.values())
        assert all(t.rmse_must_drop_vs_raw for t in g.per_class_targets.values())
        assert all(t.max_rmse_mm_yr is None for t in g.per_class_targets.values())
        assert all(t.reference_rmse_mm_yr for t in g.per_class_targets.values())
        assert {"defo_area", "subsiding"} <= set(g.per_class_targets)

    def test_gate_yaml(self, tmp_path):
        assert load_gate(None).sill_rise_max_pct == pytest.approx(5.0)
        p = tmp_path / "gate.yaml"
        p.write_text(
            "release: v0.5\nsill_rise_max_pct: 15\nper_class_targets:\n  stable:\n   "
            " max_abs_bias_mm_yr: 1.0\n"
        )
        g = load_gate(p)
        assert (
            g.sill_rise_max_pct == 15
            and g.per_class_targets["stable"].max_abs_bias_mm_yr == 1.0
        )
        assert evaluate(
            _inputs(sill_candidate=90.2, sill_change_vs_baseline_ci=(3.0, 20.0)), g
        ).passed
        p.write_text("unknown_key: 1\n")
        with pytest.raises(ValueError, match="unknown_key"):
            load_gate(p)


def _fake_exe(tmp_path, code: int):
    exe = tmp_path / f"fake-{code}"
    exe.write_text(f'#!/bin/sh\necho validate "$@"\nexit {code}\n')
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def test_golden_epoch_check_wraps_the_cal_disp_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    ok, out = golden_epoch_check("g.nc", "t.nc", executable=_fake_exe(tmp_path, 0))
    assert ok and "validate g.nc t.nc" in out
    ok, _ = golden_epoch_check("g.nc", "t.nc", executable=_fake_exe(tmp_path, 1))
    assert not ok
    with pytest.raises(FileNotFoundError, match="not found"):
        golden_epoch_check("g", "t", executable="no-such-cal-disp")


RISE = {"bias": 1.5, "median": 1.5, "rmse": 2.1}  # +0.5 vs BASE


class TestBiasRiseTest:
    """Decision 0004 (proposed): only a significant |bias| rise fails."""

    def test_significant_is_the_default_and_point_keeps_the_old_rule(self):
        assert GateConfig().bias_rise_test == "significant"
        r = evaluate(
            _inputs(velocity_candidate=RISE, bias_rise_ci=(-0.4, 0.9)),
            GateConfig(bias_rise_test="point"),
        )
        assert not r.passed and "median bias| up +0.50" in r.reasons[0]
        assert r.deltas["velocity_abs_bias_change_ci"] == (-0.4, 0.9)

    def test_significant_rule_passes_an_uncertain_rise_with_a_note(self):
        g = GateConfig(bias_rise_test="significant")
        r = evaluate(_inputs(velocity_candidate=RISE, bias_rise_ci=(-0.4, 0.9)), g)
        assert r.passed
        assert any("not significant" in n for n in r.notes)

    def test_significant_rule_fails_a_rise_above_the_limit(self):
        g = GateConfig(bias_rise_test="significant")
        r = evaluate(_inputs(velocity_candidate=RISE, bias_rise_ci=(0.3, 0.7)), g)
        assert not r.passed and "95% CI +0.30, +0.70" in r.reasons[0]

    def test_significant_rule_without_ci_falls_back_to_the_point_rule(self):
        g = GateConfig(bias_rise_test="significant")
        r = evaluate(_inputs(velocity_candidate=RISE), g)
        assert not r.passed


def test_bias_rise_ci_is_paired_and_covers_the_truth():
    from disp2vlm_validation.metrics import bias_rise_ci

    rng = np.random.default_rng(1)
    noise = rng.normal(0, 2.0, 18)  # 18 stations, shared station noise
    base = 0.5 + noise
    cand = 1.0 + noise + rng.normal(0, 0.3, 18)  # true rise +0.5, little own noise
    lo, hi = bias_rise_ci(cand, base)
    assert lo < 0.5 < hi
    assert hi - lo < 1.0  # paired: much narrower than the +-1 mm/yr of either median
    lo2, hi2 = bias_rise_ci(cand, rng.permutation(base))  # unpaired is wider
    assert (hi2 - lo2) > (hi - lo)
    with pytest.raises(ValueError, match="paired"):
        bias_rise_ci(cand, base[:5])
    assert np.isnan(bias_rise_ci(cand[:2], base[:2])[0])
