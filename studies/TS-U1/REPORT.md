# TS-U1 phase 1: whole-cycle unwrap correction on islands

Venti plan T42, PRD §7.2 and R-U1. Run 2026-10-09.

- **Candidate:** v0.5 + `unwrap_error_correction: true` (whole cycles, GNSS
  veto, 12 km anchor). cal-disp `feature/v05-unwrap-hook` (PR #7), Venti
  `c10ba88` (venti-dev PR #21).
- **Baseline:** the T38 v0.5 runs without unwrap.
- **Scoring:** `studies/ts_u1.py`.
- **Runs:** `/mnt/aurora-z0/govorcin/cal_disp_e2e/tsu1/` and
  `runs/<frame>-v05-unwrap`.

## Three bugs found on the way (fixed)

The flag had never run on the v0.5 route:

1. **cal-disp passed no unwrap hook.** With `surface.method: loclin`,
   `unwrap_error_correction: true` was a silent no-op (cal-disp PR #7).
2. **The hook was fed DISP − GNSS − CAL₁ instead of DISP − CAL₁.** The
   estimator's GNSS veto then subtracted the GNSS field twice (Venti
   `8219a52`).
3. **The shift was upsampled to the factor-trimmed size.** Every epoch with
   a shift crashed on a frame not divisible by the downsample factor: 67 of
   204 on F08882 (Venti `c10ba88`).

All three are behind the flag, which defaults to off. The golden is
unchanged.

## Truth set (T42.1)

- **Island stations:** stations in a water-mask region other than the
  mainland, each paired with the nearest mainland station within 30 km.
- **Per-pair truth:** the misfit in cycles between raw DISP and GNSS,
  island − mainland.
- **Labelling:** errors persist through a reference-date block (the
  compressed reference carries them), so the truth is **block-level**. A
  block is labelled when its pairs agree (std < 0.45 cycles) and the mean is
  within 0.25 of a whole cycle.

| frame | island stations with data | blocks | labelled blocks | error blocks |
|---|---|---|---|---|
| F08882 | TXGA, TDAM (Galveston), TXLI | 36 | 18 | 2 (TDAM −2 in 2021-07; TXGA −1 in 2022-07) |
| F16940 | SCIP, CAT2, CAT3 lie 35–100 km offshore, beyond the 12 km anchor | – | – | – |

**The PRD bar (≥ 100 cases) is far out of reach on these frames.**
Pair-level labels (287 cases, 73 apparent errors) are dominated by noise:
the misfit scatter is 0.35–0.8 cycles per pair.

## Estimator (T42.2, T42.3)

| | F08882 | F16940 |
|---|---|---|
| epochs | 204 | 285 |
| region decisions | 6 528 | 2 280 |
| shifts | 92, in 8 regions | 0 (every region too small or not measured) |
| shifts at island stations | 2 pair-level, both correct | – |
| error blocks corrected | 0 of 2 | – |
| decoys: shifts at mainland stations | 0 of 24 684 station-pairs | 0 |

**The Galveston −2-cycle block is not a region offset.**
- In 2021-07 the estimator measures region 20 (Galveston Island, ~100 km²)
  at a median jump of −0.76 cycles, with a GNSS misfit of −0.26.
- At the island stations, the same block is −1.9 to −2.0 cycles.
- So the error covers the station end of the island, not the whole region.
- A per-region whole-cycle shift cannot fix that. It is a sub-region error:
  TS-U1 phase 2 (T62).

## e2e (T42.4)

| frame | DD sill v0.5 → +unwrap (mm²) | change (95% CI) | LOS bias / RMSE (mm/yr) | gate vs v0.5 |
|---|---|---|---|---|
| F08882 | 90.9 → 90.7 | −0.2% [−1.5, +0.7] | +1.14 / 4.79 → +1.37 / 4.31 | FAIL (\|bias\| +0.22) |
| F16940 | 56.5 → 56.5 | 0.0% | unchanged | PASS (identical) |

**On F08882 the correction does what it should, where it should.**
- The five Galveston stations improve by 3.2–6.5 mm/yr: GAL2 −18.5 → −12.0,
  GAL7 −17.1 → −10.6, TXGA −14.2 → −9.4, TDAM −7.7 → −4.2,
  TXGV −7.4 → −4.2.
- The other 121 stations move by +0.03 mm/yr on average.
- The RMSE falls by 0.48 mm/yr. The sill doesn't move, since the DD sill
  uses pairs ≥ 50 km apart.

**The gate FAIL is an artefact of the frame's positive bias** (issue #2).
The Galveston stations were large negative outliers that partly cancelled
it; moving them toward truth raises the mean. A gate on |bias| should not
punish a correction that lowers RMSE and moves outliers toward zero. See
the follow-up.

## Go / no-go (T42.5)

**No-go for enabling the flag in v0.5. The default stays off.**
- The PRD bar (precision ≥ 0.99 and recall ≥ 0.8 on ≥ 100 cases) cannot be
  assessed: there are 2 error blocks in the truth set.
- Recall on what exists is 0 of 2 blocks. The real Galveston error is
  sub-region.
- The gate fails on F08882, even if for the wrong reason.

What the run does show:
- **Safe:** 0 false shifts at mainland stations, and no sill change.
- **It helps the Galveston stations by 3–6 mm/yr.**
- **The trade-study gains on islands came from free offsets (estimator C),
  not from whole cycles.** That explains the T38 gaps (`docs/baselines.md`).
  Free offsets stay out of v0.5 by decision.

## Follow-ups

- **T62 (phase 2):** sub-region / inland errors. Galveston is the test case:
  the error is local to the station end of the island.
- **A truth set with ≥ 100 cases needs frames with many near-shore island
  GNSS sites.** Candidates are Hawaii/PR (T40) and Chesapeake/Delaware bays.
  Or accept block-level truth from regions without GNSS, using the DISP
  inversion residual as a weak label.
- **Gate:** consider comparing |bias| on a fixed station set with outliers
  removed (e.g. > 5 NMAD), or gating on RMSE plus the median bias, so that
  fixing outliers is not penalised. That is an owner decision; gate numbers
  live in `requirements.py` and need a decision record.
