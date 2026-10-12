# 0003. VLM gate: per-station vertical rates vs GNSS up

- **Status:** proposed (2026-10-12), thresholds from the owner's target
- **Changes:** `requirements.VLM_GATE` (`rate_abs_median_max_mm_yr = 1.0`,
  `rate_nmad_max_mm_yr = 2.0`, `min_stations = 20`); `disp2vlm-validate vlm`.

## Context

VLM (opera_vlm) writes one product per target pair `(T0, Tk)`. The owner's
target (2026-10-11): the VLM vertical rate within 1-2 mm/yr of GNSS.
First real runs (Venti plan T56.1, `cal_disp_e2e/t56`, `t57`):

| run | stations (both looks) | median | NMAD | RMSE (mm/yr) |
|---|---|---|---|---|
| LA F16940 + F18904, 2016-2023 | 172 | −0.42 | 1.44 | 2.67 (1.67 without 6 local outliers) |
| Houston F08882 + F38238 (edge case) | 52 | +0.43 | 2.48 | 3.51 |
| NYC F08622 + F30175 (projection only, data gap) | 34 | −0.60 | 1.29 | 4.86 |

## Decision

1. The gate is on **station rates** (slope of the VLM vertical series minus
   the slope of GNSS up at the same epochs), not on per-pair displacements:
   the per-pair error carries the shared `T0` and per-epoch atmosphere,
   which σ covers (opera_vlm `sigma_rate`) and rates average.
2. Gated stations: both looks (mode 1), outside deforming areas and event
   footprints (as decision 0002). Projected (mode 2) stations and the
   excluded classes are reported.
3. Limits: |median| ≤ 1 mm/yr and NMAD ≤ 2 mm/yr, on at least 20 stations.
   RMSE is reported, not gated: a handful of local sites (landslides,
   wells, coast) set it (LA: 2.67 with, 1.67 without six of them).
4. σ realism (coverage of |z| < 1.96 and robust z spread per span) is
   reported for T57.

## Consequences

LA passes; Houston fails on NMAD (edge case, final refinement pass); NYC is
not assessed in the both-looks class (its descending stack has a gap).
**Owner question:** gate RMSE too (e.g. ≤ 2 mm/yr after a documented
outlier rule), or keep it reported?
