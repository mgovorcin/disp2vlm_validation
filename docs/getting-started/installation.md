# Installation

Python 3.11 to 3.13. The package depends on
[geepers](https://github.com/mgovorcin/geepers) for UNR GNSS access and MIDAS
rates, installed from GitHub.

## With pip

```bash
pip install "disp2vlm-validation @ git+https://github.com/mgovorcin/disp2vlm_validation"
disp2vlm-validate --help
```

## For development (pixi)

The repository has a [pixi](https://pixi.sh) workspace with a locked
environment:

```bash
git clone https://github.com/mgovorcin/disp2vlm_validation
cd disp2vlm_validation
pixi install -e dev
pixi run -e dev test        # pytest
pixi run -e dev lint        # pre-commit (ruff, black, mypy, SPDX headers)
pixi run -e dev docs        # build this site (mkdocs, strict)
pixi run -e dev disp2vlm-validate gate
```

## Optional: Venti

The `venti` extra installs [Venti](https://github.com/mgovorcin/venti-dev),
used only to reproduce a candidate calibration in the trade studies. The
validator itself does not need it.

## Running full frames

A full DISP-S1 frame is about 7700 × 9500 pixels and 200–300 epochs. The
stack is streamed once per run, and the raw velocity is cached per stack, so a
run needs a few GB of memory, not the whole stack. On Linux hosts with
fragmented transparent huge pages, set `NUMPY_MADVISE_HUGEPAGE=0`: without it
large array allocations can be very slow.
