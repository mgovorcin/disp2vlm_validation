# 0002. The velocity rules score the stations the calibration is responsible for

- **Status:** accepted (owner, 2026-10-10)
- **Changes:** `requirements.GATE.velocity_excluded_classes = ("defo_area",
  "near_event")`; the `gate.yaml` field `velocity_excluded_classes`
  (`[]` restores the all-station rule); `metrics.json` gains
  `velocity_los_gate` (the statistics the rules used, the excluded classes
  and how many stations were left out). `velocity_los` (all stations) and
  `velocity_by_class` are unchanged and still reported.

## Context

DISP-CAL removes long-wavelength secular error. Deforming areas and event
footprints are **removed before the fit and restored after it**
(remove-restore, Venti PRD): the calibration surface is not fitted there and
does not try to explain that motion. The velocity rules of the gate (RMSE
and |median bias| may not rise more than 0.2 mm/yr over the baseline) were
computed on every station, including those.

T46 Hawaii (F23211, v0.5 + remove-restore vs gamma) shows what that does:

| Stations | n | gamma median / RMSE | v0.5 + remove-restore median / RMSE |
|---|---|---|---|
| all | 93 | +17.6 / 129.5 | −2.3 / 129.8 |
| outside deforming areas and events | 18 | +18.5 / 18.5 | +0.5 / 2.4 |

The all-station RMSE is one station: ERZ4, installed during the 2018
lower East Rift Zone eruption (record 2018-05 to 2020-12; LOS rate
−1229 mm/yr; east −2298, north +1511 mm/yr). It is co-eruptive motion that
no calibration should match. With it, the gate failed v0.5 on "RMSE up
+0.37 mm/yr" while v0.5 removed the +18 mm/yr bias gamma left on every
stable station. The 2018 eruption is now an event in the Venti event DB
(`kilauea_2018_lerz`, venti-dev), so ERZ4 is a `near_event` station.

## Decision

1. The velocity rules use the stations outside `defo_area` and
   `near_event`. The DD sill rule and the golden-epoch check are unchanged
   (the sill is already a double difference on common dates).
2. The excluded classes are still reported per class in `velocity_by_class`
   and in the report, so a candidate that makes them worse is visible.
3. **A frame's benchmark condition gates that frame** (owner, 2026-10-10).
   `ClassTarget.gating: true` turns a per-class target miss into a FAIL
   reason; otherwise the frame's main signal would be checked by no rule
   once it leaves the velocity rules. **Thresholds come from evidence**
   (owner, 2026-10-10), not the PRD's fixed "RMSE < 2 mm/yr": the class
   RMSE must **drop from raw to calibrated** (`rmse_must_drop_vs_raw`).
   Raw is tied to one reference pixel, so its constant offset (the median
   raw residual on the gated stations) is removed first; the offset and
   raw's class metrics are recorded as `velocity_by_class_raw`. Houston
   (`configs/aurora/gate_F08882.yaml`): |median bias| < 1 mm/yr and the
   RMSE drop, on `defo_area` (with the Venti area DB) and `subsiding`
   (without it).
4. A run must pass the same deforming-area and event databases to every
   label it compares (candidate and baseline): the classes come from the
   candidate run's databases and are applied to both.

## Consequences

- Nothing changes for a run without `defo_geojson` / `event_geojson`: no
  station is in those classes. The T38 and T46 runs so far passed none, so
  their verdicts are unchanged until they are re-validated with the Venti
  databases.
- **Houston before remove-restore** (T46 v0.5 run, no area DB, 82
  subsiding stations):

  | | median | RMSE |
  |---|---|---|
  | raw, as referenced | −5.62 | 6.37 |
  | raw, constant offset removed | +0.09 | **3.00** |
  | gamma | +4.43 | 5.24 |
  | v0.5 | +0.92 | 4.87 |

  Against the fair raw, both calibrations make the subsiding stations
  worse: without remove-restore the 50 km surface takes out part of the
  subsidence bowl, as in Central Valley. Houston v0.5 fails this rule until
  it runs with remove-restore (T46 F08882 v05rr, running 2026-10-10).
- T46 with remove-restore, on the gated stations (outside areas and
  events; Hawaii with the `kilauea_2018_lerz` event):

  | frame | gamma median / RMSE | v0.5 + remove-restore median / RMSE | all-station verdict |
  |---|---|---|---|
  | F36542 Central Valley | +10.6 / 12.8 | +2.4 / 5.0 | PASS |
  | F23211 Hawaii | +18.5 / 18.5 | +0.5 / 2.4 | FAIL (ERZ4) |
  | F16941 Ridgecrest | +0.27 / 2.84 | +0.45 / 2.16 | FAIL (median +0.32) |

  Ridgecrest's |median| rise on the gated stations is +0.18 (< 0.2).
- Hawaii passes the velocity rules with remove-restore (table above);
  its inside-area RMSE (gamma 43, v0.5 48 mm/yr) is reported, not gated.

## Amendment (owner, 2026-10-13): the RMSE limit includes the GNSS reference error

**Problem.** Inside Houston's subsidence polygon, raw DISP with one offset
removed fits MIDAS at 1.74 mm/yr. The offset is fitted on the validation
stations themselves, so raw gets help the product cannot have. InSAR's
*relative* precision there is better than the absolute GNSS reference the
calibration ties to: the UNR grid vs MIDAS is 1.82 mm/yr in that class
(TS-G1, F08882). The calibrated RMSE, 2.42, matches
√(1.74² + 1.82²) = 2.52. "Below raw" cannot be met there by any surface
setting.

**Decision.** A class target may carry `reference_rmse_mm_yr`, the grid vs
station RMSE of that class taken from the TS-G1 study. The rule is then
RMSE ≤ √(raw² + reference²): the calibration adds no error beyond its
reference. The validator still never reads the grid; the number is a
documented study result in the frame's gate file.

**Houston** (`configs/aurora/gate_F08882.yaml`): defo_area 1.82 and
subsiding 4.23 mm/yr.

| run | defo_area | subsiding |
|---|---|---|
| v0.5 + RR | 2.42 ≤ 2.52 ✓ | 7.30 > 6.13 ✗ |
| v0.5 + RR + regions (venti-dev #32) | 2.42 ≤ 2.52 ✓ | 6.28 > 6.13 ✗ (by 0.15) |

The subsiding class outside the polygon still misses. The cause is
Galveston's TXGA (a sub-region cycle error) and Matagorda, both items for
the edge-case pass.
