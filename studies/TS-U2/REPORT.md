# TS-U2: labelling inland unwrap errors (TS-U1 phase 2, Venti plan T62.1)

**Status:** T62.1 on Houston (F08882), 2026-10-23. Analysis only; the
unwrap-error correction stays off (owner, 2026-10-09).

## Why

TS-U1 phase 1 found 2 labelled error blocks at Galveston stations; the PRD bar
for enabling the correction is precision ≥ 0.99 and recall ≥ 0.8 on ≥ 100
cases. This study builds labels from the whole calibrated stack instead of
from stations.

## Method (`studies/ts_u2.py`)

Input: the chained calibrated displacement (DISP − CAL) of F08882, 205 epochs
2016–2023, the release calibration (v0.5; values unchanged through v0.5.4 for
this frame), averaged to 180 m cells (the calibration fit grid), 1.19 M cells.

1. **Persistent whole-cycle step.** Remove each cell's rate (median of the
   epoch-to-epoch rates, so a step does not bias it). At epoch i, the median
   over 15 epochs (~6 months) after minus the median over 15 before must be
   within 0.2 of a non-zero whole number of cycles (λ/2 = 27.7 mm); the
   5-epoch step must agree; and the level must not revert over the next 15
   epochs.
2. **Regions:** connected cells with the same k and a step epoch within ±2.
3. **Inversion residual:** the region's median |`timeseries_inversion_residuals`|
   in the DISP product of the step epoch over the frame median.

Synthetic test: a planted −2 and +1 step are recovered in full; a seasonal
signal of 1.1 cycles amplitude is never labelled.

## Results (F08882)

**A step test alone does not identify unwrap errors.**

- A short-window step test labels 40% of the frame, mostly +1 in summer.
- With persistence, 20% of cells still show persistent whole-cycle steps
  (4,491 regions).
- They cluster on a few summer dates across the frame: 2017-06-30, 2019-07,
  2022-12. They are not at ministack boundaries: 26% of step cells sit within
  one epoch of a boundary, against ~20% by chance.

**The inversion residual looked like it separated the two populations**
(almost bimodal), **but the visual check below shows it does not**:

| example region | cells | residual / frame median |
|---|---|---|
| 2021-06-21 +1 | 553 | 0.4 |
| 2020-06-02 −1 | 270 | 0.9 |
| 2019-10-06 +1 | 254 | 0.1 |
| 2019-07-02 +1 | 237 | 88 |
| 2019-07-26 −1 | 235 | 2,170 |
| 2019-07-14 +1 | 230 | 21 |
| **Galveston 2022-07-22 −1** (by TXGA, GAL2, GAL7) | 14 | **212** |

| residual / frame median | regions | regions ≥ 20 cells (≥ 0.65 km²) |
|---|---|---|
| ≥ 3 | 2,651 | 299 |
| ≥ 10 | 2,362 | 266 |
| ≥ 30 | 2,132 | 231 |

- **Not decorrelation.** High-residual regions (≥ 30) have a median temporal
  coherence of 0.38, low-residual ones 0.43; the frame median is 0.44.
- **Galveston:** TS-U1's TXGA −1 (2022-07) is recovered: GAL2/GAL7 −1 on
  2022-07-22 with a residual ratio of 212. TDAM's −2 (2021-07) is not a step
  in the calibrated series: it drifts slowly from +1.3 to +2.1 cycles over
  2020–2022, which reads as a rate error, not unwrapping.

## Visual check (2026-10-23): the residual ratio is not a reliable label

Six random regions ≥ 20 cells from each class (`sample_check_F08882.png`:
region vs surroundings, detrended, and the residual map at the step epoch):

- **High ratio (≥ 30):** four are clear sharp whole-cycle steps against the
  surroundings (2017-07-12 +1 twice, 2021-07-27 −1, 2021-07-15 +1); two are
  gradual divergence, i.e. local deformation, not unwrapping (2022-06-16,
  2017-09-10).
- **Low ratio (< 3):** four are equally clear sharp steps (2021-07-03 +1 twice,
  2022-04-17 −1, 2019-07-14 −1); the others are gradual deformation.

So the residual ratio neither excludes deformation nor catches every step,
and the counts above (231 regions at ratio ≥ 30) are **not** a truth set.
What separates the cases by eye is **sharpness against the surroundings**:
an unwrap error is a k-cycle jump of region − surroundings within one or two
epochs that persists; deformation diverges gradually.

## What it means for T62

- The labeller needs a differential test (cell − local ring) with a sharpness
  condition (the jump within ≤ 2 epochs) before the counts mean anything;
  then a second visual check, and a second frame (LA, F16940).
- Galveston: TXGA's −1 (2022-07) is a step; TDAM's −2 (2021-07) is not one in
  the calibrated series (slow drift).

## Next (T62.2, T62.3)

1. Differential + sharpness labeller; visual check of both classes again;
   LA as the second frame.
2. Extend the estimator (T36) to non-water regions and score it on the labels.
3. Report and the owner's decision on enabling inland correction.

## Reproduce

```bash
python studies/ts_u2.py --stack F08882_cum_ds6.npy --meta F08882_cum_ds6.json \
    --disp-dir FRAME/disp_s1 --out-dir OUT
```

The stack is built with `opera_vlm.stack.GeometryStack.read_cumulative` from
the DISP and DISP-CAL products, averaged 6×6
(`cal_disp_e2e/t62/F08882_cum_ds6.npy`).
