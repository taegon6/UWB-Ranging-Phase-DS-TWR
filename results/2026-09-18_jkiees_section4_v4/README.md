# JKIEES Section IV v4 results (experiments 2, 3, 4, 7)

This folder records the selected-run results used for the revised Section IV manuscript.

## Selected experiments

- Experiment 2: Final stop
- Experiment 3: Next
- Experiment 4: Phase again
- Experiment 7: Run8

## Valid vehicle-pose update rate

The update rate is defined from valid vehicle-pose outputs within each ranging mode.

- SS-TWR: 113.9 Hz
- DS-TWR: 50.7 Hz
- PHASE: 26.3 Hz

## PHASE final endpoint result

Post-calibration leave-one-run-out endpoint errors for the selected four experiments:

- Exp. 2: 3.8253 cm
- Exp. 3: 4.4774 cm
- Exp. 4: 4.1885 cm
- Exp. 7: 0.7678 cm
- Mean: 3.31 cm
- RMSE: 3.63 cm

The 3.63 cm result is not the last raw online PHASE sample. It is the calibrated terminal estimate described in the manuscript revision.

## Trajectory figure convention

The trajectory figure keeps original valid raw poses unchanged. Frames that had complete raw four-link ranges but no valid online pose are re-solved offline with the 2A2T geometry. Intervals with no complete frame are shown as visual connectors only and are excluded from quantitative evaluation.

## Manuscript and figures

The DOCX, rendered PDF, and figure PDF/PNG files are stored in the project Google Drive folder:

https://drive.google.com/drive/folders/1444RS_m0EdpJbm3Vl130yQaPf0Y5O1IB

This GitHub repository intentionally avoids committing large raw experiment logs.
