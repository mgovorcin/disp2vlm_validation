#!/bin/bash
# TS-B1 sweep for one frame: p = 4, 16 (p = 8 is the T38 v0.5 run)
set -uo pipefail
export NUMPY_MADVISE_HUGEPAGE=0
: "${E2E_ROOT:?}" "${DISP_DATA:?}" "${SRC:?}" "${TRADE_STUDIES:?}"
F=$1; DISP=$2; GOLD=$3
for p in 4 16; do
  RUN=$E2E_ROOT/runs/$F-tsb1-p$p; mkdir -p $RUN
  $SRC/cal-disp/.pixi/envs/dev/bin/python "$TRADE_STUDIES/e2e_validation/calibrate_stack.py" --run-dir $RUN --disp-dir $DISP --golden-dir $GOLD --algorithm-parameters $E2E_ROOT/tsb1/configs/algorithm_parameters_p$p.yaml --cal-disp-bin $SRC/cal-disp/.pixi/envs/dev/bin/cal-disp --jobs 12 --n-workers 4 > $RUN/calibrate.log 2>&1
  echo "$F p$p calibrate exit $?"
  $SRC/disp2vlm_validation/.pixi/envs/dev/bin/disp2vlm-validate run --config $E2E_ROOT/tsb1/configs/${F}_p$p.yaml > $E2E_ROOT/tsb1/logs/${F}_p$p.log 2>&1
  echo "$F p$p validate exit $?"
done
echo done
