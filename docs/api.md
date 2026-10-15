# API

The command line wraps these modules; everything can be called from Python.

## Running

::: disp2vlm_validation.pipeline
    options:
      members: [RunConfig, FrameInputs, GoldenCheck, load_run_config, run_validation]

::: disp2vlm_validation.vlm
    options:
      members: [VlmRunConfig, run_vlm, evaluate_vlm]

::: disp2vlm_validation.demo

## Gate and requirements

::: disp2vlm_validation.requirements

::: disp2vlm_validation.gate
    options:
      members: [GateConfig, ClassTarget, load_gate, evaluate, golden_epoch_check]

## Metrics

::: disp2vlm_validation.metrics

::: disp2vlm_validation.classes

## Data

::: disp2vlm_validation.stack

::: disp2vlm_validation.gnss

## Reports and CLI

::: disp2vlm_validation.report
    options:
      members: [write_outputs, write_summary, load_traceability]

::: disp2vlm_validation.cli
