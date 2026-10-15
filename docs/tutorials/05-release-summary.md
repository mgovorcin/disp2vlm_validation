# 5. A release summary across frames

A release is judged on the benchmark frames, each chosen for one way a
calibration can go wrong.

```bash
disp2vlm-validate gate
```

| # | Category | Frame | Benchmark condition |
|---|---|---|---|
| 1 | Coastal subsidence + islands | F08882 Houston | subsiding stations |
| 2 | Stable inland | F08886 Oklahoma City | stable stations: \|bias\| < 1 mm/yr |
| 3 | High relief + islands | F16940 Los Angeles | sill drops; tropo mode does not make it worse |
| 4 | Northeast / GIA | F08622 New York | vertical pattern vs GNSS |
| 5 | Fast basin | F36542 Central Valley | continuous surface; stations outside unaffected; bowl kept |
| 6 | Coseismic event | F16941 Ridgecrest | no coseismic step leaks into the calibration |
| 7 | Sparse GNSS | F07081 Montana | realistic σ, no artifacts |
| 8 | Non-NA plate | F23211 Hawaii, F35991 Puerto Rico | plate; Kīlauea as a deforming area |

## Run every frame, then summarise

Run each frame as in [tutorial 3](03-real-frame.md), with its own
`gate.yaml` for the benchmark condition and the released algorithm as
baseline. Then:

```bash
disp2vlm-validate summary validation/*/v05 --out release_summary.html --title "cal-disp v0.5"
```

```text
F08882   v05                      PASS
F08886   v05                      PASS
...
wrote release_summary.html
```

`release_summary.html` has one row per frame (verdict, DD sill against raw and
baseline with intervals, velocity statistics) and the requirements
traceability across frames.

## Reading a release verdict

- A frame passes only if every gate rule and its benchmark condition hold.
- Notes are not failures, but they belong in the VnV report: a stable median
  bias above 1 mm/yr, or a missed reported target.
- When a frame fails for a known, local reason, the release can still go out
  with a documented waiver. That is a decision for the CalVal review, not for
  the tool.

The v0.5 release went through exactly this: see the
[v0.5 CalVal report](../vnv/v0.5-calval-report.md) and the
[baselines](../baselines.md).
