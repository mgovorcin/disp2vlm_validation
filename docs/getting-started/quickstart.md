# Quickstart

Validate three calibrations of a synthetic frame in about a minute, offline.

## 1. Write the demo frame

```bash
disp2vlm-validate demo demo
```

```text
wrote demo/configs/perfect.yaml
wrote demo/configs/half.yaml
wrote demo/configs/none.yaml
next: disp2vlm-validate run --config demo/configs/perfect.yaml
```

The frame is 40 × 60 pixels of 2 km with a 10 mm/yr velocity gradient. Every
DISP pair carries a random ramp, the long-wavelength error a calibration
should remove. The three candidate DISP-CAL products remove all of it
(`perfect`), half of it (`half`) or none (`none`). Sixteen GNSS stations
measure the true velocity, and their data is already in the frame's GNSS
cache.

## 2. Validate the candidates

`perfect` first: the other two use it as their baseline.

```bash
disp2vlm-validate run --config demo/configs/perfect.yaml
disp2vlm-validate run --config demo/configs/half.yaml
disp2vlm-validate run --config demo/configs/none.yaml
```

```text
F99999 perfect: PASS
F99999 half: FAIL
  - DD sill up +265.8% [95% CI +152.2, +628.8] vs baseline (limit 5%)
  - velocity RMSE up +1.90 mm/yr vs baseline (limit 0.2)
  - velocity |median bias| up +0.37 mm/yr vs baseline (limit 0.2)
F99999 none: FAIL
  - DD sill not reduced by calibration (8.1 vs raw 8.1 mm²)
  - DD sill up +781.4% [95% CI +577.5, +2390.2] vs baseline (limit 5%)
  - velocity RMSE up +4.78 mm/yr vs baseline (limit 0.2)
  - velocity |median bias| up +0.46 mm/yr vs baseline (limit 0.2)
```

## 3. Look at the results

Each run writes a folder under `demo/runs/<candidate>/`. Open
`demo/runs/perfect/report.html` in a browser: verdict, DD sills with
bootstrap intervals, velocity against MIDAS by station class, and the
requirements traceability. [Outputs](../guide/outputs.md) lists every file.

## 4. Summarise

```bash
disp2vlm-validate summary demo/runs/perfect demo/runs/half demo/runs/none --out demo/summary.html
```

## Next

The [tutorials](../tutorials/index.md) explain what each number means, how the
gate decides, and how to run a real OPERA frame.
