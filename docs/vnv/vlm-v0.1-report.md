# VLM v0.1 validation report

- **Release:** opera_vlm v0.1.0 (VLM-S1), Venti plan T57
- **Status:** draft, 2026-10-16
- **Inputs:** DISP-S1 + DISP-CAL (cal-disp v0.5) on asc/desc frame pairs
- **Validator:** `disp2vlm-validate vlm`, independent GNSS (UNR daily stations,
  MIDAS), never the calibration grid

## Gate (decision 0003)

Per-station vertical rates (VLM minus GNSS up) on stations seen by both looks
(`mode` 1), outside deforming areas and event footprints. **Pass:**
\|median\| ≤ 1 mm/yr and NMAD ≤ 2 mm/yr, on at least 20 stations. RMSE is
reported, not gated.

## Results

| Frames | DISP-CAL | gated n | median | NMAD | RMSE (mm/yr) | verdict |
|---|---|---|---|---|---|---|
| LA F16940 + F18904 (2016–2023) | v0.5, T46 runs | 172 | −0.42 | 1.44 | 2.67 | **PASS** |
| Houston F08882 + F38238 | v0.5, T46 runs | 18 | +0.23 | 2.03 | 4.17 | not assessable (< 20) |
| Houston F08882 + F38238 | **v0.5.0 release** (confirmation run) | 19 | −0.03 | 2.39 | 3.52 | not assessable (< 20) |

- **LA meets the owner's 1–2 mm/yr target:** 80% of stations are within
  2 mm/yr. Six local sites (BRAN, CRHS, TRAK, WNRA, MILK, GISA) dominate the
  RMSE; without them it is 1.56.
- **Houston is an edge case.** Most of its stations are inside the
  Houston-Galveston subsidence area, so 19 remain for the gate. On the release
  calibration the median moves to zero and RMSE improves (the worst stations
  improve by 2–3 mm/yr), but NMAD rises to 2.39.
- **New York and Montana** are limited by data: New York's descending DISP has a
  2020–2022 gap, and Montana has no winter DISP and two stations. Oklahoma City
  has no descending DISP-S1.

## σ realism (reported)

Coverage of \|z\| < 1.96 and the robust spread of z, by span:

| span (yr) | LA coverage / NMAD(z) | Houston (release) coverage / NMAD(z) |
|---|---|---|
| 0 | 0.76 / 0.82 | 0.97 / 0.84 |
| 1 | 0.89 / 0.82 | 0.93 / 0.87 |
| 2 | 0.85 / 0.87 | 0.87 / 1.04 |
| 3 | 0.77 / 1.16 | 0.79 / 1.19 |
| 5 | 0.81 / 1.14 | 0.82 / 1.49 |
| 7 | 0.68 / 1.45 | 0.71 / 1.47 |

- **The per-look `sigma_rate` term** (1.5 mm/yr) keeps the spread near 1 up to
  about 2 years.
- **Beyond 3 years σ under-covers** (coverage 70–80%, NMAD(z) 1.1–1.5): the
  error grows faster than linearly with the span. Open for v0.2.

## Open items

- **Re-run LA on the v0.5.0 release calibration.** LA's frame table now has
  stratified tropo and island regions; the LA numbers above use the T46
  calibration.
- **Long-span σ realism** (above).
- **Houston** in the final edge-case pass.
- **VLM v0.2:** the tiled SAS (Venti plan T63) uses every overlapping asc/desc
  track per MGRS tile, which should help frames like Houston and New York.
