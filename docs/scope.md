# Scope

`disp2vlm_validation` judges OPERA DISP-CAL (and later VLM) products against
GNSS the calibration never saw. It is the CalVal VnV tool for the v0.5
release (Venti `docs/specs.md` §2.7 and §3.4; plan T11 and T21–T25).

## What it uses, and what it never uses

- **Uses:** UNR daily station positions and their MIDAS rates (through
  `geepers[analysis]`), the DISP-S1 products, and the DISP-CAL products under
  test.
- **Never uses:** the UNR gridded field the calibration is fitted to. A
  validation against the calibration's own input would only measure the fit.
  This is an invariant (`CLAUDE.md`), and `GATE.independent_gnss_only` cannot
  be switched off.

## Metrics

| Metric | Definition | Source |
|---|---|---|
| DD sill | double-difference semivariogram sill over station pairs ≥ 50 km, station-bootstrap 95 % CI | e2e_validation trade study |
| Velocity vs MIDAS | RMSE, bias, correlation per station class: stable, subsiding, coastal, defo area, near event | §3.4 |
| Golden epoch | one fixed pair checked against its golden product | §2.7 |
| VLM | U vs GNSS Up, E vs GNSS East (after VLM v0.1) | §3.4 |
| σ realism | z-scores of residuals over σ_CAL ⊕ σ_DISP | R-E1, R-E2 |

## Modes

- **candidate vs raw:** does calibration help at all (sill must drop);
- **candidate vs baseline:** does the new algorithm beat the released one
  (sill rise ≤ 5 % unless not significant; velocity RMSE and |bias| rise
  ≤ 0.2 mm/yr);
- **across frames:** the 8-frame benchmark summary.

## Release gate (§2.7)

A run **fails** if the calibrated sill is not below raw, the sill rises more
than 5 % vs baseline and significantly, velocity RMSE or |bias| rises more
than 0.2 mm/yr, or the golden-epoch check fails. Target: |bias| ≤ 1 mm/yr per
frame. The numbers live in `disp2vlm_validation.requirements.GATE`;
`disp2vlm-validate gate` prints them.

## Benchmark frames

| # | Category | Frame |
|---|---|---|
| 1 | Coastal subsidence + islands | F08882 Houston |
| 2 | Stable inland | F08886 Oklahoma City |
| 3 | High relief + islands | F16940 Los Angeles |
| 4 | Northeast / GIA | F08622 New York |
| 5 | Fast basin (defo area) | Central Valley (TBD) |
| 6 | Coseismic event | Ridgecrest 2019 (TBD) |
| 7 | Sparse GNSS | Great Basin or Montana (TBD) |
| 8 | Non-NA plate | Hawaii / Puerto Rico (TBD) |

## Outputs

`metrics.json` and `stations.csv` per run; an HTML/PDF VnV report per frame
and a release summary; a requirements traceability table. Audience: the
internal team and the OPERA CalVal review.

## Not in scope

Making products (that is cal-disp / Venti), staging DISP stacks at scale
(the batch pipelines), and anything that would put this package in the
operational image.

## Roadmap (Venti plan)

T21 port the e2e core (`trade studies/e2e_validation/validate_stack.py`) →
T22 station classes → T23 gate logic and comparison modes → T24 reports and
traceability → T25 CLI, caching, batch execution.
