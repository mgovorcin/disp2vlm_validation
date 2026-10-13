# Baselines

Numbers this package must reproduce, and the release comparisons it has made.
Configs are in `configs/aurora/` (paths on aurora; the GNSS of every frame is
frozen in its `cache_dir` on first use).

## Reproduction of the trade study (plan T25.4)

`disp2vlm-validate run --config configs/aurora/F08882_repro_gamma.yaml`
re-validates the gamma run `runs/7085ec9-notropo` (cal-disp `v0.2-79-g7085ec9`,
600 km window, troposphere off) against `runs/7df274a`, which is what
`trade studies/e2e_validation/validate_stack.py` reported on 2026-10-02. It
reuses the trade study's raw-stack cache (`stack_adbefbce8a04`; the key is the
same by construction).

F08882 (Houston), 204 epochs, reference pixel (3054, 6260), UH01 excluded.

| quantity | trade study | disp2vlm-validation |
|---|---|---|
| DD sill calibrated (mm²) [95% CI] | 257.0 [234–281] | 257.0 [234–281] |
| DD sill raw (mm²) [95% CI] | 510.0 [452–582] | 510.0 [452–582] |
| DD sill baseline 7df274a (mm²) [95% CI] | 271.5 [251–293] | 271.5 [251–293] |
| stations / pairs in the DD | 107 / 5540 | 107 / 5540 |
| sill change vs raw | −49.6% [−55.9, −43.5] | −49.6% [−55.9, −43.5] |
| sill change vs baseline | −5.3% [−11.5, +0.3] | −5.3% [−11.5, +0.3] |
| LOS velocity vs MIDAS, n | 126 | 126 |
| calibrated bias / RMSE (mm/yr) | +4.05 / 5.07 | +4.05 / 5.07 |
| raw bias / RMSE (mm/yr) | −6.22 / 7.04 | −6.22 / 7.04 |
| baseline bias / RMSE (mm/yr) | +3.73 / 4.82 | +3.73 / 4.82 |
| verdict | FAIL (RMSE +0.25, \|bias\| +0.32 vs 7df274a) | FAIL (same two reasons) |

Identical to the printed digit, bootstrap intervals included (same seed and
paired draws). The FAIL is the trade study's own verdict on the 600 km /
troposphere-off gamma configuration against the earlier 7df274a run; that
configuration was accepted for gamma regardless (cal-disp
`docs/decisions/0001-gamma-config.md`: 600 km, troposphere off, unwrap off).

Note the default raw reference pixel: the trade study used (3054, 6260); the
last F08882 product's `corrections/reference_point` is (2898, 6117). Only the
raw variant depends on it (its bias, and the cache key), so configs that
must match the trade study set `ref_pixel` explicitly.

## v0.5 vs gamma on the four frames (Venti T38, 2026-10-09)

Candidate: cal-disp `feature/v05-calibrate-pair` (Venti `2b2678b`) with
`test_golden/v05_run/algorithm_parameters.yaml`. That is local-linear 50 km,
two passes, coherence⁸ + robust weights, k = 3.9, troposphere off and unwrap
off. Baseline: the gamma runs (Venti 600 km plane, troposphere off), which
are the trade-study `validation/` folders. Configs:
`configs/aurora/<frame>_v05.yaml`. Runs and reports:
`/mnt/aurora-z0/govorcin/cal_disp_e2e/t38/runs/<frame>/{gamma,v05-loclin}`.
Summary page: `t38/release_summary_v05.html`. Calibration took 27 min per
208 epochs (12 jobs, 0 failures).

**All four frames PASS the gate.**

| frame | stations (DD) | sill raw → gamma → v0.5 (mm²) | v0.5 vs gamma (95% CI) | LOS bias / RMSE gamma → v0.5 (mm/yr) |
|---|---|---|---|---|
| F08882 Houston | 126 (107) | 510.0 → 257.0 → 90.9 | −64.6% [−69.5, −58.7] | +4.05 / 5.07 → **+1.14** / 4.79 |
| F08886 OKC | 24 (9) | 417.5 → 190.6 → 35.2 | −81.5% [−88.5, −63.4] | +0.90 / 1.79 → +0.06 / 1.36 |
| F16940 LA | 268 (234) | 472.0 → 200.2 → 56.5 | −71.8% [−74.8, −68.1] | +2.95 / 11.07 → +0.65 / 4.13 |
| F08622 NYC | 89 (65) | 327.5 → 145.9 → 45.9 | −68.5% [−72.0, −65.2] | +0.71 / 1.53 → +0.25 / 1.23 |

