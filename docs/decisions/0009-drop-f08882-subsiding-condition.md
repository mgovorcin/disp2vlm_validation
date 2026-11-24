# 0009. Houston's subsiding stations are reported, not gated

- **Status:** accepted (owner, 2026-11-24). Ends the F08882 waivers of
  [decision 0006](0006-f08882-subsiding-waiver.md) and
  [decision 0007](0007-v058-benchmark-failures.md) for this condition.
- **Changes:** `configs/benchmark/gate_F08882.yaml`: `subsiding` gets
  `gating: false`. Its targets stay and the class is still scored and listed
  in the report as a note. The `defo_area` condition still gates. No number in
  `requirements.py` changes.

## Context

[Decision 0002](0002-velocity-gate-outside-deforming-areas.md) took the
deforming areas out of the velocity rules and made F08882's `defo_area` and
`subsiding` classes a benchmark condition instead: |median bias| < 1 mm/yr and
an RMSE that may not exceed sqrt(raw² + reference²).
[Decision 0008](0008-sill-outside-deforming-areas.md) took the same stations
out of the DD sill.

`subsiding` is the stations whose GNSS vertical rate is below −3 mm/yr. They are
deforming ground: the calibration removes the deforming areas before its fit
and restores them after (remove-restore), and does not model the subsidence. The
condition has failed on every calibration since it was set, and not because of
the calibration's long-wavelength surface:

| Run | subsiding RMSE | limit | |
|---|---|---|---|
| v0.5 (decision 0006) | 4.97 (3.25 without TXGA) | 2.53 | fail, waived |
| cal-disp 0.5.8 (decision 0007) | 3.87 | 2.53 | fail, accepted |
| 0.5.8 settings, 137 areas masked, published UNR grid | 5.37 | 2.11 | fail |
| the same, regenerated UNR grid (v33u) | 5.32 | 2.11 | fail |

With the 137-area database masked the stations left in the class are those at
the edges of the masked bowls and single subsiding sites (TXGA Galveston with
unwrap errors, Matagorda, UHC1-3), and the miss is the same with either GNSS
grid. The frame passes every other rule, and its DD sill without deforming-area
stations stays within the GATE-2 limit.

## Decision

F08882's `subsiding` class is scored and reported but no longer fails the run.
`defo_area` keeps gating: it is the area cal-disp masks, and the calibration must
not make it worse.

## Consequences

- F08882 is judged like the other frames: on the stations the calibration fits,
  plus the `defo_area` condition.
- The subsiding misses are still in `metrics.json` and the report. Users near
  Galveston and Matagorda should still expect them; the CalVal report keeps
  saying so.
- Unwrap errors (Venti T62) and the inland unwrap pilot remain open questions;
  this decision does not settle them.
