# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""A small synthetic frame to try the validator on, offline (``demo`` command).

The frame is 40 x 60 pixels of 2 km (EPSG:32615) with a vertical look. Truth
is a 10 mm/yr east-west velocity gradient. Each DISP pair adds a random
per-date ramp, the long-wavelength error a calibration should remove, plus
0.5 mm of noise; the stack has two reference blocks (21 dates, 12 days apart).

Three DISP-CAL candidates differ only in how much of the ramp they remove:
``perfect`` (all of it), ``half`` and ``none``. Sixteen GNSS stations carry
the true velocity; their MIDAS rates and daily series are written to the
frozen GNSS cache, so nothing is downloaded.

`write_demo` also writes ready-to-run configs in ``<root>/configs``:
``perfect.yaml`` (no baseline), ``half.yaml`` and ``none.yaml`` (both against
``perfect``), and ``gate.yaml`` (a per-class target).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import rasterio
import yaml
from rasterio.transform import from_origin

__all__ = ["CANDIDATES", "DEMO_GRID", "demo_config", "make_demo_frame", "write_demo"]

NY, NX, PIX = 40, 60, 2000.0
CRS = "EPSG:32615"
X0, Y0 = 300_000.0, 3_400_000.0
REF_PIXEL = (20, 30)
#: Grid of the demo frame: rows, columns, posting (m), CRS, upper-left corner.
DEMO_GRID = {"ny": NY, "nx": NX, "pixel_m": PIX, "crs": CRS, "x0": X0, "y0": Y0}
#: Candidate name -> fraction of the per-date ramp its DISP-CAL removes.
CANDIDATES = {"perfect": 1.0, "half": 0.5, "none": 0.0}


def _name(kind: str, ref: datetime, sec: datetime) -> str:
    dates = f"{ref:%Y%m%dT%H%M%S}Z_{sec:%Y%m%dT%H%M%S}Z"
    return f"OPERA_{kind}_IW_F99999_VV_{dates}_v1.0_20261009T000000Z.nc"


def _h5(path: Path, **layers: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        for k, v in layers.items():
            f[k] = v


def _tif(path: Path, data: np.ndarray) -> None:
    data = np.atleast_3d(data.T).T if data.ndim == 2 else data
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=NY,
        width=NX,
        count=data.shape[0],
        dtype="float32",
        crs=CRS,
        transform=from_origin(X0, Y0, PIX, PIX),
    ) as ds:
        ds.write(data.astype(np.float32))


