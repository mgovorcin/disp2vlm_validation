# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Reports and traceability (plan T24).

Per frame: ``stations.csv``, ``sill_draws.npz``, SVG figures and
``report.html``; across frames: ``release_summary.html``. Every figure is
followed by its data table (the table view the chart conventions require,
and the only form a reviewer can quote). Colours: the validated categorical
order blue (calibrated), orange (raw), aqua (baseline); status colours only
for the verdict, always with a text label.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from jinja2 import Environment, FunctionLoader, select_autoescape

__all__ = [
    "TRACE_CHECKS",
    "load_traceability",
    "trace_table",
    "write_outputs",
    "write_summary",
]

COLORS = {"calibrated": "#2a78d6", "raw": "#eb6834", "baseline": "#1baf7a"}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"


def _fmt(x: Any, nd: int = 1) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "\u2013"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    return f"{float(x):.{nd}f}"


def _signed(x: Any, nd: int = 1) -> str:
    if x is None or not math.isfinite(float(x)):
        return "\u2013"
    return f"{float(x):+.{nd}f}"


# ---------------------------------------------------------------- traceability


def load_traceability() -> list[dict[str, Any]]:
    """Entries of the packaged ``traceability.yaml``."""
    text = (
        resources.files("disp2vlm_validation").joinpath("traceability.yaml").read_text()
    )
    return yaml.safe_load(text)


def _check_sill_below_raw(m: Mapping) -> tuple[str, str]:
    c, r = (
        m["double_difference"]["calibrated"]["sill"],
        m["double_difference"]["raw"]["sill"],
    )
    return ("pass" if c < r else "fail"), f"{_fmt(c)} vs raw {_fmt(r)} mm²"


def _check_sill_vs_baseline(m: Mapping) -> tuple[str, str]:
    b = m.get("sill_change_vs_baseline")
    if not b:
        return "n/a", "no baseline"
    failed = any("DD sill up" in r for r in m["verdict_reasons"])
    lo, hi = b["ci95"]
    return (
        "fail" if failed else "pass"
    ), f"{_signed(b['pct'])}% [{_signed(lo)}, {_signed(hi)}]"


def _check_velocity_vs_baseline(m: Mapping) -> tuple[str, str]:
    d = m.get("deltas", {})
    if "velocity_rmse_change_mm_yr" not in d:
        return "n/a", "no baseline"
    failed = any("velocity" in r for r in m["verdict_reasons"])
    return (
        "fail" if failed else "pass",
        (
            f"RMSE {_signed(d['velocity_rmse_change_mm_yr'], 2)},"
            f" |{_bias_label(m)}|"
            f" {_signed(d['velocity_abs_bias_change_mm_yr'], 2)} mm/yr"
        ),
    )


def _check_golden_epoch(m: Mapping) -> tuple[str, str]:
    g = str(m.get("golden_epoch_check", "not run"))
    if g == "not run" or g.startswith("no candidate"):
        return "n/a", g
    failed = "golden-epoch check failed" in m["verdict_reasons"]
    return ("fail" if failed else "pass"), "cal-disp validate"


def _bias_key(m: Mapping) -> str:
    """Velocity-stats key of the bias the gate used (median since decision 0001)."""
    stat = m.get("deltas", {}).get("bias_statistic", "median")
    return "median" if stat == "median" else "bias"


def _bias_label(m: Mapping) -> str:
    return "median bias" if _bias_key(m) == "median" else "bias"


def _check_bias_target(m: Mapping) -> tuple[str, str]:
    b = m["velocity_los"]["calibrated"].get(_bias_key(m))
    if b is None:
        return "n/a", "no stations"
    return ("pass" if abs(b) <= 1.0 else "note"), f"{_signed(b, 2)} mm/yr"


def _check_independent_gnss(m: Mapping) -> tuple[str, str]:
    return "pass", f"{m['n_gnss_stations']} UNR stations, MIDAS"


def _check_classes_reported(m: Mapping) -> tuple[str, str]:
    n = sum(1 for r in m["velocity_by_class"] if r["class"] != "all" and r["n"] > 0)
    return "pass", f"{n} classes with stations"


TRACE_CHECKS = {
    "sill_below_raw": _check_sill_below_raw,
    "sill_vs_baseline": _check_sill_vs_baseline,
    "velocity_vs_baseline": _check_velocity_vs_baseline,
    "golden_epoch": _check_golden_epoch,
    "bias_target": _check_bias_target,
    "independent_gnss": _check_independent_gnss,
    "classes_reported": _check_classes_reported,
}


def trace_table(metrics: Mapping) -> list[dict[str, Any]]:
    """Traceability rows with the status and evidence of one run."""
    rows = []
    for entry in load_traceability():
        status, evidence = TRACE_CHECKS[entry["check"]](metrics)
        rows.append({**entry, "status": status, "evidence": evidence})
    return rows


# ---------------------------------------------------------------- figures


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "svg.fonttype": "none",
            "axes.axisbelow": True,
        }
    )
    return plt


