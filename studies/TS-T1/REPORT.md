# TS-T1: tropospheric correction at 0.3–1.5 km relief

Venti plan T44.1, PRD R-T1. Run 2026-10-14.

## Question

cal-disp v0.5 removes a tropospheric correction from DISP before the fit
(OPERA TROPO-ZENITH), in one of three modes: `off`, `full` (the whole
modelled delay) or `stratified` (a per-pair fit of the delay against height).
Venti's `auto` rule chooses from the DEM relief (5th–95th percentile):

- off below 0.3 km;
- stratified at 1.5 km or more;
- **off in between, until this study**.

Earlier trade studies put the two ends there: stratified helped Los Angeles
(1.56 km; DD sill −15%) and hurt flat Houston (0.12 km; +17%). Does the
correction help in the band between?

## Frames and runs

Relief of the benchmark frames (p5–p95 of the DISP-S1-STATIC DEM over land):
Houston 0.12, New York 0.42, Puerto Rico 0.70, Montana 1.07, Los Angeles
1.56, Hawaii 1.62, Ridgecrest 1.90, Central Valley 2.84 km. Three frames fall
in the band:

| Frame | Relief | Climate | Stations gated |
|---|---|---|---|
| F08622 New York | 0.42 km | humid continental | ~60 |
| F35991 Puerto Rico | 0.70 km | tropical, island | 26–28 |
| F07081 Montana | 1.07 km | semi-arid | 7 |

- **Candidates:** the frame's v0.5 configuration with `tropo.mode` set to
  `stratified` and to `full`. TROPO-ZENITH was staged for every date; every
  pair of every run had the correction applied (checked per pair in the
  cal-disp logs).
- **Baseline:** the same configuration with tropo off, so the comparison is
  paired: same stations, same bootstrap resamples.
- **Configs:** `configs/benchmark/ts_t1/` (Puerto Rico, Montana). New York
  is from the earlier two-pass trade-study runs (the v0.5 precursor), with
  the same comparison against tropo off.

## Results

Change against tropo off. The sill change has its 95% station-bootstrap
interval; a change counts as significant when the interval excludes zero.

| Frame | Mode | DD sill | velocity RMSE | \|median bias\| | Gate vs off |
|---|---|---|---|---|---|
| New York (0.42 km) | full | **+5.6%** [+2.1, +10.6] | +0.01 | +0.01 | FAIL (sill) |
| New York | stratified | **+8.2%** [+1.7, +12.8] | −0.00 | −0.04 | FAIL (sill) |
| Puerto Rico (0.70 km) | full | −3.3% [−13.2, +5.7] | −0.42 | −0.29 | PASS |
| Puerto Rico | stratified | −12.4% [−21.2, +2.2] | −0.38 | −0.41 | PASS |
| Montana (1.07 km) | full | **+7.2%** [+4.8, +9.0] | +0.05 | **+0.30** | FAIL (sill, bias) |
| Montana | stratified | −3.5% [−9.0, +0.9] | **+0.79** | +0.04 | FAIL (RMSE) |

Velocities are in mm/yr, on the gated stations against MIDAS.

- **New York:** both modes add long-wavelength error (significant sill
  rise), and the velocities do not change.
- **Puerto Rico:** both modes improve the velocities by about 0.3–0.4 mm/yr
  in RMSE and in |bias|. Stratified lowers the sill by 12%, but the
  interval reaches +2%, so the sill alone is not conclusive. With
  stratified, one coastal station (NWRC) has no calibrated value: the
  stratified fit leaves a gap there.
- **Montana:** full adds error (sill +7%, bias +0.3). Stratified lowers the
  sill slightly but raises the velocity RMSE by 0.8 mm/yr. Montana has only
  7 gated stations, so its velocity numbers are weak either way.

## Conclusions

1. **Relief alone does not decide the mode in this band.** The same
   correction hurts New York (0.42 km) and Montana (1.07 km) and helps
   Puerto Rico (0.70 km). What sets Puerto Rico apart is a humid tropical
   troposphere over an island, where the delay varies most with height and
   weather.
2. **`auto` stays off between 0.3 and 1.5 km.** No change to the default
   rule.
3. **Puerto Rico: `stratified` in the frame table.**
   - Both modes pass against off, and both improve the velocities.
   - Stratified has the larger sill drop and the larger bias improvement.
   - Venti frame table: `tropo.mode = stratified` for F35991.
4. **New York, Montana: `off`** (New York is already off in the frame table;
   Montana has no entry, which is off).
5. **Not covered:** other humid, high-relief frames (e.g. Hawaii's windward
   side) may behave like Puerto Rico. Hawaii (1.62 km) is above the band, so
   `auto` already chooses stratified there, but it has not been run with
   tropo on. That is the next check, if a wet-tropics frame matters for the
   release.

## Reproduce

```bash
export E2E_ROOT=...   # configs/benchmark/README.md
disp2vlm-validate run --config configs/benchmark/ts_t1/F35991_v05regtstrat_vs_off.yaml
```

The candidate products come from cal-disp runs with
`configs/benchmark/ts_t1/algorithm_parameters_*.yaml` and the staged
TROPO-ZENITH files.

## Addendum (2026-10-15): Hawaii above the band

Hawaii (F23211, relief 1.62 km) is above the band, so `auto` would choose
`stratified` there. Until now it had only run with tropo off. This run uses the
release configuration (cal-disp v0.5.0, the frame table) with `tropo.mode:
stratified`, validated against the same configuration with tropo off (the
confirmation run). Stratified was applied on every pair (328/328).

| Hawaii | tropo off (v0.5.0) | stratified |
|---|---|---|
| DD sill | 409.7 | 286.8 (**−27.8%** [−43.2, −18.0]) |
| gated median / RMSE (18 stations) | +0.46 / 2.40 | +0.96 / 2.30 |
| stable class (6 stations) median / RMSE | +1.49 / 2.89 | +1.90 / 3.08 |
| coastal class (9 stations) median / RMSE | −0.24 / 2.28 | −0.49 / 1.88 |
| gate against tropo off | – | **FAIL**: \|median bias\| up 0.50 mm/yr (limit 0.2) |

- **Stratified removes long-wavelength error:** the sill falls 28%, and the
  drop is significant.
- **The absolute median bias rises by 0.5 mm/yr,** driven by the six stable
  stations.
- **Hawaii stays off.** That is the frame table's current setting (no tropo
  entry). A run with `auto` would choose stratified here, so `auto` is not
  recommended for Hawaii.
- **Worth revisiting:** the sill gain is large. A bias of this size on six
  stations may reflect local station behaviour rather than the correction.
  Revisit with more stations, or with a per-class view of the bias.

Config: `configs/benchmark/ts_t1/F23211_tstrat_vs_final.yaml`; run
`$E2E_ROOT/runs/F23211-final-tstrat`.
