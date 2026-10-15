# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Read the YAML configs (``run.yaml``, ``gate.yaml``, ``vlm.yaml``).

Environment variables in a config (``$E2E_ROOT/runs/...``) are expanded, so
one config serves every machine that sets them (``configs/benchmark``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

__all__ = ["read_config"]

_UNSET = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")


def read_config(path: Path | str) -> dict[str, Any]:
    """Return the mapping in the YAML file `path`, environment variables expanded.

    Raises
    ------
    ValueError
        A variable the config uses is not set.

    """
    text = Path(path).read_text()
    body = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    missing = sorted(
        {m for m in _UNSET.findall(os.path.expandvars(body)) if m not in os.environ}
    )
    if missing:
        msg = f"{path}: environment variable(s) not set: {', '.join(missing)}"
        raise ValueError(msg)
    return yaml.safe_load(os.path.expandvars(text)) or {}
