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
   the bias is the median of the station residuals unless `bias_statistic`
   says ``mean`` (decision 0001);
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
from typing import Any, Literal

import numpy as np
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
    rmse_must_drop_vs_raw: bool = Field(
        default=False,
        description=(
            "The class RMSE must be below raw's, raw with its constant offset"
            " removed (decision 0002): the calibration must improve on DISP there"
        ),
    )
    reference_rmse_mm_yr: float | None = Field(
        default=None,
        ge=0,
        description=(
            "With rmse_must_drop_vs_raw: the accuracy of the GNSS reference for this"
            " class (grid vs stations, from the TS-G1 study; the validator never"
            " reads the grid). The calibrated RMSE may then reach"
            " sqrt(raw^2 + reference^2): the calibration adds no error beyond its"
            " reference (decision 0002 amendment, 2026-10-13)"
        ),
    )
    gating: bool = Field(
        default=False,
        description=(
            "A miss FAILS the run instead of being a note: a frame's benchmark"
            " condition (decision 0002, e.g. Houston's subsiding stations)"
        ),
    )

    model_config = {"extra": "forbid"}


class GateConfig(BaseModel):
    """Thresholds of one release (``gate.yaml``)."""

    release: str = Field(default="v0.5", description="Release the gate applies to")
    sill_min_km: float = GATE.sill_min_pair_km
    sill_rise_max_pct: float = 100.0 * GATE.sill_rise_max_frac
    velocity_rmse_rise_max_mm_yr: float = GATE.velocity_rmse_rise_max_mm_yr
    velocity_bias_rise_max_mm_yr: float = GATE.velocity_bias_rise_max_mm_yr
    bias_statistic: Literal["median", "mean"] = GATE.bias_statistic  # type: ignore[assignment]
    target_abs_bias_mm_yr: float = GATE.target_abs_bias_mm_yr
    significance_ci: float = GATE.bootstrap_ci
    bias_rise_test: Literal["point", "significant"] = Field(
        default=GATE.bias_rise_test,  # type: ignore[arg-type]
        description=(
            "'significant' (default, decision 0004): FAIL only when the paired "
            "station-bootstrap interval of the |bias| rise lies above the limit. "
            "'point': FAIL when the point rise exceeds it (the v0.5.0 rule)."
        ),
    )
    velocity_excluded_classes: list[str] = Field(
        default_factory=lambda: list(GATE.velocity_excluded_classes),
        description="Station classes left out of the velocity rules (decision 0002)",
    )
    per_class_targets: dict[str, ClassTarget] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def load_gate(path: Path | str | None) -> GateConfig:
    """`GateConfig` from a YAML file; defaults when `path` is None."""
    if path is None:
        return GateConfig()
    from .config_io import read_config

    return GateConfig(**read_config(path))


@dataclass
class GateInputs:
    """What the gate needs from a validation run.

    Velocities are the LOS statistics vs MIDAS (``bias`` = mean, ``median``,
    ``rmse`` in mm/yr); sills in mm^2. ``sill_change_vs_baseline_ci`` is the paired
    bootstrap 95% CI of the candidate's sill change vs the baseline, in %.
    """

    sill_candidate: float
    sill_raw: float
    velocity_candidate: dict[str, float]
    sill_baseline: float | None = None
    sill_change_vs_baseline_ci: tuple[float, float] | None = None
    velocity_baseline: dict[str, float] | None = None
    bias_rise_ci: tuple[float, float] | None = None
    golden_epoch_ok: bool | None = None
    class_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    class_metrics_raw: dict[str, dict[str, float]] = field(default_factory=dict)


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


def _bias(stats: dict[str, Any], statistic: str) -> float:
    """Return the bias the gate uses: ``median`` or the mean (``bias``)."""
    key = "median" if statistic == "median" else "bias"
    if key not in stats:
        msg = f"bias_statistic={statistic!r} needs {key!r} in the velocity stats"
        raise KeyError(msg)
    return float(stats[key])


