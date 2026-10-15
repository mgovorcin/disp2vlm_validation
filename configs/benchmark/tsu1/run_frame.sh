#!/bin/bash
# TS-U1 (T42.4): v0.5 + unwrap for one frame, then validate against v0.5
set -uo pipefail
export NUMPY_MADVISE_HUGEPAGE=0
: "${E2E_ROOT:?}" "${DISP_DATA:?}" "${SRC:?}" "${TRADE_STUDIES:?}"
F=$1; DISP=$2; GOLD=$3; RUN=$E2E_ROOT/runs/$F-v05-unwrap; mkdir -p $RUN
git -C $SRC/cal-disp rev-parse HEAD > $RUN/cal_disp_sha.txt
$SRC/cal-disp/.pixi/envs/dev/bin/python "$TRADE_STUDIES/e2e_validation/calibrate_stack.py" --run-dir $RUN --disp-dir $DISP --golden-dir $GOLD --algorithm-parameters $E2E_ROOT/tsu1/configs/algorithm_parameters_v05_unwrap.yaml --cal-disp-bin $SRC/cal-disp/.pixi/envs/dev/bin/cal-disp --jobs 12 --n-workers 4 > $RUN/calibrate.log 2>&1
echo "$F calibrate exit $?"
$SRC/disp2vlm_validation/.pixi/envs/dev/bin/disp2vlm-validate run --config $E2E_ROOT/tsu1/configs/${F}_v05_unwrap.yaml > $E2E_ROOT/tsu1/logs/${F}.log 2>&1
echo "$F validate exit $?"
