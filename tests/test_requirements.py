# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""The release-gate numbers match the PRD (Venti docs/specs.md section 2.7)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys

import pytest

from disp2vlm_validation import GATE, __version__
from disp2vlm_validation.requirements import BENCHMARK_FRAMES, GateThresholds


def test_gate_matches_the_prd():
    assert GATE.sill_must_drop
    assert GATE.sill_rise_max_frac == 0.05
    assert GATE.sill_min_pair_km == 50.0
    assert GATE.velocity_rmse_rise_max_mm_yr == 0.2
    assert GATE.velocity_bias_rise_max_mm_yr == 0.2
    assert GATE.target_abs_bias_mm_yr == 1.0
    # validation never uses the calibration grid; not a constructor option
    assert GATE.independent_gnss_only
    with pytest.raises(TypeError):
        GateThresholds(independent_gnss_only=False)  # type: ignore[call-arg]
    with pytest.raises(dataclasses.FrozenInstanceError):
        GATE.sill_rise_max_frac = 0.1  # type: ignore[misc]


def test_benchmark_has_the_eight_prd_frames():
    assert sorted(BENCHMARK_FRAMES) == list(range(1, 9))
    known = {f["frame"] for f in BENCHMARK_FRAMES.values() if f["frame"] != "TBD"}
    assert known == {"F08882", "F08886", "F16940", "F08622"}


def test_cli_gate_json_and_text():
    out = subprocess.run(
        [sys.executable, "-m", "disp2vlm_validation.cli", "gate", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data = json.loads(out)
    assert data["gate"]["sill_rise_max_frac"] == 0.05
    assert data["frames"]["1"]["frame"] == "F08882"
    text = subprocess.run(
        [sys.executable, "-m", "disp2vlm_validation.cli", "gate"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert __version__ in text and "F16940" in text
