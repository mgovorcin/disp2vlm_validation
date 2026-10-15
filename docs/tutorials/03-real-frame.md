# 3. Validate a real OPERA frame

The same run as on the demo, on an OPERA DISP-S1 frame and a DISP-CAL
candidate made with [cal-disp](https://github.com/mgovorcin/cal-disp). The
example is frame 8886 (Oklahoma City, stable inland ground). Expect tens of
GB of DISP-S1 data and an hour or two for the first run.

## What a run needs

| Input | Where it comes from |
|---|---|
| DISP-S1 products of the frame | ASF (`cal-disp download disp-s1`) |
| DISP-CAL products of the candidate, one per DISP pair | cal-disp runs over the stack |
| Line-of-sight unit vectors | the frame's DISP-S1-STATIC `*_line_of_sight_enu.tif` |
| Water mask, GeoTIFF on the DISP grid, 1 = land | the `water_mask` layer of a DISP product |
| GNSS | fetched once from UNR into `cache_dir`, then frozen |
| Deforming areas and events (optional) | Venti's area and event databases (GeoJSON) |

Earthdata Login credentials (`~/.netrc` for `urs.earthdata.nasa.gov`) are
needed for the ASF downloads.

## 1. DISP-S1 products

```bash
cal-disp download disp-s1 --frame-id 8886 -o F08886/disp_s1 -n 8
```

The validator reads every `OPERA_L3_DISP-*.nc` in the folder, pairs them with
the candidate by dates, and chains the reference blocks. Use the full stack
(several years): velocities over less than two years of GNSS are not
compared.

## 2. Static layers

The DISP-S1-STATIC product of the frame has the line-of-sight vectors. Find
its files through NASA CMR, then download them with your Earthdata login:

```bash
curl -s "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=OPERA_L3_DISP-S1-STATIC_V1&readable_granule_name[]=*_F08886_*&options[readable_granule_name][pattern]=true" \
  | python -c "import json,sys; [print(l['href']) for e in json.load(sys.stdin)['feed']['entry'] for l in e['links'] if l['href'].endswith('_line_of_sight_enu.tif')]"
```

## 3. Water mask and reference pixel

Both come from the last DISP product of the stack:

```python
from pathlib import Path

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin

last = sorted(Path("F08886/disp_s1").glob("OPERA_L3_DISP-S1_*.nc"))[-1]
with h5py.File(last) as h:
    land = np.squeeze(h["water_mask"][()]).astype("uint8")
    rp = h["corrections/reference_point"].attrs
    x, y = h["x"][()], h["y"][()]
    crs = h["spatial_ref"].attrs["crs_wkt"]
dx, dy = float(x[1] - x[0]), float(y[0] - y[1])
with rasterio.open(
    "F08886/water_mask.tif", "w", driver="GTiff", dtype="uint8", count=1,
    height=land.shape[0], width=land.shape[1], crs=crs,
    transform=from_origin(x[0] - dx / 2, y[0] + dy / 2, dx, dy), compress="deflate",
) as ds:
    ds.write(land, 1)
print("ref_pixel:", [int(rp["rows"][0]), int(rp["cols"][0])])
```

`ref_pixel` references the raw velocity. Leave it out of the config and the
validator takes the last product's reference point itself.

## 4. The candidate

Run cal-disp over every pair of the stack and keep its output layout,
`products/<ref>_<sec>/OPERA_L4_DISP-CAL-*.nc`. A flat folder of products
works too. When `.done` markers are present (cal-disp writes one when a pair
finishes), a product without one is ignored as interrupted. A DISP pair
without a DISP-CAL product stops the run, unless `allow_partial: true`.

## 5. `run.yaml`

```yaml
label: v05
frame:
  frame: F08886
  disp_dir: F08886/disp_s1
  water_mask: F08886/water_mask.tif
  los_file: F08886/static/OPERA_L3_DISP-S1-STATIC_F08886_20160705_S1A_v1.0_line_of_sight_enu.tif
  cache_dir: F08886/cache           # GNSS is fetched here on the first run
  ref_pixel: [2459, 5321]
  exclude_stations: []              # e.g. stations with known local problems
  defo_geojson: null                # Venti deforming-area database (optional)
  event_geojson: null               # Venti event database (optional)
candidate_dir: runs/F08886-v05/products
baseline_dir: validation/F08886/gamma    # the released algorithm's validation run
out_dir: validation/F08886/v05
workers: 6
```

Every field: [Configuration](../guide/configuration.md#runyaml).

## 6. Run

```bash
export NUMPY_MADVISE_HUGEPAGE=0
disp2vlm-validate run --config run.yaml
```

The first run fetches GNSS for the frame's bounding box from UNR (MIDAS rates
and daily positions; stations with less than two years of data are dropped)
and writes it to `cache_dir`. Later runs, and other candidates on the same
frame, reuse it unchanged: every candidate is scored against the same
stations. The raw velocity and mean coherence are cached there too, per
stack.

## Deforming areas and events

On a frame with fast local deformation (a subsidence bowl, a volcano) or an
earthquake, pass Venti's databases:

```yaml
  defo_geojson: venti/data/defo_area_db_v1.geojson
  event_geojson: venti/data/event_db_v1.geojson
```

Stations inside an area become class `defo_area`, and stations inside an
event footprint become `near_event`. Both are left
out of the velocity rules and reported per class (decision 0002); a frame's
`gate.yaml` can set targets for them ([tutorial 2](02-baseline-and-gate.md)).

## Holding stations out

`held_out_fraction: 0.3` sets aside 30% of the stations, chosen by a hash of
the station id, so the split is the same on every run and machine. They are
not used in the validation and are listed in `metrics.json` as
`held_out_stations`. They are the stations a study may use to fit
parameters (trade study TS-G1), so a fitted value is never validated on the
stations it was fitted to. `exclude_stations` drops stations from both sets.

Next: [validate VLM products](04-vlm.md).
