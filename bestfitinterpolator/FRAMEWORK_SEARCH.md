# Framework ML grid search (version 2.1)

Framework automatically selects RF, SVM and RK RF-trend hyperparameters with the restored V2.0 search routines, effective ranges and default budgets of the individual method windows. It samples a finite grid reproducibly (seed 20), up to the iteration limit. It works without visiting individual windows and ignores their Manual/Search choices.

In Framework > Validation, **ML grid search** opens the settings window. Each method has its own ranges, search folds and maximum sampled combinations. Restore Defaults changes the controls; Cancel discards edits. There is no exhaustive-search selector.

| Method | Grid defaults | Search folds | Maximum combinations |
| --- | --- | --- | --- |
| RF | ntree 200–1000, step 100; mtry 2–50, step 2; nodesize 1–20, step 1 | 3 | 10 |
| SVM | C 0.13–32, step 2; gamma 0.01–2, step 2; epsilon 0–0.5, step 0.1 (V2.0 range convention) | 3 | 12 |
| RK trend | ntree 200–800, step 100; mtry 1–50, step 2; nodesize 1–20, step 1 | 3 | 10 |

The individual RF/SVM/RK range readers and SVM candidate generator have been restored verbatim from the V2.0 source. Framework uses the same routines and effective defaults, including the V2.0 SVM two-decimal readers and exponent-based C/gamma grid construction. The report lists the actual evaluated values. RF/RK ranges use additive steps and effective mtry is bounded by the number of predictors. Prediction uses the original model.predict path; uncertainty is calculated separately.

Predictor sampling uses private file readers for each calculation, with the source and explicit NoData policies of the selected layers. It does not reuse the display providers of existing QGIS layers. The same reader is used for extraction, correlations, model training and prediction grids. Each raster is sampled in its own CRS, and counts and source paths are recorded. If less than half the eligible training observations or inside-polygon cells have complete predictors, the run stops with per-raster counts and paths rather than silently fitting a tiny subset or writing a small strip. This input-loss guard does not impute values or change selected predictors. Ordinary edge NoData remains excluded. Input coverage is frozen in the output metadata and report.

Standard RF/RK tuning minimizes search-CV MAE; SVM minimizes search-CV RMSE. The existing dense-data policy limits folds to 3 and combinations to 8 above 500 observations, and tunes on at most 2,000 observations. Massive-data RF complexity limits remain in place. Final fitting uses all eligible observations supplied to that interpolation run.

A completed standard Framework search can be reused during the same plugin session only when the actual complete-case training values, row order, target, feature order, coordinates, grid, folds and iteration limit match exactly. The selected parameters are reused; the final model is fitted again on all valid training rows. Changing any of those inputs triggers a fresh search. A different massive-validation subset cannot be reused for full-data tuning. Manual, failed and canceled searches never populate the cache. Grid resolution changes do not require another hyperparameter search.

Standard performance validation selects hyperparameters before evaluating its validation folds; its scores are not a nested estimate. The original Auto, LOOCV and K-Fold validation workflow is retained. Spatial block validation is deferred.

The report freezes the actual execution details: selection algorithm, combinations, effective values, folds, search score and criterion, population, seed and selected parameters. Reuse is explicitly identified, with zero additional search evaluations and the original search record. Changing settings after execution does not rewrite historical records.

Version 2.1 includes RF/RK uncertainty maps, offline languages and hidden Windows helpers.
