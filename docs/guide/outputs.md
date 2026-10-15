# Outputs

## A frame run (`run`)

In `out_dir`:

| File | Contents |
|---|---|
| `report.html` | Verdict and reasons, notes, DD sills with intervals, velocity by class, figures, requirements traceability. |
| `metrics.json` | Everything in the report: `verdict`, `verdict_reasons`, `notes`, `double_difference` (raw, calibrated, baseline), `sill_change_vs_raw`, `sill_change_vs_baseline`, `velocity_los`, `velocity_los_gate`, `velocity_by_class`, `velocity_by_class_raw`, `golden_epoch_check`, station counts, the config hash and package version. |
| `stations.csv` | Per station: position; MIDAS rates and σ; pixel row/col; LOS vector; GNSS LOS rate; InSAR raw and calibrated at the pixel (`pix::`) and window median (`med::`); class. |
| `station_series_mm.csv` | Calibrated LOS series at each station (dates × stations). |
| `calibrated_velocity_mm_yr.tif` | Calibrated LOS velocity on the DISP grid. |
| `sill_draws.npz` | Bootstrap draws of every sill. |
| `figures/semivariogram.svg` | DD semivariogram, raw, calibrated and baseline. |
| `figures/velocity_scatter.svg` | InSAR against GNSS LOS velocity per station. |
| `figures/class_rmse.svg` | RMSE by station class. |

In `cache_dir` (shared by every run on the frame): `gnss_midas_enu.csv`,
`gnss_enu_daily.csv.gz`, and per stack `stack_<key>/` with the raw velocity,
the mean temporal coherence and the raw station series.

## A VLM run (`vlm`)

`metrics_vlm.json`, `pair_residuals.csv`, `station_rates.csv`.

## A summary (`summary`)

One HTML page: a row per run linking to its `report.html`, and the
requirements traceability across runs.
