# Semivariogram and deterministic controls correction

Switching MoM/REML left the replacement canvas unattached: an existing empty Qt layout was treated as false and replaced with a second layout. Both controllers now distinguish an empty layout from a missing layout, so the curve remains visible after strategy changes and tab returns.

Published v1.1 draws only the theoretical curve for REML. The current controller follows that behavior again. Experimental bins remain internal starting estimates for optimization; MoM shows experimental observations and its theoretical model. The advanced validation window chooses its engine from the active fitting mode rather than a controller module name, displays optimized REML parameters, and applies the explicitly selected model. Exponential no longer resolves to the Automatic entry.

Framework SDI settings now include **View validation**. This background calculation compares Spherical, Exponential and Gaussian using the popup's current data, fitting method, maximum distance and lag. It displays RMSE, RMSE%, MAE, R², Pearson and LCCC, explains Framework's existing ranking (higher R², then lower RMSE, at its established three decimal precision), and allows applying a selected model with its validated parameters. It does not reuse cached Framework metrics. Changed data or settings invalidate the results, and failures remain visible.

The existing Framework semivariogram computation and automatic method thresholds are preserved. Ordinary Geostatistics retains its current LCCC/RMSE/R² selection policy. Fitting, prediction and CV formulas are unchanged; the UI now uses the actual fitted REML parameters for the curve and application.

IDW and TPS use separate rounded borders. The replacement group boxes receive their properties and are styled for every new dialog. IDW options use two readable rows at 800×600 and 1000×700.

Validation uses real QGIS/Qt in isolated offscreen profiles. The runtime suite checks six successive MoM/REML/Automatic changes, theoretical curve changes, returning to tabs, model validation/application in each mode, actual border pixels after reopening, Framework ranking, current cutoff/lag, and rejection of stale data/settings. Numerical baselines remain read-only. Windows QGIS 3.44.8 and 4.2.3 each pass 109 unit/contract checks; runtime evidence and exact scientific dependencies are recorded in [the Windows report](windows_qgis_4_2_report.json).

A separate comparison reads the local published Git tag **v1.1** and extracts its original functions. Six MoM/REML fitting and CV comparisons, plus three optimized REML controller fits, match exactly. The evidence records the tag commit and source hashes; no expected values were regenerated.

These checks use synthetic datasets and an iface double; they do not certify every native monitor/DPI configuration or large dataset. This is an incremental development correction, with metadata still 1.2 and no published release.
