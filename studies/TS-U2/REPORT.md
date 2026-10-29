# TS-U2: unwrapping offsets of water-separated regions (TS-U1 phase 2, Venti plan T62)

**Status:** 2026-10-27. Analysis only. The owner keeps the residual-guided
decision **out of the calibration for now** (2026-10-27), and unwrap-error
correction stays off (2026-10-09).

## Summary

1. **In DISP output, an unwrapping error is a fractional offset of a whole
   region, not a whole-cycle step.**
   - The time-series inversion spreads an error in one interferogram.
   - The region's displacement shifts by a fraction of a cycle (0.3–0.9).
   - The product's `timeseries_inversion_residuals` rises over that region
     (owner, 2026-10-23).
2. **It happens on disconnected land:** islands, peninsulas, the far shore of
   a bay.
   - The median residual of a water-separated region, against the mainland,
     separates three cases on every frame:
     - **consistent:** tracks the mainland;
     - **permanently disconnected:** lifted 2–7 orders in > 90% of epochs;
     - **episodic:** lifted in some epochs, or in whole ministacks.
   - Inland, residual plateaus ≥ 10 km² carry tiny offsets (median 1.4 mm).
     Small patches can be real ground motion (owner, 2026-10-24).
3. **A residual-guided correction works on the regions that need it and
   leaves the others alone.** It removes sharp slips at flagged epochs, plus
   their recoveries. Results (per-area figures `islandfix_*.png`):

| area (frame) | region | effect |
|---|---|---|
| Chesapeake (F00834) | 24.7 km² in the bay | −12-cycle staircase (≈ 330 mm) removed; its −20 mm/yr anomaly gone |
| Chesapeake | 6,283 km² across the bay | 2019–20 dip removed, no new drift; < 0.25 mm/yr velocity change |
| Houston (F08882) | Bolivar Peninsula, 85 km² | 4.9 of 9 cycles of summer slips removed; ~4 cycles of smooth rise remain (no GNSS to judge) |
| SW Florida (F12637) | Lower Keys | disconnected in whole ministacks (7 of 18); +0.5-cycle block offset removed on region 16; the rest only drift |
| E Florida (F40026) | barrier islands | one step; −6 mm/yr gradual drift kept; the 338 km² Cape region is empty in the calibrated product |
| LA (F16940) | Catalina, San Clemente | nothing: GNSS + `regions: separate` keep them on the mainland |
| Houston | Galveston | nothing: consistent with the mainland |

## Survey: median residual per water-separated region

Median log10 |inversion residual| per region and epoch, minus the reference
region's (the land region with the most valid DISP; in SW Florida the largest
region, the Everglades, has no DISP at all). Classes by the share of epochs
lifted ≥ 2 orders: consistent < 5%, episodic 5–90%, permanent > 90%.

