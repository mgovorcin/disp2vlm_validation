# Configuration

Three YAML files. Paths may be relative (to the working directory) or
absolute. Unknown keys are an error, so a typo cannot pass silently.

## `run.yaml`

One candidate on one frame: `disp2vlm-validate run --config run.yaml`
(`disp2vlm_validation.pipeline.RunConfig`).

| Field | Default | Meaning |
|---|---|---|
| `label` | **required** | Name of the candidate in reports and summaries. |
| `frame` | **required** | The frame's inputs, below. |
| `candidate_dir` | **required** | The candidate's DISP-CAL products, flat or `products/<ref>_<sec>/` (searched recursively). |
| `out_dir` | **required** | Where the run writes its outputs. |
| `baseline_dir` | none | Output folder of the baseline's own validation run; enables the comparison rules. |
| `gate` | none | A `gate.yaml` for this frame (below); without it, the release defaults. |
| `golden` | none | Golden-epoch check (below). |
| `window` | 7 | Side of the window, in pixels, whose median is compared with each station (next to the station's own pixel). |
| `min_window_pixels` | 10 | Fewer valid (land, finite) pixels in the window and the station gets no value. |
| `min_epochs` | 5 | A pixel needs at least this many epochs for a velocity. |
| `coh_threshold` | 0.5 | The calibrated velocity is kept where the stack's mean temporal coherence is at least this. |
| `min_common_dates` | 30 | A station enters the double differences with at least this many dates in common with the InSAR series. |
| `sill_min_km` | 50 | The DD sill is the median over station pairs at least this far apart. |
| `near_max_km` | 10 | The near-field semivariance is reported over pairs closer than this. |
| `n_boot` | 1000 | Station-bootstrap resamples for the sill intervals. |
| `seed` | 0 | Bootstrap seed. |
| `workers` | 6 | Parallel readers of the stack (0 = in process). |
| `allow_partial` | false | Skip DISP pairs without a DISP-CAL product instead of stopping. |
| `min_span_years` | 2.0 | When GNSS is fetched: stations with a shorter record are dropped. |

### `frame`

| Field | Default | Meaning |
|---|---|---|
| `frame` | **required** | Frame name, e.g. `F08886`. |
| `disp_dir` | **required** | Folder of the frame's `OPERA_L3_DISP-*.nc`. |
| `water_mask` | **required** | GeoTIFF on the DISP grid, 1 = land. |
| `los_file` | **required** | 3-band line-of-sight ENU GeoTIFF on the DISP grid (DISP-S1-STATIC). |
| `cache_dir` | **required** | The frame's frozen GNSS, and the raw-stack cache; fetched and filled on the first run. |
| `ref_pixel` | the last DISP product's | `[row, col]` reference of the raw velocity. |
| `exclude_stations` | `[]` | Stations dropped entirely, e.g. with a known bad record. |
| `held_out_fraction` | 0.0 | Share of stations set aside (hash of the id, stable everywhere) and never validated on: those a study may fit parameters to. |
| `defo_geojson` | none | Deforming-area polygons (Venti area database): class `defo_area`. |
| `event_geojson` | none | Event footprints (Venti event database): class `near_event`. |
| `pixel_m` | 30 | DISP posting in metres (distances to the sea for the coastal class). |

### `golden`

| Field | Default | Meaning |
|---|---|---|
| `golden_product` | **required** | The golden DISP-CAL product of one pair. |
| `tag` | **required** | That pair, `<ref>_<sec>`, e.g. `20220111_20220722`. |
| `executable` | `cal-disp` | Whose `validate` compares the candidate's product for `tag` with the golden (GATE-4). |

## `gate.yaml`

A frame's gate (`disp2vlm_validation.gate.GateConfig`). Every key is
optional; the defaults are the release gate (`disp2vlm-validate gate`), and a
change to them needs a decision record.

| Field | Default | Meaning |
|---|---|---|
| `release` | `v0.5` | The release the gate applies to. |
| `sill_min_km` | 50 | Pair distance for the sill. |
| `sill_rise_max_pct` | 5 | GATE-2: allowed sill rise against the baseline (if significant). |
| `velocity_rmse_rise_max_mm_yr` | 0.2 | GATE-3: allowed velocity RMSE rise against the baseline. |
| `velocity_bias_rise_max_mm_yr` | 0.2 | GATE-3: allowed \|bias\| rise against the baseline. |
| `bias_statistic` | `median` | The bias statistic: `median` (decision 0001) or `mean`. |
| `target_abs_bias_mm_yr` | 1.0 | Release target for \|bias\| (reported). |
| `significance_ci` | 0.95 | Bootstrap interval for "significant". |
| `velocity_excluded_classes` | `[defo_area, near_event]` | Classes left out of the velocity rules (decision 0002). |
| `velocity_min_overlap_years` | 3.0 | Stations whose GNSS record overlaps the stack by less than this are left out of the velocity statistics (decision 0005). |
| `per_class_targets` | `{}` | Targets per station class, below. |

### Per-class targets

| Field | Default | Meaning |
|---|---|---|
| `max_abs_bias_mm_yr` | none | \|bias\| limit for the class. |
| `max_rmse_mm_yr` | none | RMSE limit for the class. |
| `rmse_must_drop_vs_raw` | false | The class RMSE must be below raw's (raw with its constant offset removed): the calibration must improve on DISP there. |
| `reference_rmse_mm_yr` | none | With `rmse_must_drop_vs_raw`: the GNSS reference's own accuracy for the class (from trade study TS-G1). The limit becomes `sqrt(raw² + reference²)`. |
| `gating` | false | A miss FAILS the run instead of being a note: a frame's benchmark condition. |

## `vlm.yaml`

One VLM run: `disp2vlm-validate vlm --config vlm.yaml`
(`disp2vlm_validation.vlm.VlmRunConfig`).

| Field | Default | Meaning |
|---|---|---|
| `label` | **required** | Name of the run. |
| `frame` | **required** | Frame name. |
| `products_dir` | **required** | Folder of the run's VLM products. |
| `cache_dir` | **required** | The frame's frozen GNSS cache (the DISP-CAL runs' cache). |
| `out_dir` | **required** | Where the outputs go. |
| `defo_geojson`, `event_geojson` | none | As for `run.yaml`: those stations are reported, not gated. |
| `exclude_stations` | `[]` | Stations dropped entirely. |
| `half_window_days` | 3 | GNSS displacement at a date: median of the daily solutions within ± this many days. |
| `min_pairs` | 5 | A station rate needs at least this many products. |
| `min_span_years` | 2.5 | ... spanning at least this long. |
| `min_gnss_span_years` | 2.0 | When GNSS is fetched: shorter station records are dropped. |