def fig_semivariogram(
    svs: Mapping[str, pd.DataFrame], path: Path, sill_min_km: float
) -> pd.DataFrame:
    """Binned DD misfit semivariogram per variant; returns the plotted table."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    rows = []
    for name, sv in svs.items():
        if sv.empty:
            continue
        x = (
            sv["distance_km"].to_numpy()
            if "distance_km" in sv
            else sv.iloc[:, 0].to_numpy()
        )
        ycol = "gamma" if "gamma" in sv else next(c for c in sv.columns if "gamma" in c)
        y = sv[ycol].to_numpy()
        ax.plot(x, y, "-o", lw=2, ms=6, color=COLORS.get(name, INK_2), label=name)
        ax.annotate(
            name,
            (x[-1], y[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            color=INK_2,
            va="center",
            fontsize=9,
        )
        rows += [
            {"variant": name, "distance_km": float(a), "gamma_mm2": float(b)}
            for a, b in zip(x, y, strict=True)
        ]
    ax.axvline(sill_min_km, color=INK_2, lw=1, ls=":")
    from matplotlib.ticker import FixedLocator, NullLocator, ScalarFormatter

    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50, 100, 200, 500]))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel("station separation (km)")
    ax.set_ylabel("misfit semivariance \u03b3 (mm\u00b2)")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return pd.DataFrame(rows)


def fig_scatter(st: pd.DataFrame, path: Path) -> pd.DataFrame:
    """InSAR vs MIDAS LOS velocity at the station pixels."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    gps = st["gps_los_mm_yr"].to_numpy()
    lim = np.nanpercentile(
        np.abs(np.r_[gps, st.filter(like="pix::").to_numpy().ravel()]), 99
    )
    ax.plot([-lim, lim], [-lim, lim], color=INK_2, lw=1)
    for name in ("raw", "calibrated"):
        col = f"pix::{name}"
        if col in st:
            ax.scatter(
                gps,
                st[col],
                s=48,
                color=COLORS[name],
                edgecolor=SURFACE,
                linewidth=1,
                label=name,
            )
    ax.set_xlabel("GNSS (MIDAS) LOS velocity (mm/yr)")
    ax.set_ylabel("InSAR LOS velocity (mm/yr)")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    cols = ["class", "gps_los_mm_yr", *[c for c in st.columns if c.startswith("pix::")]]
    return st[[c for c in cols if c in st]].round(2)


def fig_class_rmse(by_class: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Calibrated velocity RMSE per station class (one series: no legend)."""
    plt = _plt()
    d = by_class[(by_class["n"] > 0) & (by_class.index != "all")]
    fig, ax = plt.subplots(figsize=(5.6, 2.8))
    if len(d):
        ax.barh(d.index, d["rmse"], color=COLORS["calibrated"], height=0.6)
        for y, (rmse, n) in enumerate(zip(d["rmse"], d["n"], strict=True)):
            ax.annotate(
                f"{rmse:.2f} (n={n})",
                (rmse, y),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                color=INK_2,
                fontsize=9,
            )
    ax.set_xlabel("calibrated LOS velocity RMSE vs MIDAS (mm/yr)")
    ax.grid(axis="y", visible=False)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return d[[c for c in ("n", "bias", "median", "rmse") if c in d]].round(2)


# ---------------------------------------------------------------- HTML


def _env() -> Environment:
    templates = resources.files("disp2vlm_validation").joinpath("templates")
    env = Environment(
        loader=FunctionLoader(lambda name: templates.joinpath(name).read_text()),
        autoescape=select_autoescape(default=True),
    )
    css = templates.joinpath("report.css").read_text()
    env.globals.update(f=_fmt, sg=_signed, css=css)
    return env


def _table_html(df: pd.DataFrame) -> str:
    from markupsafe import Markup

    return Markup(
        df.to_html(border=0, na_rep="\u2013", float_format=lambda x: f"{x:.2f}")
    )


def write_outputs(
    metrics: dict[str, Any],
    stations: pd.DataFrame,
    dd: Any,
    out: Path,
) -> None:
    """``stations.csv``, ``sill_draws.npz``, figures and ``report.html`` in `out`."""
    out = Path(out)
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    stations.to_csv(out / "stations.csv")
    np.savez_compressed(
        out / "sill_draws.npz", **{k: s.draws for k, s in dd.sills.items()}
    )
    sv_df = fig_semivariogram(
        dd.semivariograms, figs / "semivariogram.svg", metrics["sill_min_km"]
    )
    common = stations[np.all(np.isfinite(stations.filter(like="pix::")), axis=1)]
    st_df = fig_scatter(common, figs / "velocity_scatter.svg")
    by_class = pd.DataFrame(metrics["velocity_by_class"]).set_index("class")
    fig_class_rmse(by_class, figs / "class_rmse.svg")
    page = (
        _env()
        .get_template("frame.html.j2")
        .render(
            m=metrics,
            trace=trace_table(metrics),
            sv_table=_table_html(
                sv_df.pivot_table(
                    index="distance_km", columns="variant", values="gamma_mm2"
                )
                if not sv_df.empty
                else sv_df
            ),
            st_table=_table_html(st_df),
        )
    )
    (out / "report.html").write_text(page)


def write_summary(
    run_dirs: Sequence[Path | str], out: Path | str, title: str = "Release summary"
) -> Path:
    """``release_summary.html`` across frame runs (their ``metrics.json``)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    for d in run_dirs:
        m = json.loads((Path(d) / "metrics.json").read_text())
        m["_link"] = os.path.relpath(Path(d) / "report.html", out.parent)
        runs.append(m)
    entries = load_traceability()
    trace_rows = [
        {
            "id": e["id"],
            "requirement": e["requirement"],
            "statuses": [TRACE_CHECKS[e["check"]](m)[0] for m in runs],
        }
        for e in entries
    ]
    page = (
        _env()
        .get_template("summary.html.j2")
        .render(
            title=title,
            runs=runs,
            n_pass=sum(m["verdict"] == "PASS" for m in runs),
            trace_rows=trace_rows,
        )
    )
    out.write_text(page)
    return out
