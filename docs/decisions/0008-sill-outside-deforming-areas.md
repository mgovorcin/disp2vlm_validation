# 0008. The DD sill scores the stations the calibration fits

- **Status:** accepted (owner, 2026-11-24)
- **Changes:** `requirements.GATE.sill_excluded_classes = ("defo_area",
  "near_event")`; the `gate.yaml` field `sill_excluded_classes` (`[]` restores the
  all-station sill); `metrics.json` gains `double_difference_excluded` (the classes
  and the stations left out). The sill rules themselves (GATE-1, GATE-2) are
  unchanged.

## Context

[Decision 0002](0002-velocity-gate-outside-deforming-areas.md) took the stations of
deforming areas and event footprints out of the velocity rules: the calibration
removes those areas before its fit and restores them after (remove-restore), so
their InSAR-minus-GNSS differences measure the restored deformation, not the
calibration. The double-difference sill still used every station.

Since the 137-area database (v2 draft) is masked in cal-disp, that shows. With the
regenerated UNR grid and with the published grid alike, the Central Valley frame
F36542 fails GATE-2 on the all-station sill (+10.0% and +10.1%, 95% CI about +3 to
+20%); the rise comes from stations at the edge of the newly masked areas (Long
Valley corner), the same with either grid (`pubv2db` control, UNR grid regeneration
study, 2026-11-14). Left out of the sill, those stations take the change to +0.2%
(regenerated grid) and -0.0% (with fault creep models), a PASS. Across the ten
benchmark frames (regenerated grid v33j, 137 areas masked, 2026-11-15) the sill
without deforming-area stations stays within +-3% of the published-grid baseline.

## Decision

The DD sill leaves out the same station classes as the velocity rules,
`defo_area` and `near_event`, by default. The all-station sill is still available
(`sill_excluded_classes: []`) and the per-class velocity metrics are unchanged.

## Consequences

- GATE-1 (the sill must drop from raw) and GATE-2 (no significant rise over the
  baseline) are judged on the stations the calibration is responsible for, as the
  velocity rules are.
- Sills are not comparable with runs made before this decision; rerun the
  baseline with the same version before comparing.
- A frame mostly inside deforming areas has fewer pairs; `n_stations` and
  `n_pairs` in `metrics.json` show it.
- Houston's subsiding-class benchmark condition (decision 0006) is a separate
  question and is not changed here.
