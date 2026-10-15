# Benchmark run configs

The `run.yaml` and `gate.yaml` files of the benchmark runs in
[docs/baselines.md](../../docs/baselines.md) and the trade studies (`tsb1/`,
`tsu1/`). They are the record of what was run. Paths are environment
variables, expanded when a config is read:

| Variable | Holds |
|---|---|
| `E2E_ROOT` | the end-to-end work area: per-frame inputs (`frames/<frame>/`), GNSS caches (`cache_<frame>/`), candidate products (`runs/`) and validation outputs |
| `DISP_DATA` | the staged DISP-S1 stacks of the first four frames |
| `SRC` | the folder holding the `cal-disp` and `disp2vlm_validation` checkouts |
| `TRADE_STUDIES` | the trade-study scripts (`e2e_validation/calibrate_stack.py`) |

```bash
export E2E_ROOT=/data/cal_disp_e2e DISP_DATA=/data/opera_vlm SRC=$HOME/src TRADE_STUDIES=$HOME/trade_studies
disp2vlm-validate run --config configs/benchmark/F08886_v05.yaml
```

A config that uses an unset variable stops with the variable's name. To stage
a frame of your own, follow the
[real-frame tutorial](https://mgovorcin.github.io/disp2vlm_validation/tutorials/03-real-frame/).
