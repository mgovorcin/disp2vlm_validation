# 0005. Velocity statistics use stations that overlap the stack

- **Status:** accepted (owner, 2026-10-30). The consequence for F08882 below is
  open.
- **Changes:** `requirements.GATE.velocity_min_overlap_years = 3.0`,
  `gate.GateConfig.velocity_min_overlap_years`, `gnss.overlap_years`; the run
  writes `overlap_years` to `stations.csv` and `short_overlap_stations` to
  `metrics.json`. A value of 0 restores every station.

## Context

The velocity rules compare InSAR over the stack with each station's MIDAS rate
over the station's whole record. A station that ended before the stack began,
or started after it ended, says nothing about the stack, yet it was scored. On
F38238, 18 of 104 stations overlap by under 2 years: XDHS by 0.02 years, and
TXHU's record ends in 2007.

## Decision

Stations with less than 3 years of GNSS within the stack are left out of the
velocity statistics: all-station, gated and per-class. A stack shorter than 3
years requires the whole stack. These stations stay in `stations.csv` and are
listed in the report.

The DD sill is unchanged, since it uses common dates only. The VLM check is
unchanged, since it compares GNSS with each pair's own dates.

## Effect on the release candidate

The 10 frames of `t50conf`, same products, same baselines
(`cal_disp_e2e/t50conf_overlap3`). Gated stations; mm/yr.

| frame | stations | RMSE | median bias | verdict |
|---|---|---|---|---|
| F07081 | 7 → 3 | 1.79 → 0.82 | +0.97 → +0.81 | PASS |
| F08622 | 89 → 64 | 1.23 → 1.16 | +0.11 → +0.09 | PASS |
| F08882 | 70 → 50 | 4.86 → 4.36 | +0.21 → +0.37 | PASS → **FAIL** |
| F08886 | 24 → 16 | 1.37 → 1.06 | −0.11 → −0.11 | PASS |
| F16940 | 268 → 214 | 3.33 → 2.14 | +0.67 → +0.52 | PASS |
| F16941 | 121 → 108 | 2.16 → 1.93 | +0.45 → +0.40 | PASS |
| F23211 | 18 → 12 | 2.40 → 2.57 | +0.46 → +0.94 | PASS |
| F35991 | 26 → 15 | 3.18 → 1.53 | +0.02 → +0.61 | PASS |
| F36542 | 86 → 78 | 4.32 → 4.38 | +1.84 → +1.84 | PASS |
| F38238 | 45 → 30 | 4.84 → 4.83 | +2.62 → +2.98 | PASS |

- F07081 now has only 3 gated stations, so its velocity numbers carry little
  weight.
- The CalVal report (`docs/vnv/v0.5-calval-report.md`) still has the old
  numbers.

## Open: F08882 fails its benchmark condition

The `subsiding` class of `configs/benchmark/gate_F08882.yaml` must have
RMSE ≤ √(raw² + reference²), where raw has its constant offset removed
(decision 0002).

| | stations | calibrated RMSE | raw RMSE | reference | limit |
|---|---|---|---|---|---|
| before this decision | 32 | 5.93 | 4.43 | 4.23 | 6.12 |
| now, reference as written | 19 | 4.97 | 2.35 | 4.23 | 4.84 |
| now, reference on the same 19 stations | 19 | 4.97 | 2.35 | 0.94 | 2.53 |

- **The old limit was inflated by the stations this decision removes.** They
  raised both the raw RMSE and the reference. The reference 4.23 is the TS-G1
  grid-vs-MIDAS RMSE over all 32 stations of the class (reproduced exactly from
  `ts_g1/F08882/stations_ts_g1.csv`); on the 19 kept stations it is 0.94.
- **The calibrated RMSE is dominated by one station.** TXGA (Galveston, unwrap
  errors, Venti T62) reads −16.7 mm/yr. Without it the RMSE is 3.25, against a
  raw RMSE of 2.29, so the class still does not meet a consistent limit
  (TXBC +6.4 and TXMG +6.3 at Matagorda, UHC1–3 at −4 to −5).
- **Frame-wide the calibration still helps.** Against gamma, the DD sill is
  −60% and the gated RMSE is −0.37 mm/yr.

`gate_F08882.yaml` is not changed here. The owner decides between recomputing
the reference, recording a waiver, or both.
