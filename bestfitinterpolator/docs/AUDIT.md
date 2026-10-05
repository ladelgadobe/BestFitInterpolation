# Initial audit — 2 October 2026

Base: `local_build_v1_2_20260902/bestfitinterpolator`. Historical extracted copies
are older. This development directory preserves the 1.2 copy for regression checks.

## Architecture and state

- `BestFitInterpolator.py` loads the Designer UI, owns Data/Deterministic/CV,
  project signal connections, selected layer/field/polygon widgets, and saved
  interpolation configurations. Every `run()` previously created a new dialog.
- `ok_dispatcher.py` selects MoM/REML using the existing sample thresholds;
  `ok_r_integration_MoM.py` and `_reml.py` own variogram arrays, fitted state,
  UI controls, canvases and validation. Both retain bound Qt slots.
- `machine_learning_tab.py` owns covariate layers, extracted training frames,
  fitted RF/SVM models and grid metadata. RK receives point/grid/raster services
  from the main plugin and stores RF residuals, residual variogram, and CV state.
- `framework_tab.py` has `FrameworkDataState`, decision logic, model validation,
  dispatch, figures and an HTML report. It reads Data and controller state.
- `variogram_utils.py`, `performance_policy.py`, `grid_utils.py`, numerical
  interpolation modules and `validation_policy.py` are reusable foundations.
- Shared data have multiple readers. Exclusions must use stable feature IDs at
  those readers, before deduplication, CV, covariate extraction and interpolation.
- Qt resources are generated with Qt5. Most imports use `qgis.PyQt`; QAction,
  unscoped enums, `exec_`, `print_`, printer configuration and old QGIS enum
  containers need feature-based adapters. The QtAgg fallback already exists.

## Bugs and risks

1. Main dialog replacement does not reset `ok_ctrl`: it still owns the previous
   dialog and canvases. Reopening can update an invisible/deleted window.
2. Dispatcher rebuilds on layer/field/mode changes but merely disables the old
   controller. Not every bound slot checks that flag; handlers and closures leak.
3. Experimental cutoff/lag changes only mirror UI state; cached arrays/validation
   remain usable and can describe a previous configuration.
4. Canvas attachment tests only for `None`, not deleted Qt objects or ownership.
5. Several lifecycle paths swallow exceptions, hiding the above failures.
6. Report preview omits figures that PDF includes, and PDF reads widgets directly.
7. Existing comparison is a top-level tab using loaded rasters and previews;
   Framework needs a validated-result registry and exact pixel differences.

Preserve numerical interpolation engines, thresholds, default profiles and CV
folds. OK ranks candidates by LCCC/RMSE/R²; RK ranks by RMSE/SSE. Share primitives
and expose named policies; do not replace one with the other.

## Baseline

Installed runtime: QGIS 3.44.8, Python 3.12, NumPy 2.4.2, SciPy 1.17.0.
`tools/run_qgis_checks.py` executed existing checks: 60 passed, three legacy
test-module load errors (old QtGui widget imports / relative imports).
No pytest is installed. The local runner executes zero-argument contract tests
and unittest suites without installing packages.

## Change surface and compatibility strategy

Main orchestration, dispatcher, both OK controllers, RK, ML readers and Framework
integration will change incrementally. New small modules hold compatibility,
theme/figure styling, diagnostics state/engine/UI, reusable map controls,
advanced semivariogram UI, raster comparison and report state/rendering.
QGIS 3.14/3.22/3.28/3.34 and 4.0 are unavailable locally: report static review
separately from executed 3.44.8 tests. Use QGIS wrappers, feature detection,
Python 3.7-compatible source and the existing mathematical policies.
