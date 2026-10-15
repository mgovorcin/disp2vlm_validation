# Metrics and the gate

## Independent GNSS only

The validator uses UNR daily station positions and their MIDAS velocities,
through [geepers](https://github.com/mgovorcin/geepers). It never reads the
UNR *gridded* field the calibration is fitted to: a comparison with the
calibration's own input would only measure the fit. This cannot be switched
off (`GATE.independent_gnss_only`).

GNSS is fetched once per frame and frozen in `cache_dir`, so every candidate
on a frame meets the same stations.

## Velocity against MIDAS

At each station, the InSAR LOS velocity (the station's pixel, and the median
of a `window` × `window` neighbourhood) is compared with the station's MIDAS
east/north/up velocity projected onto the line of sight. Reported per station
class: n, bias, median, RMSE, correlation, and σ realism when σ is given.

Velocities are relative: raw DISP has an arbitrary reference, so raw is
compared after removing its constant offset; DISP-CAL is absolute and is
compared as is.

## Double-difference sill

For every pair of stations A, B: the InSAR-minus-GNSS misfit of the relative
LOS series (B − A) over their common dates, reduced to an RMSE about its
mean; `γ = rmse² / 2` is its semivariance. Differencing between stations
cancels the datum, so raw and calibrated are compared on equal terms.

- **Sill:** the median γ over pairs at least `sill_min_km` apart: the
  long-wavelength error, the thing calibration removes.
- **Near field:** the median γ over pairs closer than `near_max_km`
  (reported).
- **Intervals:** a station bootstrap. Stations are resampled with
  replacement, each pair weighted by its stations' counts, and the weighted
  median recomputed. Raw, candidate and baseline share the same resamples,
  so their differences are paired.

## Station classes

Each station gets the first class that applies:

| # | Class | Rule |
|---|---|---|
| 1 | `near_event` | inside an event footprint (`event_geojson`) |
| 2 | `defo_area` | inside a deforming area (`defo_geojson`) |
| 3 | `subsiding` | GNSS vertical rate below −3 mm/yr |
| 4 | `coastal` | within 10 km of the sea: a water body of at least 500 km² in the water mask, with bays and channels joined to it |
| 5 | `stable` | everything else |

## The release gate

A run **fails** when any of these holds (decisions 0001–0003):

| Rule | Fails when |
|---|---|
| GATE-1 | the calibrated DD sill is not below raw |
| GATE-2 | the sill rises more than 5% against the baseline, and the bootstrap interval of the rise is above zero |
| GATE-3 | velocity RMSE, or \|median bias\|, against MIDAS rises more than 0.2 mm/yr against the baseline (stations outside `defo_area` and `near_event`) |
| GATE-4 | the golden-epoch check fails |
| benchmark condition | a `gating` per-class target of the frame is missed |

Reported, not gating: \|median bias\| above 1 mm/yr, missed non-gating
per-class targets, and σ realism.

## σ realism

`z = residual / sqrt(σ_insar² + σ_gnss²)`. If the uncertainties are right,
std(z) is near 1 and about 95% of |z| are below 1.96. Reported, not gated.

## VLM

See [tutorial 4](../tutorials/04-vlm.md): pair residuals, station rates and
the VLM gate (\|median\| ≤ 1 and NMAD ≤ 2 mm/yr on at least 20 stations seen
by both looks, outside deforming areas and event footprints).
