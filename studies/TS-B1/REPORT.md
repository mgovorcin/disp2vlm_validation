# TS-B1: stable-station bias and coherence weighting

Venti plan T44.2, PRD §7.2. Run 2026-10-09.

- **Candidates:** the v0.5 configuration with `weights.coherence_power`
  p ∈ {4, 8, 16} on F08882 (Houston) and F08886 (OKC).
- **p = 8** is the T38 v0.5 run.
- **Baseline:** the gamma run.
- **Calibration:** cal-disp `feature/v05-calibrate-pair`, about 25 min per
  frame, 0 failures.
- **Configs:** `configs/benchmark/tsb1/`.
- **Runs:** `$E2E_ROOT/tsb1/` and
  `runs/<frame>-tsb1-p{4,16}`.

## Stable stations

The station classes leave no "stable" station on either frame. The coastal
rule (≤ 10 km from the water mask) also catches lakes and rivers: every OKC
station is "coastal". So TS-B1 uses a kinematic definition: GNSS
|v_up| < 1.5 mm/yr. That gives 15 stations on Houston and 22 on OKC. See the
follow-up below about the class rule.

## Results

LOS velocity vs MIDAS, mm/yr.

| frame | run | DD sill (mm², 95% CI) | all: bias / RMSE | stable: mean / median bias, RMSE |
|---|---|---|---|---|
| F08882 | gamma | 257.0 | +4.05 / 5.07 | +4.58 / +4.79, 5.10 |
| F08882 | p = 4 | 88.9 (74–109) | +1.12 / 4.72 | +1.78 / +1.08, 4.00 |
| F08882 | p = 8 | 90.9 (76–110) | +1.14 / 4.79 | +1.68 / +0.91, 4.06 |
| F08882 | p = 16 | 91.1 (77–109) | +1.22 / 4.79 | +1.69 / +0.84, 4.06 |
| F08886 | gamma | 190.6 | +0.90 / 1.79 | +0.84 / +0.83, 1.78 |
| F08886 | p = 4 | 35.4 (24–67) | +0.09 / 1.30 | +0.04 / +0.20, 1.27 |
| F08886 | p = 8 | 35.2 (26–69) | +0.06 / 1.36 | +0.04 / −0.11, 1.33 |
| F08886 | p = 16 | 35.6 (26–70) | +0.09 / 1.38 | +0.08 / −0.01, 1.34 |

All six candidate runs PASS the gate against gamma.

## Findings

1. **The weighting power does not matter at 50 km local-linear.** Between
   p = 4 and p = 16:
   - every bias moves by ≤ 0.1 mm/yr;
   - the sills move by ≤ 2.2 mm², deep inside their CIs.
   The weights have saturated: robust re-weighting plus any p ≥ 4 already
   down-weight the same decorrelated pixels.
2. **The large drop from gamma comes from the surface, not the weighting.**
   - Houston's stable bias falls from +4.6 to +1.7 mean / +0.9 median; OKC's
     from +0.8 to about 0.
   - The trade-study comparison that credited coherence weighting (gamma →
     two-pass coh⁴/coh⁸) changed the surface (600 km plane → 50 km
     local-linear) at the same time.
3. **Houston keeps +0.9 to +1.7 mm/yr at stable stations.** The mean and
   median differ because a few stations drive it. Disp2vlm_validation#2
   tracks its source.

## Decision

- **Keep `coherence_power = 8`** as the v0.5 value. Nothing favours changing
  it: p = 4 is marginally better on Houston, but not significantly.
- **Not tested: a coherence threshold.** The schema has no threshold option.
  Given finding 1, a threshold is unlikely to differ from p ≥ 4. If wanted,
  it needs a `weights.coherence_threshold` option in Venti (default off) and
  a pin bump.

## Follow-ups

- **Station classes** (disp2vlm_validation `classes.py`, PRD §3.4): "coastal"
  should mean sea coast, or ocean water in the mask, not any water body.
  Until then, stable-station metrics need the kinematic definition used
  here.
- **Issue #2:** correct the coherence-weighting evidence (finding 2).
