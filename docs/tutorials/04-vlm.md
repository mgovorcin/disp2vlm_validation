# 4. Validate VLM products

A VLM run combines calibrated ascending and descending DISP into vertical
(and east) motion. It writes one product per target pair `(T0, Tk)`, all
sharing `T0`, with the layers `vertical`, `vertical_std`, `east` and `mode`
(1 = both looks, 2 = one look). `disp2vlm-validate vlm` scores them against
the same independent GNSS.

## `vlm.yaml`

```yaml
label: la-v05
frame: F16940
products_dir: vlm/F16940_F18904/products
cache_dir: F16940/cache          # the frame's frozen GNSS cache (shared with DISP-CAL runs)
out_dir: validation/vlm/F16940
defo_geojson: venti/data/defo_area_db_v1.geojson
event_geojson: venti/data/event_db_v1.geojson
exclude_stations: []
half_window_days: 3      # GNSS: median of daily solutions within ±3 days of T0 and Tk
min_pairs: 5             # a station rate needs at least 5 products
min_span_years: 2.5      # ... spanning at least 2.5 years
```

```bash
disp2vlm-validate vlm --config vlm.yaml
```

```text
F16940 la-v05: PASS (n=172, median -0.42, NMAD 1.44, RMSE 2.67 mm/yr)
```

(The numbers are from the Los Angeles run of 2026-10-12, F16940 + F18904,
2016–2023.)

## What it measures

- **Pair residuals:** each product (3 × 3 pixel median at the station) minus
  the GNSS displacement over the same span, vertical and east.
- **Station rates:** the slope of the product's vertical series at a station
  minus the slope of the GNSS up series at the same epochs. The gate is on
  these.
- **σ realism:** `z = residual / vertical_std`, binned by span: the coverage
  of `|z| < 1.96` (95% if σ is right) and the robust spread of z.

## The VLM gate (decision 0003)

On stations seen by both looks, outside deforming areas and event
footprints:

| | limit |
|---|---|
| \|median\| of the rate residuals | ≤ 1 mm/yr |
| NMAD of the rate residuals | ≤ 2 mm/yr |
| stations | ≥ 20 |

RMSE is reported but not gated: a few local sites (landslides, wells, the
coast) dominate it.

## Outputs

`metrics_vlm.json` (statistics and verdict), `pair_residuals.csv` (one row
per product and station) and `station_rates.csv` (one row per station).

Next: [a release summary across frames](05-release-summary.md).
