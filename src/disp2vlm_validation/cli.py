# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""``disp2vlm-validate`` command line.

Only the ``gate`` subcommand exists today (prints the release gate and the
benchmark frames); the metric subcommands land with the e2e port (plan T21).
"""

from __future__ import annotations

import json
from dataclasses import asdict
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


def main() -> None:
    """Entry point."""
    tyro.extras.subcommand_cli_from_dict({"gate": gate}, description=__doc__)


if __name__ == "__main__":
    main()
