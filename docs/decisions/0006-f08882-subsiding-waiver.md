# 0006. F08882 reference on the kept stations, and a v0.5 waiver

- **Status:** accepted (owner, 2026-10-30). Closes the question left open by
  [decision 0005](0005-velocity-stations-overlap-the-stack.md).
- **Changes:** `configs/benchmark/gate_F08882.yaml`: subsiding reference
  4.23 → 0.94 mm/yr, defo_area reference 1.82 → 1.87 mm/yr. No gate number in
  `requirements.py` changes.

## Context

Decision 0005 removed stations with under 3 years of GNSS in the stack. The
class references in the gate file were still TS-G1 RMSEs over all stations of
the class, so the F08882 limit (decision 0002) mixed a raw RMSE on the kept
stations with a reference on stations no longer scored.

## Decision

1. **The reference is computed on the stations the class scores.** Same TS-G1
   file (`ts_g1/F08882/stations_ts_g1.csv`), same classes and overlap rule as
   the run.
2. **F08882 stays a FAIL in the gate.** The verdict is not edited and the limit
   is not loosened to make it pass.
3. **The failure is waived for v0.5 only, and only for this condition.** The
   waiver is recorded in the CalVal report. It does not cover other frames or
   later releases.

## Evidence

Products `runs/F08882-final`, scored with this gate file
(`cal_disp_e2e/t50conf_overlap3/f08882_ref19`).

| class | stations | calibrated RMSE | raw RMSE | reference | limit | result |
|---|---|---|---|---|---|---|
| subsiding | 19 | 4.97 | 2.35 | 0.94 | 2.53 | **fail** |
| defo_area | 48 | 1.58 | 1.58 | 1.87 | 2.45 | pass |

Why the waiver is acceptable for this release:

- **One station dominates.** TXGA (Galveston, unwrap errors, Venti T62) reads
  −16.7 mm/yr. Without it the RMSE is 3.25 mm/yr.
- **Frame-wide the calibration helps.** Against gamma the DD sill is −60%
  [−64, −56]; the gated RMSE is 4.36 against 4.73 mm/yr and the median bias
  +0.37 against +4.14 mm/yr.

What it does not excuse:

- **Without TXGA the class still does not meet the limit**: 3.25 against 2.53
  mm/yr. TXBC +6.4 and TXMG +6.3 at Matagorda and UHC1–3 at −4 to −5 mm/yr are
  real misfits, and raw is better than calibrated in this class.
- **Users of the product near Galveston and Matagorda should expect these
  errors.** The CalVal report says so.

## Revisit

The waiver ends with v0.5. Before the next release, F08882 must pass or get a
new decision. The inputs are the inland unwrap pilot (`gulf-east-v056-unw`) and
Venti T62. Unwrap correction stays off until that trade study confirms it.
