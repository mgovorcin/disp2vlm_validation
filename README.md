# disp2vlm_validation

Independent GNSS validation of OPERA DISP-CAL and VLM products: the CalVal
VnV tool for the DISP-CAL v0.5 release. It compares calibrated displacement
with UNR daily stations and MIDAS rates, never with the gridded GNSS the
calibration is fitted to, and applies the release gate.

**Status:** the per-frame pipeline, gate, reports and CLI are in (plan
T21–T25); it reproduces the trade-study F08882 numbers exactly
([docs/baselines.md](docs/baselines.md)). See [docs/scope.md](docs/scope.md).

```bash
pixi install -e dev
pixi run -e dev disp2vlm-validate gate                      # the release gate and benchmark frames
pixi run -e dev disp2vlm-validate run --config run.yaml     # one candidate on one frame
pixi run -e dev disp2vlm-validate summary RUN_DIR... --out release_summary.html
pixi run -e dev test
```

A run writes `metrics.json`, `report.html` (verdict, DD sills with bootstrap
CIs, velocity vs MIDAS by station class, requirements traceability),
`stations.csv`, `figures/*.svg` and the calibrated velocity GeoTIFF. Runs are
cached by a content hash of the package version, config and input files;
`--no-cache` recomputes. Example configs: `configs/aurora/`. Full frames on
aurora need `NUMPY_MADVISE_HUGEPAGE=0`.

**Private** until the licensing template (Apache-2.0 + NOTICE +
AI_PROVENANCE) is reviewed by JPL Patent/IP counsel and OTT.
