#!/bin/bash
export NUMPY_MADVISE_HUGEPAGE=0 PYTHONPATH=/u/aurora-r0/govorcin/00_tools/src/disp2vlm_validation/src TMPDIR=/u/aurora-r0/govorcin/tmp
run() { # frame los gnssdir dispdir
  /u/aurora-r0/govorcin/00_tools/src/cal-disp/.pixi/envs/dev/bin/python /u/aurora-r0/govorcin/00_tools/src/disp2vlm_validation/studies/ts_g1.py --frame $1 --stations /mnt/aurora-z0/govorcin/cal_disp_e2e/t38/runs/$1/v05-loclin/stations.csv --midas /mnt/aurora-z0/govorcin/cal_disp_e2e/cache_$1/gnss_midas_enu.csv --los $2 --grid-lookup $(ls $3/grid_latlon_lookup*.txt) --station-dir $3 --out /mnt/aurora-z0/govorcin/cal_disp_e2e/ts_g1/$1 --daily /mnt/aurora-z0/govorcin/cal_disp_e2e/cache_$1/gnss_enu_daily.csv.gz --disp-dir $4 2>&1 | grep -v RBF > /mnt/aurora-z0/govorcin/cal_disp_e2e/ts_g1/$1.log
}
run F08882 /u/aurora-r0/govorcin/00_tools/src/cal-disp/test_golden/input_data/static_input/OPERA_L3_DISP-S1-STATIC_F08882_20140403_S1A_v1.0_line_of_sight_enu.tif /u/aurora-r0/govorcin/00_tools/src/cal-disp/test_golden/input_data/gnss /mnt/aurora-z0/cabrera/opera_vlm/data/houston_08882/frame_08882/disp_s1 &
run F08886 $(ls /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F08886/input_data/static_input/*line_of_sight_enu.tif) /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F08886/input_data/gnss /mnt/aurora-z0/cabrera/opera_vlm/data/okc_08886/frame_8886/disp_s1 &
run F16940 $(ls /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F16940/input_data/static_input/*line_of_sight_enu.tif) /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F16940/input_data/gnss /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F16940/disp_s1 &
run F08622 $(ls /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F08622/input_data/static_input/*line_of_sight_enu.tif) /mnt/aurora-z0/govorcin/cal_disp_e2e/frames/F08622/input_data/gnss /mnt/aurora-z0/cabrera/opera_vlm/data/nyc_08622/frame_08622/disp_s1 &
wait
