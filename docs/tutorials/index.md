# Tutorials

Work through them in order. The first two run on the synthetic demo frame,
offline, in a minute; the others need real OPERA data.

| # | Tutorial | You learn | Data |
|---|---|---|---|
| 1 | [Validate a calibration](01-demo-frame.md) | what a run does, what the DD sill and velocity metrics say, where the outputs are | demo |
| 2 | [Compare with a baseline and apply the gate](02-baseline-and-gate.md) | candidate vs raw vs baseline, the gate rules, per-class targets, notes vs gating | demo |
| 3 | [Validate a real OPERA frame](03-real-frame.md) | staging DISP-S1, static layers and GNSS; writing `run.yaml`; deforming areas and events | OPERA DISP-S1 + a DISP-CAL candidate |
| 4 | [Validate VLM products](04-vlm.md) | pair residuals, station rates, the VLM gate | VLM products |
| 5 | [A release summary across frames](05-release-summary.md) | the benchmark frames, `summary`, reading a release verdict | several frame runs |
