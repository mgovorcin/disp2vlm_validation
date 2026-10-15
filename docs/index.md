# disp2vlm_validation

Independent GNSS validation of OPERA **DISP-CAL** (calibrated surface
displacement) and **VLM** (vertical land motion) products.

It compares the calibrated InSAR with UNR daily GNSS stations and their MIDAS
rates. It never uses the gridded GNSS field the calibration is fitted to, so
the result measures the product, not the fit. It then applies the CalVal
release gate and writes a report for each frame, plus a summary across frames.
It is the CalVal verification-and-validation (VnV) tool for the DISP-CAL v0.5
release.

<div class="grid cards" markdown>

- **Try it in five minutes.** Install, write a synthetic frame and validate it,
  offline. [Quickstart](getting-started/quickstart.md)
- **Learn the workflow.** Five tutorials, from the demo frame to a real OPERA
  frame and a release summary. [Tutorials](tutorials/index.md)
- **Look something up.** Configuration fields, metrics and gate rules, outputs,
  CLI. [Guide](guide/configuration.md)
- **Read the validation record.** The release gate's decisions, trade studies,
  baselines and the v0.5 CalVal report. [Record](record/index.md)

</div>

## What it answers

| Question | How |
|---|---|
| Does the calibration help at all? | The double-difference (DD) sill of InSAR minus GNSS must drop from raw DISP to calibrated. |
| Is a new algorithm at least as good as the released one? | The sill must not rise by more than 5% (with a significant bootstrap CI); velocity RMSE and \|median bias\| against MIDAS must not rise by more than 0.2 mm/yr. |
| Is it good enough where it matters? | Per-class targets (stable, subsiding, coastal, inside deforming areas, near events), set per frame. |
| Are the uncertainties honest? | σ realism: z-scores of the residuals against the product's σ (reported). |
| Is VLM within 1–2 mm/yr of GNSS? | Station vertical rates against GNSS Up; gate on median and NMAD. |

## In one screen

```bash
pip install "disp2vlm-validation @ git+https://github.com/mgovorcin/disp2vlm_validation"
disp2vlm-validate demo demo                       # a synthetic frame + configs
disp2vlm-validate run --config demo/configs/perfect.yaml
disp2vlm-validate run --config demo/configs/half.yaml
disp2vlm-validate summary demo/runs/perfect demo/runs/half --out summary.html
```

```text
F99999 perfect: PASS
F99999 half: FAIL
  - DD sill up +265.8% [95% CI +152.2, +628.8] vs baseline (limit 5%)
  - velocity RMSE up +1.90 mm/yr vs baseline (limit 0.2)
  - velocity |median bias| up +0.37 mm/yr vs baseline (limit 0.2)
```

## Scope

It reads products; it does not make them (that is
[cal-disp](https://github.com/mgovorcin/cal-disp) and
[Venti](https://github.com/mgovorcin/venti-dev)), and it is never part of the
operational image. See [Scope](scope.md).
