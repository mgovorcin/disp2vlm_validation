# 0007. cal-disp 0.5.8 ships with three benchmark failures

- **Status:** accepted (owner, 2026-11-02).
- **Changes:** nothing in `requirements.py` or the gate files. The verdicts stand.
  Scope is cal-disp 0.5.8 only. It is the new decision that
  [decision 0006](0006-f08882-subsiding-waiver.md) requires for F08882.

## Context

cal-disp 0.5.8 pins Venti `fc8c8f1`, which holds two fit fixes: venti-dev #55
takes invalid pixels out of the fit's block mean, and #57 takes fit coverage from
the cells the fit really has. Coherence power stays 8, the frame table stays
0.9-draft, and no fit masks are added.

The ten-frame benchmark, per pair against `t50conf_overlap3`, gives 7 PASS and 3
FAIL. The double-difference (DD) sill falls against the baseline on all ten.

## Decision

1. **The three FAIL verdicts stay FAIL**, and no limit changes.
2. **0.5.8 is released with them accepted**, because the other frames gain and
   the DD sill falls everywhere. The largest gains:
   F38238 RMSE 4.83 → 2.67 and median +2.98 → +0.17 mm/yr; F36542 RMSE 4.38 → 3.23
   and median +1.84 → +0.31 mm/yr.
3. **The acceptance covers these frames and conditions, in 0.5.8 only.** The next
   value-changing release needs them to pass or a new decision.

## Evidence

Median / RMSE / NMAD against GNSS on gated stations, in mm/yr. Stations with under
3 years of overlap are out (decision 0005).

| Frame | Stations | Baseline | #55 only | #55 + #57 (0.5.8) | Failing condition |
|---|---|---|---|---|---|
| F23211 Hawaii | 12 | +0.94 / 2.57 / 2.07 | +2.81 / 3.44 / 1.71 | +2.20 / 3.19 / 1.58 | RMSE +0.62, limit 0.2 |
| F08886 Oklahoma City | 16 | −0.11 / 1.06 / 1.14 | +0.61 / 1.35 / 0.63 | −0.58 / 1.33 / 1.51 | RMSE +0.27, limit 0.2 |
| F08882 Houston | 50 | +0.37 / 4.36 / 2.45 | not run | +0.13 / 3.61 / 1.65 | Subsiding class RMSE 3.87, limit 2.53 |

Runs are in `cal_disp_e2e/t58bench`: `runs/` holds 0.5.8 and `attrib/runs/` holds
#55 alone. Hawaii and Oklahoma City both also fail with #55 alone.

### Hawaii

- **It is a real regression at stations.** The median and RMSE both rise.
- **#55 brings the rise, and #57 reduces it.** #57 changes little outside the east
  side of the island, where it brings HILR from +4.1 to −0.7 mm/yr.
- **The cause is not known.** Calibrated velocity rises across most of the island,
  by over 5 mm/yr on the southeast flank and the west coast. TOUO reads +8.5 mm/yr.
- **The baseline predates stratified tropo**, so a difference from it includes
  that change as well. On the same stations v0.5.3 with stratified tropo gives
  +1.20 / 2.55 / 2.22, which suggests tropo is not the main cause.
- **In its favour:** the DD sill is −51% against the baseline [−65, −16]. The
  |median| rise of +1.26 is not significant [−0.18, +2.25]. There are only 12
  stations.

### Oklahoma City

- **The failure is small:** 0.07 mm/yr over the limit, on 16 stations. The |median|
  rise is not significant [−0.50, +0.97], and neither is the DD sill change, −24%
  [−71, +10.5].
- **#55 brings the RMSE rise.** #57 leaves RMSE about the same, but moves the
  median from +0.61 to −0.58 mm/yr and widens NMAD from 0.63 to 1.51 mm/yr. Spread
  on this frame is therefore worse with #57.

### Houston

- **This is the same condition as decision 0006, and it is smaller:** subsiding RMSE
  3.87 against 4.97 mm/yr. Raw (2.35) is still better in this class.
- **The frame improves overall:** gated RMSE 4.36 → 3.61 mm/yr and DD sill −15%
  [−21.5, −8.5] against the baseline.
- **The fixes have not been separated here.** No #55-only run exists for F08882.
- **The errors near Galveston and Matagorda in decision 0006 still apply** to users.

## Revisit

- Find out why #55 raises Hawaii's station residuals.
- The North America study (`cal_disp_e2e/ts_na/PLAN.md`) decides coherence power
  and fit masks across land cover. Oklahoma City's #57 spread is one input.
- F08882 remains tied to the inland unwrap pilot and Venti T62. Unwrap correction
  stays off until that trade study confirms it.
