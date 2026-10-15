# Copyright (c) 2026 California Institute of Technology ("Caltech").
# U.S. Government sponsorship acknowledged.
# SPDX-License-Identifier: Apache-2.0
"""Configs expand environment variables (configs/benchmark)."""

from __future__ import annotations

from pathlib import Path

import pytest

from disp2vlm_validation.config_io import read_config
from disp2vlm_validation.gate import load_gate
from disp2vlm_validation.pipeline import load_run_config

BENCHMARK = Path(__file__).parents[1] / "configs" / "benchmark"


def test_variables_are_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("E2E_ROOT", "/data/e2e")
    p = tmp_path / "c.yaml"
    p.write_text("a: $E2E_ROOT/runs  # $NOT_A_PATH in a comment\nb: ${E2E_ROOT}/x\n")
    assert read_config(p) == {"a": "/data/e2e/runs", "b": "/data/e2e/x"}


def test_an_unset_variable_is_named(tmp_path, monkeypatch):
    monkeypatch.delenv("E2E_ROOT", raising=False)
    p = tmp_path / "c.yaml"
    p.write_text("a: $E2E_ROOT/runs\n")
    with pytest.raises(ValueError, match="E2E_ROOT"):
        read_config(p)


def test_benchmark_configs_load_with_the_documented_variables(monkeypatch):
    """Every benchmark run.yaml validates once the README's variables are set."""
    for var in ("E2E_ROOT", "DISP_DATA", "SRC", "TRADE_STUDIES"):
        monkeypatch.setenv(var, f"/data/{var.lower()}")
    runs = [
        p
        for p in BENCHMARK.rglob("*.yaml")
        if not p.name.startswith(("gate_", "algorithm_parameters"))
    ]
    assert len(runs) >= 10
    for p in runs:
        cfg = load_run_config(p)
        assert str(cfg.frame.disp_dir).startswith("/data/"), p
        assert "aurora" not in str(cfg.model_dump()), p
    assert load_gate(BENCHMARK / "gate_F08882.yaml").per_class_targets
