# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Independent GNSS validation of OPERA DISP-CAL and VLM products.

The package judges calibrated displacement against GNSS that the calibration
never saw (UNR daily station positions and MIDAS rates), computes the
CalVal release-gate metrics and writes the VnV reports. Scope:
``docs/scope.md``; requirements: Venti ``docs/specs.md`` sections 2.7 and 3.4.
"""

from .requirements import GATE, GateThresholds

try:
    from ._version import __version__
except ImportError:  # pragma: no cover - not installed
    __version__ = "0.0.0"

__all__ = ["GATE", "GateThresholds", "__version__"]
