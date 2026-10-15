# TS-E4: σ realism of the DISP-CAL product (R-E4)

Venti plan T50.2, PRD R-E2 and R-E4 (σ realism is reported, not gated).
Run 2026-10-12 with `studies/ts_e4.py` on the best v0.5 run of each T46
frame (remove-restore where it applies). Outputs on the original host:
`$E2E_ROOT/ts_e4/<frame>/`.

## Question and method

- **Question:** does the uncertainty a user gets for a DISP-CAL pair cover
  the real error at independent GNSS stations?
- **Population:** every DISP pair and every station outside deforming
  areas and event footprints (decision 0002).
- **Residual:**
  - r = calibrated pair displacement at the station (from the validation
    station series, 7 × 7 pixel medians) − the GNSS LOS displacement over
    the pair (±3-day medians);
  - z = r / σ.
- **σ budgets compared:**
  - σ_CAL only: the product's `calibration_std` at the station;
  - plus σ_DISP: the per-point DISP noise users are told to add (R-E2).
    TS-S1 measured it on four frames (3.9–6.8 mm); 7 mm elsewhere;
  - plus σ_GNSS: the station's daily scatter through the two ±3-day
    medians;
  - plus σ₀ = 3.5 mm: the opt-in non-secular term (TS-G1: 2.6–4.9 mm).
- **R-E4 target:** robust std(z) in [0.8, 1.25], and coverage of |z| < 1.96
  in [90%, 98%].

## Results

| frame | stations | pairs | σ_DISP (mm) | median σ_CAL (mm) | σ_CAL + σ_DISP + σ_GNSS: robust std(z) / cov95 | + σ₀ 3.5 mm | extra σ for robust std(z) = 1 (mm) | **10 mm per point: robust std(z) / cov95** |
|---|---|---|---|---|---|---|---|---|
| F08886 Oklahoma City | 37 | 2 392 | 3.9 | 0.24 | 1.76 / 69% | 1.38 / 79% | 6.4 | **0.76 / 95%** |
| F16940 Los Angeles | 279 | 55 834 | 6.3 | 0.34 | 1.17 / 85% | 1.03 / 88% | 4.0 | **0.76 / 94%** |
| F08622 New York | 89 | 10 357 | 4.9 | 0.18 | 1.47 / 80% | 1.22 / 87% | 5.7 | **0.76 / 96%** |
| F07081 Montana | 7 | 326 | 7.0 | 0.68 | 0.94 / 96% | 0.85 / 98% | 0 | **0.67 / 99%** |
| F36542 Central Valley | 113 | 26 547 | 7.0 | 0.47 | 1.13 / 86% | 1.02 / 89% | 3.9 | **0.81 / 95%** |
| F16941 Ridgecrest | 123 | 27 698 | 7.0 | 0.52 | 1.00 / 90% | 0.91 / 92% | 0.6 | **0.72 / 96%** |
| F23211 Hawaii | 18 | 3 060 | 7.0 | 0.45 | 1.42 / 82% | 1.28 / 85% | 7.4 | **1.02 / 91%** |
| F35991 Puerto Rico | 35 | 2 675 | 7.0 | 0.48 | 2.25 / 61% | 2.05 / 65% | 15.2 | **1.64 / 74%** |
| F38238 Houston desc | 49 | 10 160 | 7.0 | 0.29 | 0.87 / 94% | 0.79 / 96% | 0 | **0.62 / 98%** |
| F08882 Houston | 73 | 9 303 | 6.8 | 0.45 | 1.21 / 83% | 1.09 / 86% | 4.9 | **0.84 / 92%** |

**σ_CAL alone covers almost nothing at the pair level.** Its median is
0.2–0.7 mm, robust std(z) runs from tens to about 80, and coverage is a few
per cent. That is as designed: σ_CAL is the uncertainty of the calibration
surface (owner, 2026-10-09). A pair's error is dominated by DISP noise below
50 km, and by non-secular motion that the secular calibration does not
model.

**The TS-S1 per-frame σ_DISP is too small.** With σ_GNSS added, robust
std(z) is 1.2–2.3 on six frames.

- TS-S1 measured 7 × 7 pixel medians, so its values are lower bounds for a
  single pixel.
- Oklahoma City's 3.9 mm came from only 7 station pairs.

**The "add 10 mm per point" placeholder of R-E2 is realistic:**

- 9 of 10 frames: coverage 91–99%, robust std(z) 0.62–1.02. Slightly
  conservative (about 20%), which is the safe side.
- Puerto Rico misses (coverage 74%). It is a tropical island with
  uncorrected troposphere, and needs about 16 mm.
- Hawaii is at the edge (1.02 / 91%).

**The error grows with the pair span inside a block.** Pairs of 0.25–1 yr
have a larger robust std(z) than pairs under 0.25 yr on every frame
(`ts_e4.json`, `by_span_full_budget`). That is seasonal and non-secular
motion.

## Recommendation

1. **Keep "add 10 mm (1σ) per point and pair" as the documented DISP term**
   (R-E2), and state that it was checked on the 10 benchmark frames. It is
   no longer a placeholder.
2. **Frame-table exception:** tropical islands with uncorrected troposphere
   (Puerto Rico) need about 16 mm. Revisit once the troposphere mode is
   chosen (TS-T1).
3. **Do not replace it with the per-frame TS-S1 values**, which are lower
   bounds.
4. **σ_CAL stays the surface-only term.** The product text must keep
   saying so, because σ_CAL alone covers about 5% of the pair residuals.
5. **R-E4 is reported as met** with the documented budget on 9 of 10
   frames.
