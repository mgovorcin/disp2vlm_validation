#!/bin/bash
# TS-B1 sweep for one frame: p = 4, 16 (p = 8 is the T38 v0.5 run)
set -uo pipefail
export NUMPY_MADVISE_HUGEPAGE=0 TMPDIR=/u/aurora-r0/govorcin/tmp
F=$1; DISP=$2; GOLD=$3
for p in 4 16; do
  RUN=/mnt/aurora-z0/govorcin/cal_disp_e2e/runs/$F-tsb1-p$p; mkdir -p $RUN
  /u/aurora-r0/govorcin/00_tools/src/cal-disp/.pixi/envs/dev/bin/python "/u/aurora-r0/govorcin/01_OPERA/VLM/DISP_CAL/trade studies/e2e_validation/calibrate_stack.py" --run-dir $RUN --disp-dir $DISP --golden-dir $GOLD --algorithm-parameters /mnt/aurora-z0/govorcin/cal_disp_e2e/tsb1/configs/algorithm_parameters_p$p.yaml --cal-disp-bin /u/aurora-r0/govorcin/00_tools/src/cal-disp/.pixi/envs/dev/bin/cal-disp --jobs 12 --n-workers 4 > $RUN/calibrate.log 2>&1
  echo "$F p$p calibrate exit $?"
  /u/aurora-r0/govorcin/00_tools/src/disp2vlm_validation/.pixi/envs/dev/bin/disp2vlm-validate run --config /mnt/aurora-z0/govorcin/cal_disp_e2e/tsb1/configs/${F}_p$p.yaml > /mnt/aurora-z0/govorcin/cal_disp_e2e/tsb1/logs/${F}_p$p.log 2>&1
  echo "$F p$p validate exit $?"
done
echo done