def make_demo_frame(root: Path | str, seed: int = 1) -> Path:
    """Write the synthetic frame under `root`.

    Layout: ``disp/`` (DISP pairs), ``perfect/``, ``half/``, ``none/`` (each a
    ``products/<ref>_<sec>/`` tree of DISP-CAL products, as cal-disp writes
    it), ``water_mask.tif``, ``los.tif`` and ``cache/`` (the GNSS cache).

    Returns
    -------
    Path
        `root`.

    """
    from pyproj import Transformer

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    _, xx = np.mgrid[0:NY, 0:NX]
    x_km = (xx - NX / 2) * PIX / 1000.0
    vel = (-5.0 + 10.0 * xx / NX) / 1000.0  # m/yr, a 10 mm/yr gradient
    t0 = datetime(2020, 1, 1)
    dates = [t0 + timedelta(days=12 * i) for i in range(21)]
    ramp = {d: rng.normal(0, 0.2, 1)[0] * x_km / 1000.0 for d in dates}  # 0.2 mm/km
    ramp[dates[0]] = np.zeros_like(x_km)
    blocks = [(dates[0], dates[1:11]), (dates[10], dates[11:])]
    for ref, secs in blocks:
        for sec in secs:
            yrs = (sec - ref).days / 365.25
            dramp = ramp[sec] - ramp[ref]
            disp = vel * yrs + dramp + rng.normal(0, 0.0005, (NY, NX))
            _h5(
                root / "disp" / _name("L3_DISP-S1", ref, sec),
                displacement=disp,
                temporal_coherence=np.full((NY, NX), 0.9, np.float32),
            )
            tag = f"{ref:%Y%m%d}_{sec:%Y%m%d}"
            for cand, frac in CANDIDATES.items():
                d = root / cand / "products" / tag
                _h5(
                    d / _name("L4_DISP-CAL-S1", ref, sec),
                    calibration=(frac * dramp).astype(np.float32),
                )
                (d / ".done").touch()
    _tif(root / "water_mask.tif", np.ones((NY, NX)))
    _tif(
        root / "los.tif",
        np.stack([np.zeros((NY, NX)), np.zeros((NY, NX)), np.ones((NY, NX))]),
    )

    # 16 stations on a grid, away from the edges
    rows, cols = np.meshgrid([6, 15, 24, 33], [8, 22, 37, 51], indexing="ij")
    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    midas, daily = {}, []
    for i, (r, c) in enumerate(zip(rows.ravel(), cols.ravel(), strict=True)):
        sid = f"G{i:03d}"
        lon, lat = to_ll.transform(X0 + (c + 0.5) * PIX, Y0 - (r + 0.5) * PIX)
        vu = vel[r, c] * 1000.0
        midas[sid] = {
            "lon": lon,
            "lat": lat,
            "ve_mm_yr": 0.0,
            "vn_mm_yr": 0.0,
            "vu_mm_yr": vu,
            "sigma_ve_mm_yr": 0.3,
            "sigma_vn_mm_yr": 0.3,
            "sigma_vu_mm_yr": 0.5,
            "first": dates[0].date(),
            "last": dates[-1].date(),
        }
        for day in dates:
            up = vu / 1000.0 * (day - t0).days / 365.25 + rng.normal(0, 0.001)
            daily.append(
                {"station": sid, "date": day, "east": 0.0, "north": 0.0, "up": up}
            )
    gnss = root / "cache"
    gnss.mkdir(exist_ok=True)
    pd.DataFrame.from_dict(midas, orient="index").rename_axis("station").to_csv(
        gnss / "gnss_midas_enu.csv"
    )
    pd.DataFrame(daily).to_csv(gnss / "gnss_enu_daily.csv.gz", index=False)
    return root


def demo_config(
    root: Path | str, candidate: str, baseline: str | None = None, **overrides
) -> dict:
    """Run config (as a dict) for one demo candidate.

    The demo stack is short (21 dates over 240 days) and small (120 km), so
    `min_common_dates` and `sill_min_km` are lowered from their full-frame
    defaults; `n_boot` is lowered to keep it quick. Paths are absolute, so the
    configs run from any directory.
    """
    root = Path(root).resolve()
    cfg = {
        "label": candidate,
        "frame": {
            "frame": "F99999",
            "disp_dir": str(root / "disp"),
            "water_mask": str(root / "water_mask.tif"),
            "los_file": str(root / "los.tif"),
            "cache_dir": str(root / "cache"),
            "ref_pixel": list(REF_PIXEL),
            "pixel_m": PIX,
        },
        "candidate_dir": str(root / candidate),
        "out_dir": str(root / "runs" / candidate),
        "baseline_dir": str(root / "runs" / baseline) if baseline else None,
        "min_common_dates": 15,
        "sill_min_km": 30.0,
        "n_boot": 200,
        "workers": 0,
    }
    cfg.update(overrides)
    return cfg


def write_demo(root: Path | str, seed: int = 1) -> list[Path]:
    """Write the demo frame and its run configs; return the config paths."""
    root = make_demo_frame(Path(root).resolve(), seed)
    cfg_dir = root / "configs"
    cfg_dir.mkdir(exist_ok=True)
    gate = cfg_dir / "gate.yaml"
    gate.write_text(
        "# A per-class target for the demo: the stable class must stay within\n"
        "# 1 mm/yr of GNSS. Classes and their rules: docs/guide/metrics.md.\n"
        "per_class_targets:\n"
        "  stable: {max_abs_bias_mm_yr: 1.0, max_rmse_mm_yr: 1.0}\n"
    )
    paths = []
    for cand, base in (("perfect", None), ("half", "perfect"), ("none", "perfect")):
        cfg = demo_config(root, cand, base, gate=str(gate))
        path = cfg_dir / f"{cand}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        paths.append(path)
    return paths
