# disp2vlm_validation

Independent GNSS validation of OPERA DISP-CAL and VLM products: the CalVal
VnV tool for the DISP-CAL v0.5 release. It compares calibrated displacement
with UNR daily stations and MIDAS rates, never with the gridded GNSS the
calibration is fitted to, and applies the release gate.

**Status:** skeleton (plan T11). The release gate and benchmark frames are
defined; the metrics land with T21–T25. See [scope](scope.md).

```bash
pixi install -e dev
pixi run -e dev disp2vlm-validate gate        # the release gate and benchmark frames
pixi run -e dev test
```

**Private** until the licensing template (Apache-2.0 + NOTICE +
AI_PROVENANCE) is reviewed by JPL Patent/IP counsel and OTT.
