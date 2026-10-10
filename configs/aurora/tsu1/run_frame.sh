#!/bin/bash
# TS-U1 (T42.4): v0.5 + unwrap for one frame, then validate against v0.5
set -uo pipefail
export NUMPY_MADVISE_HUGEPAGE=0 TMPDIR=/u/aurora-r0/govorcin/tmp
F=$1; DISP=$2; GOLD=$3; RUN=/mnt/aurora-z0/govorcin/cal_disp_e2e/runs/$F-v05-unwrap; mkdir -p $RUN
git -C /u/aurora-r0/govorcin/00_tools/src/cal-disp rev-parse HEAD > $RUN/cal_disp_sha.txt
/u/aurora-r0/govorcin/00_tools/src/cal-disp/.pixi/envs/dev/bin/python "/u/aurora-r0/govorcin/01_OPERA/VLM/DISP_CAL/trade studies/e2e_validation/calibrate_stack.py" --run-dir $RUN --disp-dir $DISP --golden-dir $GOLD --algorithm-parameters /mnt/aurora-z0/govorcin/cal_disp_e2e/tsu1/configs/algorithm_parameters_v05_unwrap.yaml --cal-disp-bin /u/aurora-r0/govorcin/00_tools/src/cal-disp/.pixi/envs/dev/bin/cal-disp --jobs 12 --n-workers 4 > $RUN/calibrate.log 2>&1
echo "$F calibrate exit $?"
/u/aurora-r0/govorcin/00_tools/src/disp2vlm_validation/.pixi/envs/dev/bin/disp2vlm-validate run --config /mnt/aurora-z0/govorcin/cal_disp_e2e/tsu1/configs/${F}_v05_unwrap.yaml > /mnt/aurora-z0/govorcin/cal_disp_e2e/tsu1/logs/${F}.log 2>&1
echo "$F validate exit $?"
