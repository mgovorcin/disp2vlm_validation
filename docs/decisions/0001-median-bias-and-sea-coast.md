# 0001. Median bias in the gate; "coastal" means the sea

- **Status:** accepted (owner, 2026-10-09)
- **Changes:** `requirements.GATE.bias_statistic = "median"`; the `gate.yaml`
  field `bias_statistic`; `classes.classify_stations(sea_min_km2=500)`.

## Context

**Bias.** The gate fails a candidate when its |bias| against MIDAS rises by
more than 0.2 mm/yr over the baseline (PRD §2.7). The release target is
|bias| ≤ 1 mm/yr. Both used the **mean** station residual. On F08882 the
TS-U1 unwrap run corrected five Galveston stations by 3–6 mm/yr toward
MIDAS. They had been large negative outliers on a frame whose bias is
positive (issue #2), so:

- the mean rose from +1.14 to +1.37 mm/yr, and the gate failed (+0.22);
- the RMSE fell from 4.79 to 4.31, and the median stayed at +0.95.

A rule that fails a candidate for fixing outliers judges the outliers, not
the calibration.

**Coastal.** The station classes (PRD §3.4) report metrics separately for
coastal stations, because the coast is where calibration fails differently:
water gaps, islands, unwrapping across water, and the land/sea troposphere.
The rule was "within 10 km of any water in the DISP water mask". Those masks
hold thousands of ponds, reservoirs and rivers; Oklahoma City has ~20 000
water bodies. As a result:

- every F08886 station was "coastal";
- no stable class was left on F08886 or F08882, which is the class TS-B1
  needed.

## Decision

1. **The bias rules use the median of the station residuals.** That covers
   the rise vs baseline (0.2 mm/yr, unchanged), the release target
   (1 mm/yr, unchanged, reported) and the per-class targets. The mean is
   still reported next to it. The RMSE rule is unchanged, so a candidate
   that makes outliers worse still fails. `gate.yaml` can set
   `bias_statistic: mean` for a release that needs the old rule.
2. **"Coastal" is within 10 km of the sea.** The sea is a water body of at
   least 500 km² in the water mask, together with the bays and tidal channels
   joined to it.
   - On the four frames the seas are 900–15 000 km²: the Gulf of Mexico,
     Galveston Bay, the Pacific, and the Atlantic with Long Island Sound.
   - The largest inland water body is ~300 km².
   - `sea_min_km2=0` restores the old rule.

## Consequences on the T38 runs (v0.5 vs gamma)

Gamma → v0.5, mean / median LOS bias in mm/yr:

| frame | mean bias | median bias |
|---|---|---|
| F08882 | +4.05 → +1.14 | +4.35 → +0.95 |
| F08886 | +0.90 → +0.06 | (see `docs/baselines.md`) |
| F16940 | +2.95 → +0.65 | +2.17 → +0.61 |

- All four frames still PASS.
- **The 1 mm/yr release target is now met on all four frames**; with the
  mean, Houston missed it at +1.14.
- **The TS-U1 unwrap run passes the gate under the median.** Its no-go stands
  on the other grounds in `studies/TS-U1/REPORT.md`, and the correction
  stays off.
- **Stable stations reappear** on Oklahoma City and Houston. Class tables in
  the reports change.
