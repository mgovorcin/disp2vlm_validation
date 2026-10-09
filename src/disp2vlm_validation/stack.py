# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""DISP stacks, their DISP-CAL products, and chained per-pixel velocities.

Ported from ``trade studies/e2e_validation/validate_stack.py`` (plan T21.2,
T21.4) without hard-coded paths. A stack is the set of DISP-S1 products of a
frame; each epoch may have a DISP-CAL product with the same reference and
secondary dates. Calibrated displacement is ``DISP - calibration``.

Epochs are chained across reference-date blocks as
``opera_utils.disp.create_rebased_displacement`` does: the last cumulative
value of a block is the offset of the next one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

__all__ = [
    "Epoch",
    "VelocityFit",
    "apply_calibration",
    "decimal_year",
    "list_epochs",
    "parse_dates",
    "read_epoch",
    "stream_epochs",
]

PAIR_DATES = re.compile(r"_(\d{8}T\d{6})Z_(\d{8}T\d{6})Z_")
DISP_GLOB = "OPERA_L3_DISP-*.nc"
CAL_GLOB = "OPERA_L4_DISP-CAL-*.nc"
_EPOCH0 = datetime(2000, 1, 1)
DAYS_PER_YEAR = 365.25


def parse_dates(name: str) -> tuple[datetime, datetime]:
    """Return the reference and secondary datetimes of a DISP or DISP-CAL file."""
    m = PAIR_DATES.search(name)
    if m is None:
        msg = f"no _<ref>Z_<sec>Z_ dates in {name!r}"
        raise ValueError(msg)
    ref, sec = m.groups()
    return (
        datetime.strptime(ref, "%Y%m%dT%H%M%S"),
        datetime.strptime(sec, "%Y%m%dT%H%M%S"),
    )


def decimal_year(t: datetime) -> float:
    """Decimal year with 365.25-day years from 2000-01-01."""
    return 2000.0 + (t - _EPOCH0).total_seconds() / 86400.0 / DAYS_PER_YEAR


@dataclass(frozen=True)
class Epoch:
    """One DISP product and, if found, its DISP-CAL product."""

    ref: datetime
    sec: datetime
    disp: Path
    cal: Path | None = None

    @property
    def tag(self) -> str:
        """``<ref>_<sec>`` dates, the key used to match DISP and DISP-CAL."""
        return f"{self.ref:%Y%m%d}_{self.sec:%Y%m%d}"

    @property
    def t(self) -> float:
        """Secondary date as a decimal year."""
        return decimal_year(self.sec)


def _index_cal_products(cal_dir: Path) -> dict[str, Path]:
    """Newest DISP-CAL product per pair tag, searched recursively.

    Accepts both a flat directory and the e2e layout
    ``products/<tag>/OPERA_L4_DISP-CAL-*.nc`` (a ``.done`` marker next to the
    product is honoured when present in any product directory).
    """
    out: dict[str, Path] = {}
    done_dirs = {p.parent for p in Path(cal_dir).rglob(".done")}
    for path in sorted(Path(cal_dir).rglob(CAL_GLOB)):
        if done_dirs and path.parent not in done_dirs:
            continue  # an interrupted e2e product directory
        ref, sec = parse_dates(path.name)
        tag = f"{ref:%Y%m%d}_{sec:%Y%m%d}"
        if tag not in out or path.name > out[tag].name:  # newest production time
            out[tag] = path
    return out


def list_epochs(
    disp_dir: Path | str,
    cal_dir: Path | str | None = None,
    *,
    allow_partial: bool = False,
) -> list[Epoch]:
    """Epochs of a stack sorted by secondary date, each with its CAL product.

    Raises
    ------
    FileNotFoundError
        If `disp_dir` has no DISP product, or a CAL product is missing and
        `allow_partial` is False (then those epochs are skipped instead).

    """
    disp_files = sorted(Path(disp_dir).glob(DISP_GLOB))
    if not disp_files:
        msg = f"no {DISP_GLOB} in {disp_dir}"
        raise FileNotFoundError(msg)
    cal_index = _index_cal_products(Path(cal_dir)) if cal_dir is not None else {}
    epochs: list[Epoch] = []
    missing: list[str] = []
    for f in disp_files:
        ref, sec = parse_dates(f.name)
        e = Epoch(ref=ref, sec=sec, disp=f)
        if cal_dir is not None:
            cal = cal_index.get(e.tag)
            if cal is None:
                missing.append(e.tag)
                continue
            e = Epoch(ref=ref, sec=sec, disp=f, cal=cal)
        epochs.append(e)
    if missing and not allow_partial:
        msg = (
            f"{len(missing)} epochs have no DISP-CAL product in {cal_dir}"
            f" (first: {missing[:3]}); pass allow_partial to skip them"
        )
        raise FileNotFoundError(msg)
    epochs.sort(key=lambda e: e.sec)
    return epochs


