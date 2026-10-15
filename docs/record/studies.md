# Trade studies

Each study has a script in `studies/`, a test, and a report. The reports
are in the repository.

| Study | Question | Report |
|---|---|---|
| TS-G1 | How well does the interpolated UNR grid (the calibration's GNSS input) match independent stations, and how much should σ_CAL be inflated per frame (k)? | [studies/TS-G1](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-G1/REPORT.md) |
| TS-S1 | How much DISP noise is left below the calibration cutoff (about 50 km)? | [studies/TS-S1](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-S1/REPORT.md) |
| TS-B1 | Where does the stable-station bias come from, and which coherence weighting is best? | [studies/TS-B1](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-B1/REPORT.md) |
| TS-U1 | Does whole-cycle unwrap correction on islands help? (phase 1: no-go for v0.5) | [studies/TS-U1](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-U1/REPORT.md) |
| TS-E4 | Are the product's uncertainties realistic? | [studies/TS-E4](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-E4/REPORT.md) |
| TS-T1 | Does a tropospheric correction help at 0.3–1.5 km relief? (only on humid Puerto Rico) | [studies/TS-T1](https://github.com/mgovorcin/disp2vlm_validation/blob/main/studies/TS-T1/REPORT.md) |

Studies read the validator's outputs; one, TS-G1, also reads the UNR grid
itself, because the grid is its subject. Its results never feed the gate.
