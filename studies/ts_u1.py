# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""TS-U1 phase 1: whole-cycle unwrap correction scored at GNSS stations.

Venti plan T42, PRD §7.2. Truth comes from island (or cut-off) stations with
trusted GNSS, per DISP pair, without touching the estimator's internals:

- **truth**: the raw DISP displacement difference island station - nearest
  mainland station, minus the same GNSS difference, in cycles (lambda/2).
  Real motion cancels through GNSS, so a whole-cycle misfit is an unwrapping
  error; the label is ``round(m)`` when ``|m - round(m)| < label_tolerance``,
  otherwise ambiguous (troposphere, noise);
- **applied**: the change, in cycles, of the calibrated displacement at the
  station between the run with unwrap correction and the run without it
  (everything else is identical, so the shift dominates);
- **decoys**: mainland stations, which must never be shifted.

Precision = correct shifts / all shifts at labelled island cases; recall =
correct shifts / labelled errors; the PRD bar is precision >= 0.99 and
recall >= 0.8 on >= 100 cases.

Station series are the ``disp2vlm-validate`` outputs (7 x 7 pixel medians,
chained); within a reference block the difference between a secondary date
and the block's reference date is the pair's own displacement.

    python studies/ts_u1.py --frame F08882 --stations RUN/stations.csv \
        --raw CACHE/stack_*/raw_station_series_mm.csv \
        --cal-off V05_RUN/station_series_mm.csv \
        --cal-on UNWRAP_RUN/station_series_mm.csv \
        --daily CACHE/gnss_enu_daily.csv.gz --disp-dir DISP \
        --water-mask WM.tif --out OUT
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from disp2vlm_validation.stack import list_epochs

CYCLE_MM = 0.055465763 / 2 * 1000.0  # Sentinel-1 C band, lambda / 2 of LOS


def pair_values(series: pd.DataFrame, pairs: list[tuple[pd.Timestamp, pd.Timestamp]]):
    """Per-pair displacement: sec minus the block's reference date."""
    idx = series.index
    rows = {}
    for ref, sec in pairs:
        if ref in idx and sec in idx:
            rows[(ref, sec)] = series.loc[sec] - series.loc[ref]
    out = pd.DataFrame(rows).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["ref", "sec"])
    return out


def gnss_pair_values(
    daily_los: pd.DataFrame,
    pairs: list[tuple[pd.Timestamp, pd.Timestamp]],
    half_window_days: int = 3,
) -> pd.DataFrame:
    """GNSS LOS displacement per pair (+-window medians at both dates)."""
    d = daily_los.sort_index()
    win = pd.Timedelta(days=half_window_days)
    rows = {
        (r, s): d.loc[s - win : s + win].median() - d.loc[r - win : r + win].median()
        for r, s in pairs
    }
    out = pd.DataFrame(rows).T
    out.index = pd.MultiIndex.from_tuples(out.index, names=["ref", "sec"])
    return out


def nearest_partner(
    stations: pd.DataFrame, island: list[str], mainland: list[str], max_km: float
) -> dict[str, str]:
    """Nearest mainland station to each island station within `max_km`."""
    lat0 = np.radians(stations["lat"].mean())
    xy = np.c_[stations["lon"] * 111.32 * np.cos(lat0), stations["lat"] * 110.57]
    pos = dict(zip(stations.index, xy, strict=True))
    out = {}
    for s in island:
        d = {m: float(np.hypot(*(pos[s] - pos[m]))) for m in mainland}
        if d:
            m = min(d, key=lambda k: d[k])
            if d[m] <= max_km:
                out[s] = m
    return out