def _class_target_misses(
    target: ClassTarget,
    m: dict[str, float],
    raw: dict[str, float] | None,
    statistic: str,
    label: str,
) -> list[str]:
    """Return what one class misses of its target (empty when it meets it)."""
    out = []
    bias = abs(_bias(m, statistic))
    if target.max_abs_bias_mm_yr is not None and bias > target.max_abs_bias_mm_yr:
        out.append(f"|{label}| {bias:.2f} > {target.max_abs_bias_mm_yr:g} mm/yr")
    if target.max_rmse_mm_yr is not None and m["rmse"] > target.max_rmse_mm_yr:
        out.append(f"RMSE {m['rmse']:.2f} > {target.max_rmse_mm_yr:g} mm/yr")
    if target.rmse_must_drop_vs_raw and raw and raw.get("n", 0):
        ref = target.reference_rmse_mm_yr
        if ref is None and m["rmse"] >= raw["rmse"]:
            out.append(
                f"RMSE {m['rmse']:.2f} not below raw {raw['rmse']:.2f} mm/yr"
                " (offset removed)"
            )
        elif ref is not None and m["rmse"] > float(np.hypot(raw["rmse"], ref)):
            out.append(
                f"RMSE {m['rmse']:.2f} above sqrt(raw {raw['rmse']:.2f}^2 + reference"
                f" {ref:.2f}^2) = {float(np.hypot(raw['rmse'], ref)):.2f} mm/yr"
            )
    return out


def _bias_rule(
    d_bias: float,
    ci: tuple[float, float] | None,
    g: GateConfig,
    label: str,
    *,
    reasons: list[str],
    notes: list[str],
) -> None:
    """Apply the |bias| rise rule (`GateConfig.bias_rise_test`, decision 0004)."""
    limit = g.velocity_bias_rise_max_mm_yr
    if g.bias_rise_test == "significant" and ci is not None:
        fails = ci[0] > limit
    else:
        fails = d_bias > limit
    ci_txt = f" [95% CI {ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else ""
    if fails:
        reasons.append(
            f"velocity |{label}| up {d_bias:+.2f} mm/yr{ci_txt} vs baseline"
            f" (limit {limit:g})"
        )
    elif d_bias > limit:
        notes.append(
            f"velocity |{label}| up {d_bias:+.2f} mm/yr vs baseline, not"
            f" significant{ci_txt} (decision 0004)"
        )


def evaluate(inputs: GateInputs, gate: GateConfig | None = None) -> GateResult:
    """Apply the gate (see the module docstring)."""
    g = gate or GateConfig()
    label = "median bias" if g.bias_statistic == "median" else "bias"
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
        d_bias = abs(_bias(cur, g.bias_statistic)) - abs(_bias(ref, g.bias_statistic))
        deltas["velocity_rmse_change_mm_yr"] = d_rmse
        deltas["velocity_abs_bias_change_mm_yr"] = d_bias
        if d_rmse > g.velocity_rmse_rise_max_mm_yr:
            reasons.append(
                f"velocity RMSE up {d_rmse:+.2f} mm/yr vs baseline (limit"
                f" {g.velocity_rmse_rise_max_mm_yr:g})"
            )
        deltas["velocity_abs_bias_change_ci"] = inputs.bias_rise_ci
        _bias_rule(d_bias, inputs.bias_rise_ci, g, label, reasons=reasons, notes=notes)
    if inputs.golden_epoch_ok is False:
        reasons.append("golden-epoch check failed")

    deltas["bias_statistic"] = g.bias_statistic
    key = "median" if g.bias_statistic == "median" else "bias"
    bias = inputs.velocity_candidate.get(key)
    if bias is not None and abs(bias) > g.target_abs_bias_mm_yr:
        notes.append(
            f"|{label}| {abs(bias):.2f} mm/yr above the release target"
            f" {g.target_abs_bias_mm_yr:g} mm/yr (reported, not gating)"
        )
    for cls, target in g.per_class_targets.items():
        m = inputs.class_metrics.get(cls)
        if not m or m.get("n", 0) == 0:
            continue
        misses = _class_target_misses(
            target, m, inputs.class_metrics_raw.get(cls), g.bias_statistic, label
        )
        tag = f"{cls} (benchmark condition)" if target.gating else cls
        (reasons if target.gating else notes).extend(f"{tag}: {x}" for x in misses)
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