def _read2d(path: Path, key: str) -> np.ndarray:
    with h5py.File(path) as f:
        return np.squeeze(f[key][()])


def read_epoch(
    epoch: Epoch, ref_pixel: tuple[int, int] | None = None
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """Return ``(calibrated, raw, coherence)`` for one epoch (float32, metres).

    ``calibrated`` is ``DISP - calibration`` (None without a CAL product);
    ``raw`` (only with `ref_pixel`) is DISP referenced to that pixel, and
    ``coherence`` its temporal coherence.
    """
    disp = _read2d(epoch.disp, "displacement")
    calibrated = None
    if epoch.cal is not None:
        calibrated = (disp - _read2d(epoch.cal, "calibration")).astype(np.float32)
    raw = coh = None
    if ref_pixel is not None:
        raw = (disp - disp[tuple(ref_pixel)]).astype(np.float32)
        coh = _read2d(epoch.disp, "temporal_coherence").astype(np.float32)
    return calibrated, raw, coh


def apply_calibration(epoch: Epoch) -> np.ndarray:
    """Calibrated displacement ``DISP - calibration`` of one epoch (plan T21.4)."""
    if epoch.cal is None:
        msg = f"epoch {epoch.tag} has no DISP-CAL product"
        raise ValueError(msg)
    calibrated, _, _ = read_epoch(epoch)
    assert calibrated is not None
    return calibrated


def stream_epochs(
    epochs: Sequence[Epoch],
    ref_pixel: tuple[int, int] | None = None,
    workers: int = 4,
) -> Iterator[
    tuple[Epoch, tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]]
]:
    """Yield ``(epoch, read_epoch(epoch))`` in order, reading ahead in processes.

    ``workers=0`` reads in this process (tests, small stacks).
    """
    if workers <= 0:
        for e in epochs:
            yield e, read_epoch(e, ref_pixel)
        return
    with ProcessPoolExecutor(workers) as pool:
        futs = [pool.submit(read_epoch, e, ref_pixel) for e in epochs[:workers]]
        for i, e in enumerate(epochs):
            res = futs[i].result()
            futs[i] = None  # type: ignore[call-overload]
            if i + workers < len(epochs):
                futs.append(pool.submit(read_epoch, epochs[i + workers], ref_pixel))
            yield e, res


class VelocityFit:
    """Streaming per-pixel OLS of chained cumulative displacement against time.

    Buffers are preallocated and updated in place: fresh full-frame
    temporaries every epoch cost more in page faults than the arithmetic.
    """

    def __init__(self, shape: tuple[int, int], t0: float) -> None:
        self.t0 = t0
        self.n, self.st, self.st2, self.sy, self.sty = (
            np.zeros(shape) for _ in range(5)
        )
        self.offset, self.cum, self.tmp = (np.zeros(shape) for _ in range(3))
        self.ok = np.zeros(shape, dtype=bool)
        self.block: object = None

    def add(
        self, block_key: object, t: float, disp_m: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        """Add an epoch of block `block_key` (its reference date); return cumulative."""
        if block_key != self.block:
            if self.block is not None:
                np.copyto(
                    self.offset, self.cum
                )  # last cumulative of the previous block
            self.block = block_key
        np.add(self.offset, disp_m, out=self.cum)
        np.isfinite(self.cum, out=self.ok)
        np.logical_and(self.ok, mask, out=self.ok)
        tt = t - self.t0
        np.add(self.n, 1.0, out=self.n, where=self.ok)
        np.add(self.st, tt, out=self.st, where=self.ok)
        np.add(self.st2, tt * tt, out=self.st2, where=self.ok)
        np.add(self.sy, self.cum, out=self.sy, where=self.ok)
        np.multiply(self.cum, tt, out=self.tmp)
        np.add(self.sty, self.tmp, out=self.sty, where=self.ok)
        return self.cum

    def velocity_mm_yr(self, min_epochs: int = 5) -> np.ndarray:
        """OLS slope in mm/yr; NaN with fewer than `min_epochs` valid epochs."""
        den = self.n * self.st2 - self.st**2
        good = (self.n >= min_epochs) & (den > 0)
        v = np.full(self.n.shape, np.nan)
        v[good] = (self.n[good] * self.sty[good] - self.st[good] * self.sy[good]) / den[
            good
        ]
        return (v * 1000.0).astype(np.float32)
