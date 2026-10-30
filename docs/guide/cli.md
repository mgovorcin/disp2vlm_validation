# Command line

```text
disp2vlm-validate {gate,run,vlm,summary,demo}
```

| Command | Does |
|---|---|
| `gate [--format text\|json]` | Print the release gate and the benchmark frames. |
| `run --config run.yaml [--no-cache] [--verbose]` | Validate one candidate on one frame. |
| `vlm --config vlm.yaml [--verbose]` | Validate a VLM run. |
| `summary RUN_DIR... [--out release_summary.html] [--title STR]` | One page across runs. |
| `demo OUT_DIR [--seed INT]` | Write the synthetic demo frame and its configs. |

`run` prints the verdict and the reasons, and exits normally either way: read
the verdict from the output or from `metrics.json`.

## `gate`

```text
$ disp2vlm-validate gate
disp2vlm-validation: CalVal release gate
  sill_must_drop                 True
  sill_rise_max_frac             0.05
  sill_min_pair_km               50.0
  velocity_rmse_rise_max_mm_yr   0.2
  velocity_bias_rise_max_mm_yr   0.2
  bias_statistic                 median
  target_abs_bias_mm_yr          1.0
  bootstrap_ci                   0.95
  velocity_excluded_classes      ('defo_area', 'near_event')
  velocity_min_overlap_years     3.0
  independent_gnss_only          True
benchmark frames:
  ...
```

## Python

Everything the CLI does is a function call:

```python
from disp2vlm_validation.pipeline import load_run_config, run_validation

metrics = run_validation(load_run_config("run.yaml"))
print(metrics["verdict"], metrics["verdict_reasons"])
```

See the [API reference](../api.md).
