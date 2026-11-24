# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""VelocityFit: chained blocks and gaps that no pair bridges."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from disp2vlm_validation.stack import VelocityFit, decimal_year

SHAPE = (3, 4)
RATE = 0.02  # m/yr


def blocks(starts, per_block=6, step=24, rng=None, noise=0.0):
    """``(ref, sec, disp)``: blocks starting at `starts`; each block chains onto
    the previous one unless the next start is later than its last secondary."""
    out = []
    for s in starts:
        for k in range(1, per_block + 1):
            sec = s + timedelta(days=step * k)
            disp = np.full(SHAPE, RATE * (sec - s).days / 365.25)
            if rng is not None:
                disp = disp + rng.normal(0.0, noise, SHAPE)
            out.append((s, sec, disp))
    return out


def run(epochs, t0, mask=None, **kw):
    fit = VelocityFit(SHAPE, t0, **kw)
    mask = np.ones(SHAPE, bool) if mask is None else mask
    for ref, sec, d in epochs:
        fit.add(ref, decimal_year(sec), d, mask)
    return fit


def test_gap_gets_its_own_intercept():
    a = datetime(2016, 7, 1)
    b = a + timedelta(days=6 * 24 + 3 * 365)  # 3 years with no bridging pair
    ep = blocks([a, b])
    t0 = np.mean([decimal_year(s) for _, s, _ in ep])
    fit = run(ep, t0)
    np.testing.assert_allclose(fit.velocity_mm_yr(), 20.0, rtol=1e-5)
    assert fit.segments == 2 and len(fit.gaps) == 1
    # gluing the blocks (the old behaviour) loses the motion across the gap
    glued = run(ep, t0, gap_days=1e9)
    assert glued.segments == 1
    assert (glued.velocity_mm_yr() < 10.0).all()


def test_connected_blocks_match_polyfit():
    rng = np.random.default_rng(0)
    a = datetime(2017, 1, 1)
    starts = [a + timedelta(days=6 * 24 * i) for i in range(4)]  # each chains on
    ep = blocks(starts, rng=rng, noise=0.003)
    t = np.array([decimal_year(s) for _, s, _ in ep])
    fit = run(ep, t.mean())
    assert fit.segments == 1 and not fit.gaps
    cum, off, last = [], np.zeros(SHAPE), None
    for ref, _, d in ep:
        if last is not None and ref != last[0]:
            off = last[1]
        c = off + d
        cum.append(c)
        last = (ref, c)
    cum = np.array(cum)
    want = np.polyfit(t, cum.reshape(len(t), -1), 1)[0].reshape(SHAPE) * 1000
    np.testing.assert_allclose(fit.velocity_mm_yr(), want, rtol=1e-4)


def test_gap_matches_least_squares_with_two_intercepts_and_nans():
    rng = np.random.default_rng(1)
    a = datetime(2016, 1, 1)
    b = a + timedelta(days=6 * 24 + 1200)
    ep = blocks([a, b], rng=rng, noise=0.004)
    ep[2][2][0, 0] = np.nan  # a missing epoch in one pixel
    t = np.array([decimal_year(s) for _, s, _ in ep])
    seg = np.array([0] * 6 + [1] * 6)
    fit = run(ep, t.mean())
    got = fit.velocity_mm_yr()
    for i, j in np.ndindex(SHAPE):
        y = np.array([d[i, j] for _, _, d in ep])
        y[6:] += y[5]  # chained as VelocityFit chains (any offset: own intercept)
        ok = np.isfinite(y)
        g = np.column_stack([t, seg == 0, seg == 1]).astype(float)[ok]
        want = np.linalg.lstsq(g, y[ok], rcond=None)[0][0] * 1000
        np.testing.assert_allclose(got[i, j], want, rtol=1e-4)


def test_explicit_ref_t_and_one_epoch_segment():
    a, b = 2018.0, 2022.0
    fit = VelocityFit(SHAPE, 2019.0)
    m = np.ones(SHAPE, bool)
    for k in range(1, 7):
        fit.add("A", a + 0.1 * k, np.full(SHAPE, RATE * 0.1 * k), m, ref_t=a)
    fit.add("B", b + 0.1, np.full(SHAPE, 5.0), m, ref_t=b)  # lone epoch: no slope info
    np.testing.assert_allclose(fit.velocity_mm_yr(), 20.0, rtol=1e-5)
    assert fit.segments == 2


def test_too_few_epochs_is_nan():
    assert np.isnan(VelocityFit(SHAPE, 0.0).velocity_mm_yr(min_epochs=5)).all()
