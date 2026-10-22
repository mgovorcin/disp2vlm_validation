# 0004. The |bias| rise rule counts only a significant rise

- **Status:** accepted (owner, 2026-10-21). `requirements.GATE.bias_rise_test`
  is `"significant"`; `"point"` keeps the v0.5.0 rule for reproducing older
  verdicts.
- **Changes:** `requirements.GATE.bias_rise_test`, `gate.GateConfig.bias_rise_test`,
  `GateInputs.bias_rise_ci`, `metrics.bias_rise_ci`; the run reports the
  interval as `deltas.velocity_abs_bias_change_ci` in every comparison.

## Context

The candidate-vs-baseline rules (Venti PRD 2.7) fail a candidate whose
velocity RMSE or |median bias| rises by more than 0.2 mm/yr against the
baseline. The sill rule already asks for significance (the paired
station-bootstrap interval of the change must exclude zero); the bias rule
compares the point change only.

On small frames that compares noise with the limit. Hawaii (F23211, 18 gated
stations) with stratified tropo against tropo off (TS-T1 addendum,
2026-10-15): DD sill −27.8% [−43.2, −18.0], RMSE 2.40 → 2.30, but |median
bias| +0.46 → +0.96, a FAIL on the bias rule alone (owner 2026-10-15: tropo
helps; revise the rule for this case).

- The paired station bootstrap of that change is **+0.50 [−0.39, +0.92]**
  mm/yr: not significant. The median of 18 residuals is itself uncertain by
  ±0.93 mm/yr (95%), more than four times the 0.2 limit.
- Sampled as the 3x3-median around each station instead of the station pixel,
  the medians do not move (+0.42 → +0.40): the rise is single-pixel noise.

## Decision

A |bias| rise fails only when the paired station-bootstrap interval of the
change (`bootstrap_ci`, 95%) lies above `velocity_bias_rise_max_mm_yr`, i.e.
its lower bound exceeds 0.2 mm/yr. A point rise above the limit that is not
significant is reported as a note. Without a baseline interval the point
rule applies. The RMSE rule and the limits are unchanged.

## Consequences

Applied to every candidate-vs-baseline comparison on disk (63, 2026-10-21,
`cal_disp_e2e/{t46,t50conf,t57,tsb1,tsu1}`), the bias verdict changes on 6,
all rises whose interval spans zero:

| comparison | rise [95% CI] | verdict now | verdict with 0004 |
|---|---|---|---|
| Hawaii stratified vs off (v0.5.0) | +0.50 [−0.39, +0.93] | FAIL (bias only) | PASS |
| Montana full tropo vs off (TS-T1) | +0.30 [−0.03, +0.30] | FAIL | FAIL (DD sill +7.2%) |
| F16941 v05b, v05b_db, v05rrwide (T46) | +0.23 to +0.41, all spanning 0 | FAIL (bias only) | PASS |

No released configuration changes: the F16941 runs are superseded
(the release runs v05rr, PASS under both rules) and the TS-T1 decision for
Montana stands on the sill. Hawaii could then use stratified tropo (`auto`
already chooses it at 1.62 km relief), subject to the v0.5.3 re-run below.

## Hawaii on cal-disp v0.5.3 (2026-10-21)

v0.5.0 evaluated the stratified model only on each epoch's valid pixels
(venti-dev #45); the re-run on v0.5.3 (`cal_disp_e2e/t57/hawaii_v053`,
328/328 pairs) gives the same station verdict:

| Hawaii, stratified vs off | v0.5.0 | v0.5.3 |
|---|---|---|
| DD sill vs off | −27.8% [−43.2, −18.0] | −27.6% [−40.5, −19.4] |
| gated median / RMSE (18 stations) | +0.96 / 2.30 (off +0.46 / 2.40) | +0.96 / 2.30 (off +0.46 / 2.40) |
| \|median\| rise [paired 95% CI] | +0.50 [−0.39, +0.92] | +0.50 [−0.39, +0.92] |
| same, 3x3-median sample | −0.02 | −0.06 |
| verdict now / with 0004 | FAIL / PASS | FAIL / PASS |

With 0004 accepted, Hawaii can take `tropo.mode: stratified` in the frame
table (a separate Venti PR, cal-disp release with a metadata-only golden
rebuild, as 0.5.2).
