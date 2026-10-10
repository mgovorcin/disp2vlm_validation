# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""The release gate: configuration and evaluation (PRD section 2.7; plan T23).

A run FAILS when any of these holds:

1. the calibrated double-difference sill is not below the raw one;
2. versus the baseline, the sill rises more than `sill_rise_max_pct` and the
   rise is significant (the paired bootstrap CI of the change is above 0);
3. versus the baseline, the velocity RMSE or |bias| (vs MIDAS) rises more
   than `velocity_rmse_rise_max_mm_yr` / `velocity_bias_rise_max_mm_yr`;
4. the golden-epoch check fails.

The thresholds come from `gate.yaml` (per release); the defaults are
`disp2vlm_validation.requirements.GATE`. |bias| <= `target_abs_bias_mm_yr`
and per-class targets are reported, not gating.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .requirements import GATE

__all__ = [
    "GateConfig",
    "GateInputs",
    "GateResult",
    "evaluate",
    "golden_epoch_check",
    "load_gate",
]


class ClassTarget(BaseModel):
    """Reported per-class target (not gating)."""

    max_abs_bias_mm_yr: float | None = None
    max_rmse_mm_yr: float | None = None

    model_config = {"extra": "forbid"}


class GateConfig(BaseModel):
    """Thresholds of one release (``gate.yaml``)."""

    release: str = Field(default="v0.5", description="Release the gate applies to")
    sill_min_km: float = GATE.sill_min_pair_km
    sill_rise_max_pct: float = 100.0 * GATE.sill_rise_max_frac
    velocity_rmse_rise_max_mm_yr: float = GATE.velocity_rmse_rise_max_mm_yr
    velocity_bias_rise_max_mm_yr: float = GATE.velocity_bias_rise_max_mm_yr
    target_abs_bias_mm_yr: float = GATE.target_abs_bias_mm_yr
    significance_ci: float = GATE.bootstrap_ci
    per_class_targets: dict[str, ClassTarget] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def load_gate(path: Path | str | None) -> GateConfig:
    """`GateConfig` from a YAML file; defaults when `path` is None."""
    if path is None:
        return GateConfig()
    return GateConfig(**(yaml.safe_load(Path(path).read_text()) or {}))


@dataclass
class GateInputs:
    """What the gate needs from a validation run.

    Velocities are the LOS statistics vs MIDAS (``bias``, ``rmse`` in
    mm/yr); sills in mm^2. ``sill_change_vs_baseline_ci`` is the paired
    bootstrap 95% CI of the candidate's sill change vs the baseline, in %.
    """

    sill_candidate: float
    sill_raw: float
    velocity_candidate: dict[str, float]
    sill_baseline: float | None = None
    sill_change_vs_baseline_ci: tuple[float, float] | None = None
    velocity_baseline: dict[str, float] | None = None
    golden_epoch_ok: bool | None = None
    class_metrics: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class GateResult:
    """Verdict, the FAIL reasons, and the reported (non-gating) notes."""

    passed: bool
    reasons: list[str]
    notes: list[str]
    deltas: dict[str, Any]

    @property
    def verdict(self) -> str:
        """``PASS`` or ``FAIL``."""
        return "PASS" if self.passed else "FAIL"


def evaluate(inputs: GateInputs, gate: GateConfig | None = None) -> GateResult:
    """Apply the gate (see the module docstring)."""
    g = gate or GateConfig()
    reasons: list[str] = []
    notes: list[str] = []
    deltas: dict[str, Any] = {}

    if not inputs.sill_candidate < inputs.sill_raw:
        reasons.append(
            f"DD sill not reduced by calibration ({inputs.sill_candidate:.1f} vs raw"
            f" {inputs.sill_raw:.1f} mm²)"
        )
    deltas["sill_change_vs_raw_pct"] = 100.0 * (
        inputs.sill_candidate / inputs.sill_raw - 1.0
    )

    if inputs.sill_baseline is not None:
        d_sill = 100.0 * (inputs.sill_candidate / inputs.sill_baseline - 1.0)
        ci = inputs.sill_change_vs_baseline_ci
        significant = ci is None or not ci[0] <= 0.0
        deltas["sill_change_vs_baseline_pct"] = d_sill
        deltas["sill_change_vs_baseline_ci"] = ci
        if d_sill > g.sill_rise_max_pct and significant:
            ci_txt = f" [95% CI {ci[0]:+.1f}, {ci[1]:+.1f}]" if ci else ""
            reasons.append(
                f"DD sill up {d_sill:+.1f}%{ci_txt} vs baseline (limit"
                f" {g.sill_rise_max_pct:g}%)"
            )
    if inputs.velocity_baseline is not None:
        cur, ref = inputs.velocity_candidate, inputs.velocity_baseline
        d_rmse = cur["rmse"] - ref["rmse"]
        d_bias = abs(cur["bias"]) - abs(ref["bias"])
        deltas["velocity_rmse_change_mm_yr"] = d_rmse
        deltas["velocity_abs_bias_change_mm_yr"] = d_bias
        if d_rmse > g.velocity_rmse_rise_max_mm_yr:
            reasons.append(
                f"velocity RMSE up {d_rmse:+.2f} mm/yr vs baseline (limit"
                f" {g.velocity_rmse_rise_max_mm_yr:g})"
            )
        if d_bias > g.velocity_bias_rise_max_mm_yr:
            reasons.append(
                f"velocity |bias| up {d_bias:+.2f} mm/yr vs baseline (limit"
                f" {g.velocity_bias_rise_max_mm_yr:g})"
            )
    if inputs.golden_epoch_ok is False:
        reasons.append("golden-epoch check failed")

    bias = inputs.velocity_candidate.get("bias")
    if bias is not None and abs(bias) > g.target_abs_bias_mm_yr:
        notes.append(
            f"|bias| {abs(bias):.2f} mm/yr above the release target"
            f" {g.target_abs_bias_mm_yr:g} mm/yr (reported, not gating)"
        )
    for cls, target in g.per_class_targets.items():
        m = inputs.class_metrics.get(cls)
        if not m or m.get("n", 0) == 0:
            continue
        if (
            target.max_abs_bias_mm_yr is not None
            and abs(m["bias"]) > target.max_abs_bias_mm_yr
        ):
            notes.append(
                f"{cls}: |bias| {abs(m['bias']):.2f} > {target.max_abs_bias_mm_yr:g}"
                " mm/yr"
            )
        if target.max_rmse_mm_yr is not None and m["rmse"] > target.max_rmse_mm_yr:
            notes.append(
                f"{cls}: RMSE {m['rmse']:.2f} > {target.max_rmse_mm_yr:g} mm/yr"
            )
    return GateResult(passed=not reasons, reasons=reasons, notes=notes, deltas=deltas)


def golden_epoch_check(
    golden: Path | str,
    candidate: Path | str,
    *,
    executable: str = "cal-disp",
    timeout_s: float = 1800.0,
) -> tuple[bool, str]:
    """Compare a candidate pair product with the golden via ``cal-disp validate``.

    Returns ``(ok, output)``. The comparison and its tolerance are cal-disp's
    own (``validate GOLDEN TEST``), so this package does not re-implement it.
    """
    exe = shutil.which(executable)
    if exe is None:
        msg = f"{executable!r} not found on PATH; install cal-disp or pass executable="
        raise FileNotFoundError(msg)
    proc = subprocess.run(
        [exe, "validate", str(golden), str(candidate)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
