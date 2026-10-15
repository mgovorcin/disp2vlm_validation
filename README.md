# disp2vlm_validation

[![docs](https://github.com/mgovorcin/disp2vlm_validation/actions/workflows/docs.yml/badge.svg)](https://mgovorcin.github.io/disp2vlm_validation/)
[![test](https://github.com/mgovorcin/disp2vlm_validation/actions/workflows/test.yaml/badge.svg)](https://github.com/mgovorcin/disp2vlm_validation/actions/workflows/test.yaml)

Independent GNSS validation of OPERA DISP-CAL and VLM products: the CalVal
VnV tool for the DISP-CAL v0.5 release. It compares calibrated displacement
with UNR daily stations and MIDAS rates, never with the gridded GNSS the
calibration is fitted to, and applies the release gate.

**Documentation: <https://mgovorcin.github.io/disp2vlm_validation/>**:
quickstart, tutorials, configuration and metrics reference, and the
validation record (decisions, trade studies, the v0.5 CalVal report).

## Try it

```bash
pip install "disp2vlm-validation @ git+https://github.com/mgovorcin/disp2vlm_validation"
disp2vlm-validate demo demo                               # a synthetic frame, offline
disp2vlm-validate run --config demo/configs/perfect.yaml  # PASS
disp2vlm-validate run --config demo/configs/half.yaml     # FAIL, with the reasons
```

## Commands

```bash
disp2vlm-validate gate                      # the release gate and benchmark frames
disp2vlm-validate run --config run.yaml     # one candidate on one frame
disp2vlm-validate vlm --config vlm.yaml     # a VLM run
disp2vlm-validate summary RUN_DIR... --out release_summary.html
```

A run writes `metrics.json`, `report.html` (verdict, DD sills with bootstrap
CIs, velocity vs MIDAS by station class, requirements traceability),
`stations.csv`, `figures/*.svg` and the calibrated velocity GeoTIFF. Runs are
cached by a content hash of the package version, config and input files;
`--no-cache` recomputes. Full frames on Linux hosts may need
`NUMPY_MADVISE_HUGEPAGE=0`.

## Development

```bash
pixi install -e dev
pixi run -e dev test     # pytest
pixi run -e dev lint     # pre-commit
pixi run -e dev docs     # mkdocs build --strict
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under Apache-2.0 (see
[LICENSE](LICENSE) and [NOTICE](NOTICE)); how AI tools were used is in
[AI_PROVENANCE.md](AI_PROVENANCE.md).