| frame | area | regions | consistent | episodic | permanent | `regions` in frame table (0.8) |
|---|---|---|---|---|---|---|
| F00834 | Baltimore / DC, Chesapeake | 12 | 1 | 3 | 8 (incl. 6,283 km²) | none (venti-dev #51 adds it) |
| F00831 | Outer Banks | 19 | 7 | 6 | 6 (707 km²) | none (#51) |
| F40026 | E Florida | 6 | 0 | 5 | 1 (338 km²) | none |
| F38238 | Houston desc | 4 | 0 | 1 | 3 | none (validated, not added) |
| F08622 | New York | 19 | 9 | 10 | 0 | none |
| F08882 | Houston asc | 8 | 1 | 5 | 2 | separate |
| F16940 / F18904 | Los Angeles | 3 | 1 | 0 | 2 | separate |
| F35991 | Puerto Rico | 1 | 0 | 1 | 0 | separate |
| F12637 | SW Florida, Keys | 27 | (Lower Keys disconnected in whole ministacks) | | | none |
| F36008 | Long Island Sound | 22 | 22 | 0 | 0 | none (#51) |

Frames without water-separated regions: F07081, F08886, F16941, F23211, F36542.

The mainland residual itself has two features:
- a sawtooth with each ministack;
- one frame-wide lift in Aug–Oct 2017 (Hurricane Harvey).

`island_residuals_*.png` shows the series.

## Why a region still slips with `regions: separate`

The calibration gives each non-mainland region its own per-epoch offset only
when it has ≥ `region_min_pixels` usable pixels. Bolivar decorrelates every
summer, so its offset is skipped in exactly the epochs where it slips. The
inversion residual flags it in 200 of 205 epochs. A region decision based on
the residual, instead of the valid-pixel count, would address this at the
source. **Not adopted** (owner, 2026-10-27).

## Correction method (`studies/ts_u2.py`)

- **Region flag:** median log10 residual ≥ 2 orders above the reference.
- **Region-minus-reference series** (cycles) on the chained calibrated stack
  (180 m). For offshore islands the reference is the mainland coastal band.
- **Slips:**
  - A 5-epoch median step ≥ 0.5 cycle and ≥ 3σ of the region's own
    epoch-to-epoch noise.
  - It must sit at a flagged epoch or one bordering a flagged run (the exit of
    a disconnected ministack).
  - It is placed on the sharpest single-epoch jump and removed by its own
    size.
  - An opposite step ≥ 0.25 within 60 epochs is removed with it (a dip and
    its recovery).
- **Tests:** a staircase is removed, a dip with its recovery is removed, drift
  is untouched, and a block offset is removed including its unflagged exit.

**What did not work** (on these frames, kept for the record):

| attempt | failure |
|---|---|
| greedy step removal (5-epoch persistence) | removed one edge of a dip only: false drift (Chesapeake) |
| 1-year persistence | missed staircases whose slips recur yearly (Bolivar: 0 removed) |
| joint piecewise-constant segmentation | cut gradual drift into steps and removed real motion (E Florida −6.7 cycles) |
| segment-level sharpness ratio | rejected every staircase split |
| inland residual plateaus (any size) | small patches are ground signal; ≥ 10 km² plateaus carry ~1 mm offsets |
| whole-cycle step detection, residual magnitude ratio (earlier TS-U2) | wrong model: offsets are fractional |

## Recommendations

1. **Frame table:** `regions: separate` where the survey finds permanently
   disconnected regions and GNSS validation agrees. Chesapeake, Outer Banks
   and Long Island are in venti-dev #51. E Florida needs validation first.
   Houston descending was validated and gets no entry yet (below).
2. **The residual is a diagnostic of disconnected regions** for any unlisted
   frame. A check that warns when a frame without `regions` has a
   permanently disconnected region would have caught F18904 (LA descending).
3. **Correction in the calibration:** off (owner). Revisit with GNSS truth on
   a disconnected region without its own station (Bolivar has none).

## Houston descending (F38238) with `regions: separate`

Full stack (378 epochs) with the 0.9 frame table plus `surface.regions:
separate`, scored against the release-candidate run (`t50conf`), 2026-10-29.
Figure: `F38238_regions_vs_release.png`.

| metric | release | regions | change |
|---|---|---|---|
| DD sill (mm²) | 81.3 | 81.0 | −0.4% |
| velocity RMSE, gate stations (n=45) | 4.84 | 4.45 | −0.39 |
| median bias, gate stations | 2.62 | 2.44 | −0.18 |
| velocity RMSE, all stations (n=100) | 4.55 | 4.37 | −0.18 |
| verdict | PASS | PASS | |

- **The survey's targets are untouched.** The three permanently disconnected
  regions are islets of 2–7 km² in Galveston Bay. They carry no station, and
  their velocity barely changes.
- **The change is inland.** Rivers and reservoirs split the mainland into
  blocks, and each block gets its own offset. 31% of pixels move by more than
  0.5 mm/yr and 7% by more than 2 mm/yr, in blocks in the NW, W and NE.
- **GNSS support is mixed.** Of the 14 stations that move by more than 0.5
  mm/yr, 10 improve and 4 get worse by 1–2 mm/yr.
  - Most of the RMSE gain comes from one station, XDHS, in the NE block: its
    residual goes from +9.8 to −5.0 mm/yr.
  - Without XDHS, the RMS over the other 13 stations is 4.67 → 4.60 mm/yr.

**Recommendation: no frame-table entry for F38238 for now.** The islets are
too small to matter, and the inland re-leveling is supported by one station.
The NE block around XDHS is worth a look on its own.

## Reproduce

```bash
python studies/ts_u2.py --stack F08882_cum_ds6.npy --meta F08882_cum_ds6.json \
    --disp-dir FRAME/disp_s1 --out regions.json
```

The stack is `opera_vlm.stack.GeometryStack.read_cumulative` of the DISP and
DISP-CAL products averaged 6×6 (`cal_disp_e2e/t62/*_cum_ds6.npy`). The figures
were made with the prototype scripts behind `cal_disp_e2e/t62/maps/`. That
version placed a slip within ±2 epochs of the sharpest jump; `ts_u2.py` places
it on it.
