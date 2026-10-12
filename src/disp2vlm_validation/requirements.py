# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""The CalVal release gate as data (Venti PRD section 2.7).

One place for the numbers a run is judged by, so the gate logic (plan T23),
the reports (T24) and the traceability table all read the same values. A
change here changes what passes; it needs a decision record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["BENCHMARK_FRAMES", "GATE", "VLM_GATE", "GateThresholds", "VlmGate"]


@dataclass(frozen=True)
class GateThresholds:
    """Release-gate thresholds; a run FAILS if any condition is violated.

    Attributes
    ----------
    sill_must_drop : bool
        The calibrated double-difference sill must be below the raw one.
    sill_rise_max_frac : float
        Candidate vs baseline: a sill rise above this fraction that is also
        statistically significant fails.
    sill_min_pair_km : float
        Station pairs shorter than this are not used for the sill.
    velocity_rmse_rise_max_mm_yr, velocity_bias_rise_max_mm_yr : float
        Candidate vs baseline: velocity RMSE or |bias| vs MIDAS may not rise
        by more than this.
    bias_statistic : str
        Which bias the bias rules use: ``"median"`` of the station residuals
        (default since decision 0001) or ``"mean"``. A mean is moved by a few
        outliers, so fixing them on a frame with a bias of the other sign
        raised |mean| and failed the gate.
    target_abs_bias_mm_yr : float
        Release target per frame (reported, not a pass/fail condition), on
        the same bias statistic.
    bootstrap_ci : float
        Confidence level of the station-bootstrap intervals.

    """

    sill_must_drop: bool = True
    sill_rise_max_frac: float = 0.05
    sill_min_pair_km: float = 50.0
    velocity_rmse_rise_max_mm_yr: float = 0.2
    velocity_bias_rise_max_mm_yr: float = 0.2
    bias_statistic: str = "median"
    target_abs_bias_mm_yr: float = 1.0
    bootstrap_ci: float = 0.95
    independent_gnss_only: bool = field(default=True, init=False)


GATE = GateThresholds()


@dataclass(frozen=True)
class VlmGate:
    """VLM gate on per-station vertical rates vs GNSS up (decision 0003, proposed).

    Owner target (2026-10-11): VLM vertical rate within 1-2 mm/yr of GNSS.
    Gated stations: both looks (mode 1), outside deforming areas and event
    footprints (decision 0002). RMSE is reported, not gated: a handful of
    local sites (landslides, wells, coast) dominate it. Baseline: LA
    (F16940 + F18904, 2016-2023), 172 stations: median -0.49, NMAD 1.47,
    RMSE 2.77 (1.67 without 6 outliers) mm/yr.

    Attributes
    ----------
    rate_abs_median_max_mm_yr, rate_nmad_max_mm_yr : float
        Limits on |median| and NMAD of (VLM rate - GNSS up rate).
    min_stations : int
        Fewer gated stations than this: not assessed (FAIL with that reason).

    """

    rate_abs_median_max_mm_yr: float = 1.0
    rate_nmad_max_mm_yr: float = 2.0
    min_stations: int = 20


VLM_GATE = VlmGate()

# PRD section 2.7: the 8-frame CalVal v0.5 benchmark. Frames 5-8 are TBD
# (plan T40); the condition is the category-specific check on top of the gate.
BENCHMARK_FRAMES: dict[int, dict[str, str]] = {
    1: {
        "frame": "F08882",
        "name": "Houston",
        "category": "coastal subsidence + islands",
        "condition": "subsiding stations: bias < 1, RMSE < 2 mm/yr",
    },
    2: {
        "frame": "F08886",
        "name": "Oklahoma City",
        "category": "stable inland",
        "condition": "stable stations: |bias| < 1 mm/yr",
    },
    3: {
        "frame": "F16940",
        "name": "Los Angeles",
        "category": "high relief + islands",
        "condition": "sill drops; tropo mode does not make it worse",
    },
    4: {
        "frame": "F08622",
        "name": "New York",
        "category": "northeast / GIA",
        "condition": "vertical pattern vs GNSS",
    },
    5: {
        "frame": "TBD",
        "name": "Central Valley",
        "category": "fast basin (defo area)",
        "condition": "continuous surface; stations outside unaffected; bowl kept",
    },
    6: {
        "frame": "TBD",
        "name": "Ridgecrest 2019",
        "category": "coseismic event",
        "condition": "no step leaks into CAL",
    },
    7: {
        "frame": "TBD",
        "name": "Great Basin or Montana",
        "category": "sparse GNSS",
        "condition": "realistic sigma; no artifacts",
    },
    8: {
        "frame": "TBD",
        "name": "Hawaii (PA) / Puerto Rico (CA)",
        "category": "non-NA plate",
        "condition": "correct plate layer; Kilauea as a defo area",
    },
}
