# Baselines

Numbers this package must reproduce, and the release comparisons it has made.
Configs are in `configs/aurora/` (paths on aurora; the GNSS of every frame is
frozen in its `cache_dir` on first use).

## Reproduction of the trade study (plan T25.4)

`disp2vlm-validate run --config configs/aurora/F08882_repro_gamma.yaml`
re-validates the gamma run `runs/7085ec9-notropo` (cal-disp `v0.2-79-g7085ec9`,
600 km window, troposphere off) against `runs/7df274a`, which is what
`trade studies/e2e_validation/validate_stack.py` reported on 2026-10-02. It
reuses the trade study's raw-stack cache (`stack_adbefbce8a04`; the key is the
same by construction).

F08882 (Houston), 204 epochs, reference pixel (3054, 6260), UH01 excluded.

| quantity | trade study | disp2vlm-validation |
|---|---|---|
| DD sill calibrated (mm²) [95% CI] | 257.0 [234–281] | 257.0 [234–281] |
| DD sill raw (mm²) [95% CI] | 510.0 [452–582] | 510.0 [452–582] |
| DD sill baseline 7df274a (mm²) [95% CI] | 271.5 [251–293] | 271.5 [251–293] |
| stations / pairs in the DD | 107 / 5540 | 107 / 5540 |
| sill change vs raw | −49.6% [−55.9, −43.5] | −49.6% [−55.9, −43.5] |
| sill change vs baseline | −5.3% [−11.5, +0.3] | −5.3% [−11.5, +0.3] |
| LOS velocity vs MIDAS, n | 126 | 126 |
| calibrated bias / RMSE (mm/yr) | +4.05 / 5.07 | +4.05 / 5.07 |
| raw bias / RMSE (mm/yr) | −6.22 / 7.04 | −6.22 / 7.04 |
| baseline bias / RMSE (mm/yr) | +3.73 / 4.82 | +3.73 / 4.82 |
| verdict | FAIL (RMSE +0.25, \|bias\| +0.32 vs 7df274a) | FAIL (same two reasons) |

Identical to the printed digit, bootstrap intervals included (same seed and
paired draws). The FAIL is the trade study's own verdict on the 600 km /
troposphere-off gamma configuration against the earlier 7df274a run; that
configuration was accepted for gamma regardless (cal-disp
`docs/decisions/0001-gamma-config.md`: 600 km, troposphere off, unwrap off).

Note the default raw reference pixel: the trade study used (3054, 6260); the
last F08882 product's `corrections/reference_point` is (2898, 6117). Only the
raw variant depends on it (its bias, and the cache key), so configs that
must match the trade study set `ref_pixel` explicitly.
