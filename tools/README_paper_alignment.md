# Paper Alignment Notes

This setup was checked against:

- `jkiees-36-3-274.pdf`: IEEE 802.15.4z UWB ranging accuracy and measurement-time optimization.
- `jkiees-36-8-749.pdf`: single-channel high-precision UWB localization.

## What Is Prepared

The current workspace is prepared for the local experiment target:

- two anchors and one tag,
- anchor A at `(0, 0)`,
- anchor B at `(2.5, 0)`,
- `ss-twr` and `ds-twr` run labels,
- positive-y 2D solution from two ranges,
- raw serial logs,
- position CSV,
- 2D map PNG,
- position summary report,
- x/y median filter with default window `30`.

Run from VS Code:

```text
Tasks: Run Task -> UWB MAIN SS: 2-anchor collect + analyze
Tasks: Run Task -> UWB MAIN DS: 2-anchor collect + analyze
```

## Match To jkiees-36-3-274

This paper compares `SS-TWR` and `DS-TWR` and emphasizes setting timing
parameters based on packet duration and DW3000 processing time.

Prepared pieces:

- SS/DS firmware selection tasks are available.
- SS/DS data collection labels are available.
- DS final code already contains tuned delay/timeout values.
- The workspace records mode labels in CSV/meta/report files.

Still to verify on hardware:

- whether the selected SS example prints `DIST: ... m`,
- whether SS and DS are using the intended timing values for the selected PHY,
- whether SS/DS ranging rate and variance match the paper trend.

## Match To jkiees-36-8-749

This paper's high-precision ranging uses DS-TWR plus an additional post-final
packet, CIR first-path phase extraction, phase correction, N-value correction,
and median filtering. Its localization demo uses four anchors and least squares,
then applies a median filter of size 30 to x/y coordinates.

Prepared pieces:

- DS-TWR collection and analysis pipeline.
- x/y median filter window defaults to `30`, matching the demo stabilization idea.
- 2D map generation and summary reporting.

Adapted because the current target is two anchors:

- The paper uses at least three anchors for unambiguous 2D least-squares
  localization and used four anchors in the demo.
- This setup uses two anchors, so it solves the two-circle intersection and keeps
  only the positive-y solution.

Not yet implemented:

- post-final packet exchange,
- CIR phase extraction for poll/response/final/post-final,
- phase-error cancellation,
- N-value correction,
- phase/N median filter size 25.

## Practical Conclusion

The current setup follows the papers at the experiment-pipeline level:

- SS vs DS comparison from the March paper,
- DS-focused high-precision direction and median-filtered coordinates from the
  August paper,
- local adaptation to two anchors with positive-y selection.

It is not yet a full reproduction of the August high-precision method. A full
reproduction requires firmware work for post-final and CIR phase extraction.