Release target |bias| ≤ 1 mm/yr: met on three frames by the mean; F08882 is
at +1.14 (reported, not gating). See the bias issue (T38.4).

### Under decision 0001 (median bias, sea-only coastal), re-run 2026-10-09

| frame | verdict | median LOS bias gamma → v0.5 (mm/yr) | stations per class | stable stations: median bias / RMSE |
|---|---|---|---|---|
| F08882 Houston | PASS | +4.35 → **+0.95** | subsiding 82, coastal 20, stable 24 | **+3.12** / 5.08 |
| F08886 OKC | PASS | +0.83 → −0.11 | stable 24 | −0.11 / 1.36 |
| F16940 LA | PASS | +2.17 → +0.61 | subsiding 19, coastal 40, stable 209 | +0.32 / 1.72 |
| F08622 NYC | PASS | +0.73 → +0.11 | subsiding 2, coastal 48, stable 39 | +0.38 / 1.30 |

- **The release target (|median bias| ≤ 1 mm/yr) is met on all four
  frames.**
- **The class rule now leaves stable stations everywhere.** Before, OKC had
  only "coastal" stations, from its ponds and reservoirs.
- **Houston's stable stations show the frame's positive bias plainly**
  (issue #2). The frame-wide median is close to zero because the 82
  subsiding stations dominate it.
- **The TS-U1 unwrap run now passes the gate.** Its median bias is unchanged
  at +0.95; the no-go stands on the other grounds.

### Spread of the station residuals (NMAD), v0.5 vs gamma

On F08882 the NMAD of the velocity residuals rises from 1.29–1.51 (gamma) to
2.7–2.9 mm/yr (v0.5), while RMSE and median bias fall.

- **It is not the GNSS grid.** The change at each station does not
  correlate with the grid-minus-station error from TS-G1 (r = −0.01).
- **Within reference blocks, v0.5 is better.** The per-station scatter of
  the within-block rates drops from 7.5 to 4.2 mm/yr.
- **The chained velocity spreads more.** Each block's last-epoch surface
  error, at ~50 km scale and mostly atmosphere, is carried into every later
  epoch. Gamma's frame-wide plane carries only a near-constant, which ends
  up in the bias, not the spread.

This concerns how a velocity (VLM) is built from chained per-pair
DISP-CAL products, not the per-pair product. It is tracked in
disp2vlm_validation issue #3.

### Differences > 10% from the trade-study two-pass runs (T38.3)

The trade study's proposal (`twopass-Cw8*` runs: sill 80.8 / 25.8 / 52.0 /
28.2 mm², RMSE 3.28 / 1.31 / 3.19 / 1.08) was not the v0.5 configuration. Its
prototype ran **estimator C** between the passes:

- a free offset for every water-separated region;
- whole-cycle unwrap shifts.

v0.5 has neither, by decision: unwrap is off, and free offsets are "not in
v0.5; part of TS-U1" (PRD risk table). Every gap traces to that.

| frame | quantity | trade study | v0.5 | diff | explanation |
|---|---|---|---|---|---|
| F08882 | RMSE | 3.28 | 4.79 | +46% | Five Galveston-area stations (GAL2, GAL7, TXGA, TDAM, TXGV) are 7–17 mm/yr lower in v0.5. The trade run's unwrap pass shifted regions in 181/204 epochs. Without those stations: 4.01 vs 3.35. |
| F08882 | sill | 80.8 | 90.9 | +12.5% | Same cause; the CIs overlap (72–92 vs 76–110). |
| F08886 | sill | 25.8 | 35.2 | +36% | Only 9 stations / 36 pairs; the CIs overlap (21–37 vs 26–69). No unwrap shifts there, so the cause is per-region offsets or the estimator. |
| F16940 | RMSE | 3.19 | 4.13 | +29.5% | Three island stations: SCIP +32, CAT2 +15, CAT3 +12 mm/yr, which the trade run's free per-region offsets fixed. Without them: 3.20 vs 3.18 (identical). |
| F08622 | sill | 28.2 | 45.9 | +63% | NYC has 101 water-separated regions; the trade run shifted 81/208 epochs and fit free offsets in all of them. Velocities agree within 1.6 mm/yr at every station. On the 128 epochs without shifts the gap is +49%, so the rest is the per-region offsets, and it propagates through the chain. **Partly explained**; a direct test belongs to TS-U1 (T42). |

Consequence for TS-U1: per-region offsets are worth −35 to −40% of the DD
sill on coastal frames with many water-separated regions (NYC, Houston), and
they fix island stations (LA).

## The benchmark gate on 10 frames (Venti T46, 2026-10-12)

