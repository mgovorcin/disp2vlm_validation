# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""``disp2vlm-validate`` command line.

``gate`` prints the release gate and the benchmark frames; ``run`` validates
one candidate on one frame (``run.yaml``, see `pipeline.RunConfig`); ``vlm``
validates a VLM run against GNSS (``vlm.yaml``, see `vlm.VlmRunConfig`);
``summary`` gathers frame runs into ``release_summary.html``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import tyro

from . import __version__
from .requirements import BENCHMARK_FRAMES, GATE


def gate(
    fmt: Annotated[Literal["text", "json"], tyro.conf.arg(name="format")] = "text",
) -> None:
    """Print the CalVal release gate and the benchmark frames (PRD 2.7)."""
    if fmt == "json":
        print(json.dumps({"gate": asdict(GATE), "frames": BENCHMARK_FRAMES}, indent=1))
        return
    print(f"disp2vlm-validation {__version__}: CalVal release gate")
    for key, value in asdict(GATE).items():
        print(f"  {key:30s} {value}")
    print("benchmark frames:")
    for num, f in BENCHMARK_FRAMES.items():
        print(f"  {num}. {f['frame']:7s} {f['name']:32s} {f['condition']}")


def run(config: Path, no_cache: bool = False, verbose: bool = False) -> None:
    """Validate one candidate on one frame; write metrics, figures, report.html.

    Parameters
    ----------
    config
        ``run.yaml`` (`disp2vlm_validation.pipeline.RunConfig`).
    no_cache
        Recompute even when ``metrics.json`` has the same config hash.
    verbose
        Debug logging.

    """
    from .pipeline import load_run_config, run_validation

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    m = run_validation(load_run_config(config), use_cache=not no_cache)
    print(f"{m['frame']} {m['label']}: {m['verdict']}")
    for r in m["verdict_reasons"]:
        print(f"  - {r}")


def vlm(config: Path, verbose: bool = False) -> None:
    """Validate one VLM run against independent GNSS (``vlm.yaml``).

    See `disp2vlm_validation.vlm.VlmRunConfig` for the fields.
    """
    import yaml

    from .vlm import VlmRunConfig, run_vlm

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = VlmRunConfig(**yaml.safe_load(Path(config).read_text()))
    m = run_vlm(cfg)
    s = m["vertical_rate"]["gated_both_looks"]
    print(
        f"{m['frame']} {m['label']}: {m['verdict']} (n={s.get('n')}, median"
        f" {s.get('median', float('nan')):+.2f}, NMAD"
        f" {s.get('nmad', float('nan')):.2f}, RMSE {s.get('rmse', float('nan')):.2f}"
        " mm/yr)"
    )
    for r in m["verdict_reasons"]:
        print(f"  - {r}")


def summary(
    runs: list[Path],
    /,
    out: Path = Path("release_summary.html"),
    title: str = "Release summary",
) -> None:
    """Gather frame runs (folders with ``metrics.json``) into one HTML page."""
    from .report import write_summary

    path = write_summary(runs, out, title)
    for d in runs:
        m = json.loads((Path(d) / "metrics.json").read_text())
        print(f"{m['frame']:8s} {m['label']:24s} {m['verdict']}")
    print(f"wrote {path}")


def main() -> None:
    """Entry point."""
    tyro.extras.subcommand_cli_from_dict(
        {"gate": gate, "run": run, "vlm": vlm, "summary": summary},
        description=__doc__,
    )


if __name__ == "__main__":
    main()
