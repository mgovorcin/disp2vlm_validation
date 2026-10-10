# CLAUDE.md — disp2vlm_validation

## What this repo is

The CalVal VnV tool for DISP-CAL (and later VLM): it scores calibrated DISP
against independent GNSS (UNR daily stations, MIDAS), applies the release
gate of the Venti PRD §2.7 and writes per-frame reports and a release
summary. It does not make products (cal-disp / Venti do) and is never part of
the operational image.

## Architecture

`src/disp2vlm_validation/`: `requirements.py` (the gate and benchmark frames
as data, the single source of the numbers), `stack.py` (DISP and DISP-CAL
stacks, streaming velocity fit), `gnss.py` (UNR + MIDAS, frozen per frame;
station sampler, held-out split), `metrics.py` (DD sill with paired bootstrap,
velocity stats), `classes.py` (station classes, per-class metrics, σ realism),
`gate.py` (`gate.yaml`, `evaluate`, golden-epoch check), `pipeline.py` (one
frame run, `RunConfig`, caches), `report.py` + `templates/` (HTML, SVG,
traceability from `traceability.yaml`), `cli.py` (`gate`, `run`, `summary`).
`studies/` holds one-off analyses (e.g. `bias_by_block.py`), each with a test.
Baselines and the T38 comparison: `docs/baselines.md`.

## Invariants (do not break without a decision record)

- **Only independent GNSS.** Never read the UNR gridded field or anything
  derived from it (the calibration's own input). `GATE.independent_gnss_only`
  is not a constructor argument on purpose. The one exception is
  `studies/ts_g1.py` (TS-G1), whose subject *is* the grid: it reads it to
  compare it with stations and never feeds the gate or a report.
- Gate numbers live only in `requirements.py`; a change there changes what
  passes and needs a decision record in `docs/decisions/`.
- No product writing; no runtime dependency on cal-disp. Venti is an optional
  extra used only to reproduce a candidate calibration.

## Commands

```bash
export RATTLER_CACHE_DIR=/u/aurora-r0/govorcin/.cache/rattler UV_CACHE_DIR=/u/aurora-r0/govorcin/.cache/uv
export TMPDIR=/u/aurora-r0/govorcin/tmp
pixi install -e dev
pixi run -e dev test          # pytest
pixi run -e dev lint          # pre-commit run -a
pixi run -e dev docs          # mkdocs build --strict
pixi run -e dev disp2vlm-validate gate
```

Full-frame stacks on aurora need `NUMPY_MADVISE_HUGEPAGE=0`.

## Golden / value-change policy

No golden dataset. A change that moves a metric on the four existing frames
(F08882, F08886, F16940, F08622) is reported in the PR body with before and
after numbers from the archived baseline runs.

## Conventions

- Branches: never commit on `main` after the scaffold; `feature/<topic>`;
  PRs to `mgovorcin/disp2vlm_validation` `main`. See `CONTRIBUTING.md`.
- Every addition ships with its test in the same commit (`unit-tests` skill).
- Style: ruff + black + mypy via pre-commit; NumPyDoc docstrings; SPDX header
  (`Apache-2.0`, Caltech copyright) on every `.py` file.
- Private until the licensing review clears.