cal-disp v0.5 (loclin 50 km two-pass, coh^8 + robust, k = 3.9, tropo off,
unwrap off, 50 km GNSS grid buffer) against gamma (Venti 600 km plane) on
the 8 PRD frames plus Houston descending (F38238, the VLM pair) and the
first three T38 frames. Gate under decision 0002: velocity rules on the
stations outside deforming areas and event footprints (Venti DB
`1.0-draft`, venti-dev `f96bb19`: Houston-Galveston, San Joaquin, Kern N/S,
Kīlauea; Ridgecrest Mw 7.1 / 6.4, Kīlauea 2018 LERZ); Houston's benchmark
condition gates F08882 (`configs/aurora/gate_F08882.yaml`). "+ RR" is
v0.5 with remove-restore (cal-disp `_remove_restore_valid`, same DBs).

| frame | run | verdict | DD sill, change vs gamma | gated v0.5: median / RMSE | gated gamma: median / RMSE |
|---|---|---|---|---|---|
| F08886 Oklahoma City | v0.5 | PASS | 35 (−81%) | −0.11 / 1.37 | +0.83 / 1.79 |
| F16940 Los Angeles | v0.5 | PASS | 56 (−72%) | +0.64 / 4.13 | +2.17 / 11.07 |
| F08622 New York | v0.5 | PASS | 46 (−69%) | +0.11 / 1.23 | +0.73 / 1.53 |
| F07081 Montana | v0.5 | PASS | 23 (−64%) | +0.97 / 1.79 | +1.96 / 2.54 |
| F36542 Central Valley | v0.5 + RR | PASS | 103 (−69%) | +2.42 / 5.04 | +10.61 / 12.80 |
| F16941 Ridgecrest | v0.5 + RR | PASS | 65 (−68%) | +0.45 / 2.16 | +0.27 / 2.84 |
| F23211 Hawaii | v0.5 + RR | PASS | 425 (−42%) | +0.48 / 2.41 | +18.46 / 18.46 |
| F35991 Puerto Rico | v0.5 | PASS | 187 (−81%) | +0.51 / 3.71 | +6.51 / 8.68 |
| F38238 Houston desc | v0.5 | PASS | 71 (−53%) | +2.47 / 4.87 | +7.01 / 7.14 |
| F08882 Houston | v0.5 + RR | **FAIL** | 114 (−56%) | +0.82 / 5.90 | +4.22 / 5.51 |

Velocities in mm/yr (LOS rate − MIDAS). Runs: `cal_disp_e2e/t46/runs/<F>/{v05b,v05rr}_db`,
table `t46/summary_db.md`.

- **v0.5 + remove-restore passes 9 of 10.** The DD sill drops 42–81% from
  gamma on every frame; the median bias drops on every frame but
  Ridgecrest (+0.45 vs +0.27, inside the 0.2 rise limit with RR; plain
  v0.5 misses it by 0.03).
- **Remove-restore** turns Central Valley from FAIL (all-station RMSE 24 vs
  17) to PASS and lowers the in-area residuals (CV in-polygon median +32.6
  → +8.9 mm/yr); on Ridgecrest it keeps the coseismic signal out of the
  fit for spanning pairs.
- **Hawaii's** ~130 mm/yr all-station RMSE was one co-eruptive station
  (ERZ4, 2018 LERZ); with the event in the DB, 75 of 93 stations are in an
  area or footprint and the 18 outside give +0.48 / 2.41 against gamma's
  +18.5 / 18.5.
- **Houston fails** on three counts: the gated RMSE rises +0.39 (Galveston
  and Matagorda coast); the subsiding area (benchmark condition) has RMSE
  2.42 against the offset-removed raw 1.74; and the subsiding class outside
  it 7.30 against 4.43. Galveston is a disconnected region with
  whole-cycle jumps in ~24% of raw pairs that the 50 km surface partly
  absorbs (T62; the trade study's free per-region offsets fixed these
  stations, see above). Unwrap correction on: gated RMSE 5.90 → 5.19
  (better than gamma), but incomplete; it stays off. Edge case for the
  final refinement pass.

### Good environments and VLM (T56, T57)

On benign frames the chained per-pair DISP-CAL velocity is within 1–2 mm/yr
of MIDAS (NMAD: NYC 0.87, OKC 1.47, Montana asc F40308 0.45, LA desc F18904
1.45) and *lowers* the scatter of raw DISP. VLM on LA (F16940 + F18904,
2016–2023, `disp2vlm-validate vlm`): 172 both-look stations, vertical rate
− GNSS up median −0.42, NMAD 1.44, RMSE 2.67 (1.67 without six local
sites), 80% within 2 mm/yr: PASS (decision 0003, proposed).
