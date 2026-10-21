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
| LA F16940 + F18904 | **v0.5.1 release**, F18904 unlisted | 167 | −0.35 | 1.46 | 2.77 | **PASS** |
| LA F16940 + F18904 | v0.5.2 (F18904 frame entry, venti-dev #44) | 161 | −0.29 | 1.32 | 2.65 | **PASS** |
| LA F16940 + F18904 | **v0.5.3** (+ stratified tropo fix, venti-dev #45) | 172 | −0.38 | 1.29 | 2.71 | **PASS** |
| Houston F08882 + F38238 | v0.5, T46 runs | 18 | +0.23 | 2.03 | 4.17 | not assessable (< 20) |
| Houston F08882 + F38238 | **v0.5.0 release** (confirmation run) | 19 | −0.03 | 2.39 | 3.52 | not assessable (< 20) |

- **LA meets the owner's 1–2 mm/yr target:** 80% of stations are within
  2 mm/yr. Six local sites (BRAN, CRHS, TRAK, WNRA, MILK, GISA) dominate the
  RMSE; without them it is 1.56.
- **LA on the release calibration (2026-10-20) still passes.** F18904, the
  descending partner, is not in the frame table, so the release calibrates it
  without LA's island regions and stratified tropo. Its Catalina offset is
  wrong (CAT2 LOS −54.2 vs GNSS −29.7 mm/yr); before the release the ascending
  offset was wrong the other way and the two cancelled, so CAT2 goes from
  −0.6 to −13.1 mm/yr (GNSS −1.0). Giving F18904 the LA settings
  (frame table 0.7-draft, venti-dev #44) brings CAT2 to −2.1, lowers NMAD to
  1.32 and the F18904 DD sill to −91.4% of raw (−89.0% without). Without the
  six local sites the RMSE is 1.58 (1.56 on the T46 runs). Runs:
  `cal_disp_e2e/t57/{la_release,la_regions,la_full}`.
- **v0.5.3 restores the LA mountain stations.** Up to v0.5.2 the stratified
  tropo model was evaluated only on each epoch's valid DISP pixels, so the
  calibration was NaN on 16–21% of every LA epoch (mostly finite DISP with
  `recommended_mask = 0`). VLM lost those epochs and DAM2, P574, RKMG, VIMT
  and WNRA fell back to single-look projection. With the model evaluated
  wherever DEM and delay exist (venti-dev #45, cal-disp v0.5.3) all five are
  two-look again: 172 gated stations, NMAD 1.29 mm/yr, the best LA result;
  CAT2 −1.6 (GNSS −1.0). Without the six local sites the RMSE is 1.64 on the
  larger station set. Run: `cal_disp_e2e/t57/la_dem`.
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

Those columns are the T46 / v0.5.0 calibrations. On **cal-disp v0.5.3** (LA,
`t57/la_dem`) the spread is 0.76–0.93 at every span up to 7 years, and coverage
of 1.96σ is 0.81–0.92 (0.87–0.96 with `gnss_epoch_estimate: window_fit`):
the long-span growth above came mostly from the NaN tropo holes that v0.5.3
fixed. What is left is not σ but an **offset shared by all stations of a pair**
(`pair_common_mode`, 2026-10-21):

| LA, v0.5.3 | T0 | common mode (mean ± sd over pairs) | coverage 1σ / 1.96σ without it |
|---|---|---|---|
| GNSS 7-day median | 2016-07-31 | +6.4 ± 3.0 mm | 0.76 / 0.92 |
| GNSS window fit (±48 d, like the VLM) | 2016-07-31 | +4.6 ± 2.0 mm | 0.79 / 0.92 |
| GNSS window fit | 2016-10-23 (`t57/la_t0late`) | +6.9 ± 3.0 mm | 0.75 / 0.91 |

- **A third is validation smoothing:** 7-day GNSS medians carry network-wide
  excursions of up to 4 mm that the VLM's 96-day window does not.
- **Part is the GNSS seasonal cycle, absent from the VLM by design:** the
  calibration ties the long wavelengths to a secular (constant-velocity) GNSS
  grid, so a VLM pair has no long-wavelength seasonal term while a station pair
  does (network annual amplitude 3.5 mm). With T0 near the seasonal peak
  (October) the station seasonal predicts the spring/fall alternation of the
  offset (correlation 0.71).
- **The rest, +3 to +4 ± 2 mm,** is a small constant plus a network rate bias
  of ~0.3–0.5 mm/yr, within the gate (|median| ≤ 1 mm/yr). Moving T0 off the
  stack edge does not remove it.
- Station **rates are unaffected** by a shared offset; the per-pair products
  carry it and σ does not include it.

## Open items

- **Catalina CAT3 is a local site.** Its VLM error (+6.3 mm/yr) comes from the
  CAT3 pixel itself, which reads 7 (ascending) and 5 (descending) mm/yr LOS above
  its 1 km surroundings in both looks while the station is stable: a pixel
  artefact on the Two Harbors isthmus, not calibration. The island as a whole
  is tied to GNSS within ~2 mm/yr LOS; an opt-in per-island plane
  (venti-dev #47) removes the remaining tilt but does not change the LA result.
- **Per-pair common mode** (above): decide whether the per-pair VLM documents
  that long-wavelength seasonal motion is not included, or σ gains a
  correlated seasonal term; and whether validation smooths GNSS like the VLM
  (`window_fit`).
- **Houston** in the final edge-case pass.
- **VLM v0.2:** the tiled SAS (Venti plan T63) uses every overlapping asc/desc
  track per MGRS tile, which should help frames like Houston and New York.