def score(
    raw: pd.DataFrame,
    gnss: pd.DataFrame,
    cal_off: pd.DataFrame,
    cal_on: pd.DataFrame,
    *,
    partners: dict[str, str],
    mainland: list[str],
    label_tolerance: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Truth vs applied shifts at island stations; shifts at mainland decoys."""
    applied = ((cal_on - cal_off) / CYCLE_MM).reindex(raw.index)
    rows = []
    for s, m in partners.items():
        dm = ((raw[s] - raw[m]) - (gnss[s] - gnss[m])) / CYCLE_MM
        for (ref, sec), v in dm.items():
            if not np.isfinite(v):
                continue
            n = round(v)
            labelled = abs(v - n) < label_tolerance
            a = applied.at[(ref, sec), s] if s in applied else np.nan
            rows.append(
                {
                    "station": s,
                    "mainland": m,
                    "ref": ref.date(),
                    "sec": sec.date(),
                    "misfit_cycles": v,
                    "true_error": n if labelled else np.nan,
                    # the correction removes the error: applied = -error
                    "applied_cycles": round(-a) if np.isfinite(a) else np.nan,
                    "applied_raw": -a,
                }
            )
    cases = pd.DataFrame(rows)
    lab = cases.dropna(subset=["true_error", "applied_cycles"])
    shifted = lab[lab["applied_cycles"] != 0]
    errors = lab[lab["true_error"] != 0]
    correct = (shifted["applied_cycles"] == shifted["true_error"]).sum()
    dec = applied[[c for c in mainland if c in applied]]
    dec_shifts = int((dec.abs().round() >= 1).sum().sum())
    summary = {
        "labelled_cases": len(lab),
        "ambiguous_cases": int(cases["true_error"].isna().sum()),
        "true_errors": len(errors),
        "shifts_at_islands": len(shifted),
        "correct_shifts": int(correct),
        "precision": float(correct / len(shifted)) if len(shifted) else np.nan,
        "recall": float(correct / len(errors)) if len(errors) else np.nan,
        "decoy_station_pairs": int(dec.notna().sum().sum()),
        "decoy_shifts": dec_shifts,
    }
    return cases, dec, summary


def score_blocks(
    cases: pd.DataFrame, label_tolerance: float = 0.25, max_std: float = 0.45
) -> tuple[pd.DataFrame, dict]:
    """Block-level truth: errors persist through a reference-date block.

    Per (station, block): the mean pair misfit is labelled ``round(mean)``
    when the block's pairs agree (std below `max_std` cycles) and the mean is
    within `label_tolerance` of a whole cycle; the applied shift is the
    block's median rounded.
    """
    g = cases.groupby(["station", "ref"])
    b = g.agg(
        n=("misfit_cycles", "size"),
        mean=("misfit_cycles", "mean"),
        std=("misfit_cycles", "std"),
        applied=("applied_raw", "median"),
    )
    b["applied"] = b["applied"].round()
    near = (b["mean"] - b["mean"].round()).abs() < label_tolerance
    b["true_error"] = np.where(near & (b["std"] < max_std), b["mean"].round(), np.nan)
    lab = b.dropna(subset=["true_error", "applied"])
    shifted = lab[lab["applied"] != 0]
    errors = lab[lab["true_error"] != 0]
    correct = int((shifted["applied"] == shifted["true_error"]).sum())
    return b.reset_index(), {
        "blocks": len(b),
        "labelled_blocks": len(lab),
        "error_blocks": len(errors),
        "shifted_blocks": len(shifted),
        "correct_blocks": correct,
        "precision": float(correct / len(shifted)) if len(shifted) else np.nan,
        "recall": float(correct / len(errors)) if len(errors) else np.nan,
    }


def classify_by_region(stations: pd.DataFrame, water_mask: Path) -> pd.Series:
    """Region label of each station on the water-mask segmentation (needs Venti)."""
    import rasterio
    from venti.unwrap.regions import segment_regions

    with rasterio.open(water_mask) as ds:
        land = ds.read(1).astype(bool)
    labels = segment_regions(land)
    r, c = stations["row"].to_numpy(), stations["col"].to_numpy()
    return pd.Series(labels[r, c], index=stations.index, name="region")


def main() -> None:
    """Command line."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in (
        "stations",
        "raw",
        "cal_off",
        "cal_on",
        "daily",
        "disp_dir",
        "water_mask",
        "out",
    ):
        p.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    p.add_argument("--frame", required=True)
    p.add_argument("--partner-km", type=float, default=30.0)
    a = p.parse_args()

    st = pd.read_csv(a.stations, index_col=0)
    region = classify_by_region(st, a.water_mask)
    st = st.assign(region=region)
    main_id = int(region[region > 0].value_counts().idxmax())
    island = [s for s in st.index if region[s] > 0 and region[s] != main_id]
    mainland = [s for s in st.index if region[s] == main_id]
    partners = nearest_partner(st, island, mainland, a.partner_km)

    pairs = [
        (pd.Timestamp(e.ref).normalize(), pd.Timestamp(e.sec).normalize())
        for e in list_epochs(a.disp_dir)
    ]

    def series(path: Path) -> pd.DataFrame:
        s = pd.read_csv(path, index_col=0, parse_dates=True)
        return pair_values(s[[c for c in st.index if c in s]], pairs)

    daily = pd.read_csv(a.daily, parse_dates=["date"])
    daily = daily[daily["station"].isin(st.index)]
    lv = st.loc[daily["station"], ["los_e", "los_n", "los_u"]].to_numpy()
    daily["los"] = (lv * daily[["east", "north", "up"]].to_numpy()).sum(axis=1) * 1000.0
    wide = daily.pivot_table(index="date", columns="station", values="los")
    raw = series(a.raw)
    gnss = gnss_pair_values(wide, list(raw.index)).reindex(raw.index)
    cases, _, summary = score(
        raw,
        gnss,
        series(a.cal_off),
        series(a.cal_on),
        partners=partners,
        mainland=mainland,
    )
    blocks, block_summary = score_blocks(cases) if len(cases) else (pd.DataFrame(), {})
    summary.update(blocks=block_summary)
    summary.update(
        frame=a.frame,
        island_stations=island,
        partners=partners,
        n_regions_with_stations=int(region[region > 0].nunique()),
    )
    a.out.mkdir(parents=True, exist_ok=True)
    cases.to_csv(a.out / "truth_islands.csv", index=False)
    blocks.to_csv(a.out / "truth_blocks.csv", index=False)
    (a.out / "ts_u1.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    if len(cases):
        print(
            cases.groupby("station")[["misfit_cycles", "applied_raw"]]
            .describe()
            .round(2)
            .to_string()
        )


if __name__ == "__main__":
    main()
