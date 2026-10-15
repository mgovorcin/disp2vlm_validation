# Validation record

How the v0.5 release gate was set, and the evidence behind each choice.

| Record | What it holds |
|---|---|
| [Scope](../scope.md) | What the tool uses and never uses, metrics, modes, benchmark frames. |
| [Decisions](../decisions/0001-median-bias-and-sea-coast.md) | Changes to what passes, each with its reason. |
| [Trade studies](studies.md) | The analyses that set parameters and checked assumptions. |
| [Baselines](../baselines.md) | Gamma and v0.5 numbers on the benchmark frames. |
| [v0.5 CalVal report](../vnv/v0.5-calval-report.md) | The release verdict, requirements traceability, findings, sign-off. |

## Decisions

| # | Decision | Status |
|---|---|---|
| [0001](../decisions/0001-median-bias-and-sea-coast.md) | The gate's bias is the median; "coastal" means within 10 km of the sea (≥ 500 km² of water). | accepted 2026-10-09 |
| [0002](../decisions/0002-velocity-gate-outside-deforming-areas.md) | The velocity rules score stations outside deforming areas and event footprints; a frame's benchmark condition gates it. | accepted 2026-10-10 (amended 2026-10-13) |
| [0003](../decisions/0003-vlm-gate.md) | VLM gate on per-station vertical rates: median and NMAD; RMSE reported. | accepted 2026-10-13 |
