#!/bin/bash
: "${E2E_ROOT:?}" "${SRC:?}"
export NUMPY_MADVISE_HUGEPAGE=0 PYTHONPATH=$SRC/disp2vlm_validation/src
run() { # frame los gnssdir dispdir
  $SRC/cal-disp/.pixi/envs/dev/bin/python $SRC/disp2vlm_validation/studies/ts_g1.py --frame $1 --stations $E2E_ROOT/t38/runs/$1/v05-loclin/stations.csv --midas $E2E_ROOT/cache_$1/gnss_midas_enu.csv --los $2 --grid-lookup $(ls $3/grid_latlon_lookup*.txt) --station-dir $3 --out $E2E_ROOT/ts_g1/$1 --daily $E2E_ROOT/cache_$1/gnss_enu_daily.csv.gz --disp-dir $4 2>&1 | grep -v RBF > $E2E_ROOT/ts_g1/$1.log
}
run F08882 $SRC/cal-disp/test_golden/input_data/static_input/OPERA_L3_DISP-S1-STATIC_F08882_20140403_S1A_v1.0_line_of_sight_enu.tif $SRC/cal-disp/test_golden/input_data/gnss $DISP_DATA/houston_08882/frame_08882/disp_s1 &
run F08886 $(ls $E2E_ROOT/frames/F08886/input_data/static_input/*line_of_sight_enu.tif) $E2E_ROOT/frames/F08886/input_data/gnss $DISP_DATA/okc_08886/frame_8886/disp_s1 &
run F16940 $(ls $E2E_ROOT/frames/F16940/input_data/static_input/*line_of_sight_enu.tif) $E2E_ROOT/frames/F16940/input_data/gnss $E2E_ROOT/frames/F16940/disp_s1 &
run F08622 $(ls $E2E_ROOT/frames/F08622/input_data/static_input/*line_of_sight_enu.tif) $E2E_ROOT/frames/F08622/input_data/gnss $DISP_DATA/nyc_08622/frame_08622/disp_s1 &
wait
