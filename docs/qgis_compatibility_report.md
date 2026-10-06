# Compatibility audit and delivery

Date: 2026-10-05. [Full execution evidence](https://github.com/ladelgadobe/BestFitInterpolation/actions/runs/37340079859).

Current minimum actually tested: **QGIS 3.14.15**. Current maximum actually tested: **QGIS 4.2.3**. Windows also passed QGIS 3.44.8. The nine Linux targets each passed all 13 functional blocks; every numerical fixture matched the preserved pre-change baseline.

The [pre-change audit](qgis_compatibility_audit.md) preceded implementation. The Git checkout previously contained an older 1.1 source, so this branch also brings in the already verified local 1.2 interface. One plugin source serves all tested versions.

## Windows QGIS 4.2 correction

The initial Linux matrix below predates this correction. It used Matplotlib 3.10.1 for QGIS 4.x and did not establish compatibility with the newer Windows distribution.

Windows QGIS 4.2.3 was reproduced using Qt 6.11.0, Python 3.12.14, Matplotlib 3.11.2, NumPy 2.4.6, SciPy 1.18.1 and scikit-learn 1.9.1. The original build failed Framework initialization and embedded drawing because Matplotlib removed `cm.get_cmap`.

The palette adapter now uses the public registry where available and retains the historical lookup for old Matplotlib. Palette previews are resolved before a parented Qt widget is constructed, avoiding orphan controls after errors. Information-button guards belong to each dialog, so reopening recreates them. All controllers retain a readable 120×160 minimum canvas size; pages scroll internally rather than crushing the semivariogram on a small viewport.

The corrected Windows 4.2.3 and 3.44.8 distributions each passed 107 checks, all 13 functional blocks, numerical baselines and full IDW/TPS/OK/RF/SVM/RK sessions. Actual Qt preview pixels were checked after optimized IDW, Larger View and repeated tab switches at 1000×700 and 800×600. Source hashes bind the Windows evidence to the correction. These API-removal and pixel checks also run in every CI target. [Windows reproduction and correction evidence](windows_qgis_4_2_report.json) records the failure, dependencies, successful results, full session and screenshot hashes.

The original Linux table and measurements below remain a historical record. Current expanded CI results are published as workflow artifacts and linked from draft PR #3. Offscreen tests use real QGIS/Qt widgets with synthetic data and a small iface double; they do not certify every desktop, monitor scale or large dataset.

## Semivariogram followup 2026-10-05

The current followup restores the published v1.1 distinction: REML displays its theoretical curve only; MoM displays the experimental observations and fitted model. Empty existing layouts are reused when changing controllers, so the embedded curve remains visible after successive fitting-method changes. Advanced validation uses the active fitting mode and optimized REML parameters. IDW/TPS replacement groups are bordered on every reopening and fit in two readable rows.

Framework semivariogram settings now validate Spherical, Exponential and Gaussian using the current data, cutoff, lag and fit. Metrics, the existing R²/RMSE ranking, and manual application are visible. Changed data/settings invalidate the results. Windows QGIS 3.44.8 and 4.2.3 each pass 109 checks and all 13 expanded functional blocks, including real pixels after six strategy switches and reopened method groups. Nine numerical comparisons with published v1.1 are exact. See [the semivariogram correction](semivariogram_revision_20261005.md) and the updated Windows JSON evidence. The earlier measurements below remain historical.

## Native integer and intermediate-version followup 2026-10-06

QGIS 3.14.0 was reproduced in its actual Windows 32-bit interpreter. Native NumPy bin indices correct the shared geostatistics, residual RK and Framework failure; wide counters and pair ordinals remain int64. Both NumPy 1.18.3 (original runtime) and 1.21.6 (existing ML package stack) were exercised. ML dependency loading now separates Python/platform ABIs and prefers the current interpreter's working stack, avoiding WinError 193 when 3.14 and 3.44 share QGIS3's profile. Legacy packages are preserved.

Windows 3.14.0, 3.44.8 and 4.2.3 each passed 114 contracts, all 13 functional blocks including RF manual/grid residual fitting, and the complete interpolation/comparison/report session. The expanded full CI passed all 18 stable targets: every stable minor from 3.14 through 3.44 and QGIS 4.0/4.2. New released stable 4.x minors enter the matrix automatically; weekly nightly remains informational. Every stable full-matrix target is required. The schedule changes are in draft PR 3 and use GitHub's default branch after integration. See [the correction and CI links](integer_compatibility_20261006.md) and [measured Windows/CI evidence](integer_compatibility_20261006.json). Older tables below remain historical.

## Interface delivered

- View HTML opens an automatically generated temporary file in the browser without asking for a save path. Each preview is immutable; temporary files are removed with the owning report UI. Images are embedded.
- Navigation opens the corresponding collapsed section. Individual summaries, Expand all and Collapse all work. Unknown workflow links are disabled rather than sent to nonexistent destinations.
- Framework Comparison contains maps only. Both selectors include every valid method; metrics and method results remain in Validation.
- A real headless Edge browser verified links, individual closing, expanding and collapsing. The native Qt overview also dispatched its workflow links correctly.

## Versions

| Requested | Actual | Status | Functional blocks | Qt | Python |
|---|---|---|---|---|---|
| 3.14 | 3.14.15-Pi | EXECUTED | 13/13 | 5.12.8 | 3.8.2 |
| 3.16 | 3.16.16-Hannover | EXECUTED | 13/13 | 5.12.8 | 3.8.10 |
| 3.22 | 3.22.16-Białowieża | EXECUTED | 13/13 | 5.12.8 | 3.8.10 |
| 3.28 | 3.28.15-Firenze | EXECUTED | 13/13 | 5.15.3 | 3.10.12 |
| 3.34 | 3.34.15-Prizren | EXECUTED | 13/13 | 5.15.13 | 3.12.3 |
| 3.40 | 3.40.15-Bratislava | EXECUTED | 13/13 | 5.15.13 | 3.12.3 |
| 3.44 | 3.44.15-Solothurn | EXECUTED | 13/13 | 5.15.13 | 3.12.3 |
| 4.0 | 4.0.3-Norrköping | EXECUTED | 13/13 | 6.9.2 | 3.13.7 |
| 4.2 and current stable 4.x | 4.2.3-Belém do Pará | EXECUTED | 13/13 | 6.9.2 | 3.13.7 |

Versions actually executed successfully: 3.14, 3.16, 3.22, 3.28, 3.34, 3.40, 3.44, 4.0 and 4.2. Versions only statically checked: **none of the requested stable targets**. Nightly is optional and was not executed.

## Static analysis and fixes

- 274 import records; 41 dependency/API review findings; zero Python 3.7 grammar errors. Grammar parsing does not run Python 3.7 and does not verify runtime annotations.
- Qt5: retained feature-detected legacy enums and Matplotlib Qt5Agg fallback. Historical Matplotlib figure transforms reject deepcopy; cloning our own in-memory figure uses a serialization fallback while preserving masks, colors, ranges and independent artists.
- Qt6: adapted QFont.Weight.Bold and replaced four boolean window modality arguments with Qt.WindowModality.WindowModal. The official QGIS 4 checker completed read-only with zero migration findings and unchanged source hashes.
- PyQGIS: exercised real application, layers, map canvas, task/signal lifecycle and geometry/unit adapters. QAction disposal prevents accumulation across initGui/unload cycles.
- Python/dependencies: the selected official 3.14 Focal image uses Python 3.8. The older Bionic variant (Python 3.6 / NumPy 1.13) failed and is not supported. Existing plugin requirements include Python >=3.7 and NumPy >=1.17; dependency versions are reported separately for every target.
- Removed an obsolete Python 2 alias initializer in plugin_upload.py that otherwise raised NameError during production import coverage.
- Image discovery now recognizes archived distribution suffixes with underscores. All targets use exact requested major/minor and recorded immutable official image digests; no other QGIS version substitutes for a missing environment.
- Docker output is finalized atomically by the host to handle root-owned evidence. Assertions are enabled by unsetting PYTHONOPTIMIZE. The final gate checks prerequisite job results in addition to evidence, so orchestration errors cannot create a green gate.

## CI workflows and tests created

- `.github/workflows/qgis-compatibility.yml`: fast push/PR matrix (3.14, 3.44, 4.0, latest stable 4.x); full manual, weekly and published-release matrix. Optional nightly is informational. Stable duplicate targets retain aliases and run once.
- Shared local/CI Docker runner; official image discovery; cached scientific layers; runtime identity and Qt6 guard; source mounted read-only and runtime networking disabled.
- Required compatibility gate for minimum supported QGIS, latest 3.x, oldest supported 4.x and current stable 4.x. Secondary historical failures are reported faithfully and may initially be informative. Unexpected prerequisite infrastructure failures fail the gate.
- Main branch protection requires the GitHub Actions compatibility-gate check, strict updates and administrator enforcement. No additional human approval rule was added.
- Six no-QGIS CI policy tests cover missing images/artifacts, static status, failure preservation and archived Focal tag resolution.
- Thirteen functional blocks: imports, classFactory, initGui/unload signals, main window/tabs/Matplotlib, Data with missing values, numerical baseline, semivariogram/ordinary kriging/CV, spatial diagnostics, RF/residual kriging/CV, Framework validation/winner/output, aligned map comparison/NoData, HTML/report/PDF, repeated opening/closing.
- 104 existing and added checks passed locally in QGIS 3.44.8. The historical figure clone regression verifies preserved content and independent styling. The full Windows UI session exercised IDW/TPS/OK/RF/SVM/RK, real covariates, five fresh sessions, small-window layouts, PDFs and provenance.

## Mathematical regression

**Did compatibility work change mathematical behavior? NO.** Numerical equations, seeds, metrics, interpolation parameters and selection policies were retained. Local checks compare original 1.2 numerical function ASTs and calculations. The committed fixture was captured before compatibility changes and was never regenerated to make CI pass.

Across every tested target, maximum absolute fixture difference was **4.88498130835e-15**. Relative tolerance is 1e-5; absolute tolerance is 1e-7. LISA classes matched exactly. The JSON and detailed measured report below retain every calculation and environment.

## Known limitations and metadata recommendation

- Results apply to the exact recorded Windows/Linux runtimes and scientific dependencies. They do not certify every patch, operating system or Python distribution within the metadata range.
- Functional UI tests use real QgsApplication/Qt widgets with a small iface double. They do not replace complete interactive desktop visual review in every QGIS version.
- External R/rpy2 integration, every optional ML model, very large dataset performance, cancellation at every possible stage and all real monitor DPI combinations are outside this portable matrix. The local integration session additionally exercises SVM and the preserved numerical checks exercise REML.
- Some harmless offscreen, layout, GDAL and Matplotlib deprecation warnings remain and are listed in evidence. No critical Qt callback or plugin error was ignored.
- Nightly and hypothetical later stable 4.x versions have no execution claim. Missing environments become STATICALLY_CHECKED or UNAVAILABLE; required gaps block the gate.
- Recommended qgisMinimumVersion: **3.14**, with Python >=3.7 and suitable scientific dependencies. Recommended qgisMaximumVersion: **4.99** as plugin repository eligibility for the 4.x family, monitored by dynamic latest-stable tests; the maximum actually executed is 4.2.3. Both metadata values were already present and remain unchanged. No supportsQt6 shortcut or compatibility badge is used.
- The workflow and development source are in draft PR #3. No merge or published release was performed. Scheduled runs and default-branch manual availability take effect after the workflow is merged to main.

## Files created

- `.dockerignore`
- `.github/workflows/qgis-compatibility.yml`
- `bestfitinterpolator/async_jobs.py`
- `bestfitinterpolator/compat.py`
- `bestfitinterpolator/diagnostics_engine.py`
- `bestfitinterpolator/diagnostics_plot.py`
- `bestfitinterpolator/diagnostics_table.py`
- `bestfitinterpolator/diagnostics_ui.py`
- `bestfitinterpolator/docs/AUDIT.md`
- `bestfitinterpolator/docs/CHANGE_INVENTORY.md`
- `bestfitinterpolator/docs/COMPATIBILITY_MATRIX.md`
- `bestfitinterpolator/docs/IMPLEMENTATION_REPORT.md`
- `bestfitinterpolator/docs/README.md`
- `bestfitinterpolator/docs/UI_REVISION_REPORT.md`
- `bestfitinterpolator/grid_utils.py`
- `bestfitinterpolator/interpolation_result.py`
- `bestfitinterpolator/larger_view.py`
- `bestfitinterpolator/map_comparison.py`
- `bestfitinterpolator/map_comparison_ui.py`
- `bestfitinterpolator/map_controls.py`
- `bestfitinterpolator/mpl_compat.py`
- `bestfitinterpolator/performance_policy.py`
- `bestfitinterpolator/report_builder.py`
- `bestfitinterpolator/report_model.py`
- `bestfitinterpolator/semivariogram_dialog.py`
- `bestfitinterpolator/semivariogram_engine.py`
- `bestfitinterpolator/spatial_diagnostics.py`
- `bestfitinterpolator/test/benchmark_dense_v12.py`
- `bestfitinterpolator/test/test_dense_processing_v12_contract.py`
- `bestfitinterpolator/test/test_development_diagnostics.py`
- `bestfitinterpolator/test/test_development_maps_reports.py`
- `bestfitinterpolator/test/test_development_numerical_baseline.py`
- `bestfitinterpolator/test/test_development_tasks.py`
- `bestfitinterpolator/test/test_development_ui_refinement.py`
- `bestfitinterpolator/test/test_figure_clone_compatibility.py`
- `bestfitinterpolator/test/test_release_1_2_contract.py`
- `bestfitinterpolator/test/test_version_1_2_foundation_contract.py`
- `bestfitinterpolator/theme.py`
- `bestfitinterpolator/ui_arrow_down.svg`
- `bestfitinterpolator/ui_arrow_up.svg`
- `bestfitinterpolator/ui_refinement.py`
- `bestfitinterpolator/variogram_utils.py`
- `ci/checker_reviews.json`
- `ci/qgis_targets.json`
- `ci/resolve_images.py`
- `ci/review_checker.py`
- `ci/run_qgis4_checker.py`
- `ci/static_check.py`
- `ci/summarize.py`
- `docker/compatibility.Dockerfile`
- `docs/qgis_compatibility.md`
- `docs/qgis_compatibility_audit.md`
- `docs/qgis_compatibility_report.json`
- `docs/qgis_compatibility_report.md`
- `scripts/capture_numerical_baseline.py`
- `scripts/run_qgis_tests.py`
- `scripts/test_qgis_version.py`
- `scripts/test_qgis_version.sh`
- `tests/compatibility/numerical.py`
- `tests/compatibility/runtime_cases.py`
- `tests/compatibility/test_ci_policy.py`
- `tests/data/numerical_baseline.json`

## Files modified relative to the older Git source

- `.gitignore`
- `README.md`
- `bestfitinterpolator/BestFitInterpolator.py`
- `bestfitinterpolator/BestFitInterpolator_dialog_base.ui`
- `bestfitinterpolator/IDW_optimized.py`
- `bestfitinterpolator/README.html`
- `bestfitinterpolator/README.md`
- `bestfitinterpolator/README.txt`
- `bestfitinterpolator/RF_Interpolation.py`
- `bestfitinterpolator/RF_RegressionKriging.py`
- `bestfitinterpolator/SVM_Interpolation.py`
- `bestfitinterpolator/Thin_plate_spline.py`
- `bestfitinterpolator/framework_decision_tree_view.py`
- `bestfitinterpolator/framework_sdi_dialog.py`
- `bestfitinterpolator/framework_tab.py`
- `bestfitinterpolator/kriging_ordinary.py`
- `bestfitinterpolator/kriging_reml.py`
- `bestfitinterpolator/machine_learning_tab.py`
- `bestfitinterpolator/metadata.txt`
- `bestfitinterpolator/ml_bootstrap.py`
- `bestfitinterpolator/notifications.py`
- `bestfitinterpolator/ok_dispatcher.py`
- `bestfitinterpolator/ok_r_integration_MoM.py`
- `bestfitinterpolator/ok_r_integration_reml.py`
- `bestfitinterpolator/plugin_upload.py`
- `bestfitinterpolator/reml_bridge.py`
- `bestfitinterpolator/test/smoke_qgis_release.py`
- `bestfitinterpolator/test/test_BestFitInterpolator_dialog.py`
- `bestfitinterpolator/test/test_about_tab_contract.py`
- `bestfitinterpolator/test/test_popup_notifications_contract.py`
- `bestfitinterpolator/test/test_qgis_environment.py`
- `bestfitinterpolator/test/test_release_1_1_contract.py`
- `bestfitinterpolator/test/test_translations.py`
- `bestfitinterpolator/test/test_validation_configuration_contract.py`
- `bestfitinterpolator/test/test_validation_presentation_contract.py`
- `bestfitinterpolator/test/test_visible_text_encoding.py`
- `bestfitinterpolator/validation_policy.py`

## Detailed runtime evidence

# Best Fit Interpolator Compatibility

| Requested QGIS | Actual QGIS | Verification | Tests | Required |
|---|---|---|---|---|
| 3.14 | 3.14.15-Pi | EXECUTED | 13/13 | True |
| 3.16 | 3.16.16-Hannover | EXECUTED | 13/13 | False |
| 3.22 | 3.22.16-Białowieża | EXECUTED | 13/13 | False |
| 3.28 | 3.28.15-Firenze | EXECUTED | 13/13 | False |
| 3.34 | 3.34.15-Prizren | EXECUTED | 13/13 | False |
| 3.40 | 3.40.15-Bratislava | EXECUTED | 13/13 | False |
| 3.44 | 3.44.15-Solothurn | EXECUTED | 13/13 | True |
| 4.0 | 4.0.3-Norrköping | EXECUTED | 13/13 | True |
| 4.2 (latest stable 4.x) | 4.2.3-Belém do Pará | EXECUTED | 13/13 | True |

## Numerical comparison against QGIS 3.44.8-Solothurn

Relative tolerance: 1e-05; absolute tolerance: 1e-07. Exact LISA class comparison. Expected values are never regenerated in CI.

| QGIS | Calculation | Maximum absolute difference |
|---|---|---|
| 3.14 | idw | 0 |
| 3.14 | tps | 4.4408921e-16 |
| 3.14 | lags | 0 |
| 3.14 | semivariance | 1.110223e-16 |
| 3.14 | metrics | 0 |
| 3.14 | fit_spherical | 2.7755576e-17 |
| 3.14 | model_spherical | 1.110223e-16 |
| 3.14 | kriging_spherical | 1.5543122e-15 |
| 3.14 | cv_spherical | 1.110223e-16 |
| 3.14 | fit_exponential | 2.7755576e-17 |
| 3.14 | model_exponential | 0 |
| 3.14 | kriging_exponential | 7.7715612e-16 |
| 3.14 | cv_exponential | 0 |
| 3.14 | fit_gaussian | 2.220446e-16 |
| 3.14 | model_gaussian | 1.110223e-16 |
| 3.14 | kriging_gaussian | 1.2212453e-15 |
| 3.14 | cv_gaussian | 1.110223e-16 |
| 3.14 | moran | 0 |
| 3.14 | local_moran | 4.4408921e-16 |
| 3.14 | lisa | same classes |
| 3.14 | statistical_votes | 0 |
| 3.14 | rk_residuals | 2.220446e-16 |
| 3.14 | rk_final | 8.8817842e-16 |
| 3.16 | idw | 0 |
| 3.16 | tps | 4.4408921e-16 |
| 3.16 | lags | 0 |
| 3.16 | semivariance | 1.110223e-16 |
| 3.16 | metrics | 0 |
| 3.16 | fit_spherical | 2.7755576e-17 |
| 3.16 | model_spherical | 1.110223e-16 |
| 3.16 | kriging_spherical | 1.5543122e-15 |
| 3.16 | cv_spherical | 1.110223e-16 |
| 3.16 | fit_exponential | 2.7755576e-17 |
| 3.16 | model_exponential | 0 |
| 3.16 | kriging_exponential | 7.7715612e-16 |
| 3.16 | cv_exponential | 0 |
| 3.16 | fit_gaussian | 2.220446e-16 |
| 3.16 | model_gaussian | 1.110223e-16 |
| 3.16 | kriging_gaussian | 1.2212453e-15 |
| 3.16 | cv_gaussian | 1.110223e-16 |
| 3.16 | moran | 0 |
| 3.16 | local_moran | 4.4408921e-16 |
| 3.16 | lisa | same classes |
| 3.16 | statistical_votes | 0 |
| 3.16 | rk_residuals | 2.220446e-16 |
| 3.16 | rk_final | 8.8817842e-16 |
| 3.22 | idw | 0 |
| 3.22 | tps | 4.4408921e-16 |
| 3.22 | lags | 0 |
| 3.22 | semivariance | 1.110223e-16 |
| 3.22 | metrics | 0 |
| 3.22 | fit_spherical | 2.7755576e-17 |
| 3.22 | model_spherical | 1.110223e-16 |
| 3.22 | kriging_spherical | 1.5543122e-15 |
| 3.22 | cv_spherical | 1.110223e-16 |
| 3.22 | fit_exponential | 2.7755576e-17 |
| 3.22 | model_exponential | 0 |
| 3.22 | kriging_exponential | 7.7715612e-16 |
| 3.22 | cv_exponential | 0 |
| 3.22 | fit_gaussian | 2.220446e-16 |
| 3.22 | model_gaussian | 1.110223e-16 |
| 3.22 | kriging_gaussian | 1.2212453e-15 |
| 3.22 | cv_gaussian | 1.110223e-16 |
| 3.22 | moran | 0 |
| 3.22 | local_moran | 4.4408921e-16 |
| 3.22 | lisa | same classes |
| 3.22 | statistical_votes | 0 |
| 3.22 | rk_residuals | 2.220446e-16 |
| 3.22 | rk_final | 8.8817842e-16 |
| 3.28 | idw | 0 |
| 3.28 | tps | 2.220446e-16 |
| 3.28 | lags | 0 |
| 3.28 | semivariance | 1.110223e-16 |
| 3.28 | metrics | 0 |
| 3.28 | fit_spherical | 2.7755576e-17 |
| 3.28 | model_spherical | 1.110223e-16 |
| 3.28 | kriging_spherical | 8.8817842e-16 |
| 3.28 | cv_spherical | 2.220446e-16 |
| 3.28 | fit_exponential | 2.7755576e-17 |
| 3.28 | model_exponential | 0 |
| 3.28 | kriging_exponential | 8.8817842e-16 |
| 3.28 | cv_exponential | 2.220446e-16 |
| 3.28 | fit_gaussian | 2.220446e-16 |
| 3.28 | model_gaussian | 1.110223e-16 |
| 3.28 | kriging_gaussian | 1.5543122e-15 |
| 3.28 | cv_gaussian | 2.220446e-16 |
| 3.28 | moran | 0 |
| 3.28 | local_moran | 4.4408921e-16 |
| 3.28 | lisa | same classes |
| 3.28 | statistical_votes | 0 |
| 3.28 | rk_residuals | 2.220446e-16 |
| 3.28 | rk_final | 4.8849813e-15 |
| 3.34 | idw | 0 |
| 3.34 | tps | 4.4408921e-16 |
| 3.34 | lags | 0 |
| 3.34 | semivariance | 1.110223e-16 |
| 3.34 | metrics | 0 |
| 3.34 | fit_spherical | 2.7755576e-17 |
| 3.34 | model_spherical | 1.110223e-16 |
| 3.34 | kriging_spherical | 1.3322676e-15 |
| 3.34 | cv_spherical | 1.110223e-16 |
| 3.34 | fit_exponential | 2.7755576e-17 |
| 3.34 | model_exponential | 0 |
| 3.34 | kriging_exponential | 7.7715612e-16 |
| 3.34 | cv_exponential | 2.220446e-16 |
| 3.34 | fit_gaussian | 2.220446e-16 |
| 3.34 | model_gaussian | 1.110223e-16 |
| 3.34 | kriging_gaussian | 8.8817842e-16 |
| 3.34 | cv_gaussian | 4.4408921e-16 |
| 3.34 | moran | 0 |
| 3.34 | local_moran | 4.4408921e-16 |
| 3.34 | lisa | same classes |
| 3.34 | statistical_votes | 0 |
| 3.34 | rk_residuals | 2.220446e-16 |
| 3.34 | rk_final | 1.7763568e-15 |
| 3.40 | idw | 0 |
| 3.40 | tps | 4.4408921e-16 |
| 3.40 | lags | 0 |
| 3.40 | semivariance | 1.110223e-16 |
| 3.40 | metrics | 0 |
| 3.40 | fit_spherical | 2.7755576e-17 |
| 3.40 | model_spherical | 1.110223e-16 |
| 3.40 | kriging_spherical | 1.3322676e-15 |
| 3.40 | cv_spherical | 1.110223e-16 |
| 3.40 | fit_exponential | 2.7755576e-17 |
| 3.40 | model_exponential | 0 |
| 3.40 | kriging_exponential | 4.4408921e-16 |
| 3.40 | cv_exponential | 3.3306691e-16 |
| 3.40 | fit_gaussian | 2.220446e-16 |
| 3.40 | model_gaussian | 1.110223e-16 |
| 3.40 | kriging_gaussian | 8.8817842e-16 |
| 3.40 | cv_gaussian | 3.3306691e-16 |
| 3.40 | moran | 0 |
| 3.40 | local_moran | 4.4408921e-16 |
| 3.40 | lisa | same classes |
| 3.40 | statistical_votes | 0 |
| 3.40 | rk_residuals | 2.220446e-16 |
| 3.40 | rk_final | 1.7763568e-15 |
| 3.44 | idw | 0 |
| 3.44 | tps | 4.4408921e-16 |
| 3.44 | lags | 0 |
| 3.44 | semivariance | 1.110223e-16 |
| 3.44 | metrics | 0 |
| 3.44 | fit_spherical | 2.7755576e-17 |
| 3.44 | model_spherical | 1.110223e-16 |
| 3.44 | kriging_spherical | 1.3322676e-15 |
| 3.44 | cv_spherical | 1.110223e-16 |
| 3.44 | fit_exponential | 2.7755576e-17 |
| 3.44 | model_exponential | 0 |
| 3.44 | kriging_exponential | 4.4408921e-16 |
| 3.44 | cv_exponential | 3.3306691e-16 |
| 3.44 | fit_gaussian | 2.220446e-16 |
| 3.44 | model_gaussian | 1.110223e-16 |
| 3.44 | kriging_gaussian | 8.8817842e-16 |
| 3.44 | cv_gaussian | 3.3306691e-16 |
| 3.44 | moran | 0 |
| 3.44 | local_moran | 4.4408921e-16 |
| 3.44 | lisa | same classes |
| 3.44 | statistical_votes | 0 |
| 3.44 | rk_residuals | 2.220446e-16 |
| 3.44 | rk_final | 1.7763568e-15 |
| 4.0 | idw | 0 |
| 4.0 | tps | 2.220446e-16 |
| 4.0 | lags | 0 |
| 4.0 | semivariance | 1.110223e-16 |
| 4.0 | metrics | 0 |
| 4.0 | fit_spherical | 2.7755576e-17 |
| 4.0 | model_spherical | 1.110223e-16 |
| 4.0 | kriging_spherical | 1.3322676e-15 |
| 4.0 | cv_spherical | 1.110223e-16 |
| 4.0 | fit_exponential | 2.7755576e-17 |
| 4.0 | model_exponential | 0 |
| 4.0 | kriging_exponential | 3.3306691e-16 |
| 4.0 | cv_exponential | 2.220446e-16 |
| 4.0 | fit_gaussian | 2.220446e-16 |
| 4.0 | model_gaussian | 1.110223e-16 |
| 4.0 | kriging_gaussian | 4.4408921e-16 |
| 4.0 | cv_gaussian | 3.3306691e-16 |
| 4.0 | moran | 0 |
| 4.0 | local_moran | 4.4408921e-16 |
| 4.0 | lisa | same classes |
| 4.0 | statistical_votes | 0 |
| 4.0 | rk_residuals | 2.220446e-16 |
| 4.0 | rk_final | 1.7763568e-15 |
| 4.2 | idw | 0 |
| 4.2 | tps | 2.220446e-16 |
| 4.2 | lags | 0 |
| 4.2 | semivariance | 1.110223e-16 |
| 4.2 | metrics | 0 |
| 4.2 | fit_spherical | 2.7755576e-17 |
| 4.2 | model_spherical | 1.110223e-16 |
| 4.2 | kriging_spherical | 1.3322676e-15 |
| 4.2 | cv_spherical | 1.110223e-16 |
| 4.2 | fit_exponential | 2.7755576e-17 |
| 4.2 | model_exponential | 0 |
| 4.2 | kriging_exponential | 3.3306691e-16 |
| 4.2 | cv_exponential | 2.220446e-16 |
| 4.2 | fit_gaussian | 2.220446e-16 |
| 4.2 | model_gaussian | 1.110223e-16 |
| 4.2 | kriging_gaussian | 4.4408921e-16 |
| 4.2 | cv_gaussian | 3.3306691e-16 |
| 4.2 | moran | 0 |
| 4.2 | local_moran | 4.4408921e-16 |
| 4.2 | lisa | same classes |
| 4.2 | statistical_votes | 0 |
| 4.2 | rk_residuals | 2.220446e-16 |
| 4.2 | rk_final | 1.7763568e-15 |

## QGIS 3.14

Image: {'tag': 'qgis/qgis:final-3_14_15_focal', 'image': 'qgis/qgis@sha256:ce12d68788daababbcebccabe63fca5d2987eb1b78e3e1a93c671604ad321cba', 'digest': 'sha256:ce12d68788daababbcebccabe63fca5d2987eb1b78e3e1a93c671604ad321cba', 'origin': 'Archived official QGIS image'}

Environment: {'QGIS': '3.14.15-Pi', 'Qt': '5.12.8', 'Python': '3.8.2', 'GDAL': '3.0.4', 'PROJ': '6.3.1', 'NumPy': '1.17.4', 'SciPy': '1.3.3', 'scikit-learn': '0.22.2.post1', 'matplotlib': '3.1.2', 'pandas': '0.25.3'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations. 
- Warning: an integer is required (got type WindowFlags).  Implicit conversion to integers using __int__ is deprecated, and may be removed in a future version of Python.
- Warning: tight_layout : falling back to Agg renderer

## QGIS 3.16

Image: {'tag': 'qgis/qgis:release-3_16', 'image': 'qgis/qgis@sha256:e186075df76f8ea88c4d3ca1abf3364d0018b96d5b443429f829a26b48e948e4', 'digest': 'sha256:e186075df76f8ea88c4d3ca1abf3364d0018b96d5b443429f829a26b48e948e4', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '3.16.16-Hannover', 'Qt': '5.12.8', 'Python': '3.8.10', 'GDAL': '3.0.4', 'PROJ': '6.3.1', 'NumPy': '1.17.4', 'SciPy': '1.3.3', 'scikit-learn': '0.22.2.post1', 'matplotlib': '3.1.2', 'pandas': '0.25.3'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations. 
- Warning: an integer is required (got type WindowFlags).  Implicit conversion to integers using __int__ is deprecated, and may be removed in a future version of Python.
- Warning: tight_layout : falling back to Agg renderer

## QGIS 3.22

Image: {'tag': 'qgis/qgis:3.22.16-focal', 'image': 'qgis/qgis@sha256:7eb48f1af09cfbb10a8941767cb1e7615ba7480426e191605cce27d33a299263', 'digest': 'sha256:7eb48f1af09cfbb10a8941767cb1e7615ba7480426e191605cce27d33a299263', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '3.22.16-Białowieża', 'Qt': '5.12.8', 'Python': '3.8.10', 'GDAL': '3.0.4', 'PROJ': '6.3.1', 'NumPy': '1.17.4', 'SciPy': '1.3.3', 'scikit-learn': '0.22.2.post1', 'matplotlib': '3.1.2', 'pandas': '0.25.3'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations. 
- Warning: an integer is required (got type WindowFlags).  Implicit conversion to integers using __int__ is deprecated, and may be removed in a future version of Python.
- Warning: tight_layout : falling back to Agg renderer

## QGIS 3.28

Image: {'tag': 'qgis/qgis:final-3_28_15', 'image': 'qgis/qgis@sha256:ac32c27d2fa816f525e3ac264c1c5243454e6f857cb0cfd04345a4e9022fb85c', 'digest': 'sha256:ac32c27d2fa816f525e3ac264c1c5243454e6f857cb0cfd04345a4e9022fb85c', 'origin': 'Archived official QGIS image'}

Environment: {'QGIS': '3.28.15-Firenze', 'Qt': '5.15.3', 'Python': '3.10.12', 'GDAL': '3.4.1', 'PROJ': '8.2.1', 'NumPy': '1.21.5', 'SciPy': '1.8.0', 'scikit-learn': '0.23.2', 'matplotlib': '3.5.1', 'pandas': '1.3.5'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Please use `line_search_wolfe1` from the `scipy.optimize` namespace, the `scipy.optimize.linesearch` namespace is deprecated.
- Warning: Please use `line_search_wolfe2` from the `scipy.optimize` namespace, the `scipy.optimize.linesearch` namespace is deprecated.
- Warning: Please use `spmatrix` from the `scipy.sparse` namespace, the `scipy.sparse.base` namespace is deprecated.
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations.

## QGIS 3.34

Image: {'tag': 'qgis/qgis:3.34.15-noble', 'image': 'qgis/qgis@sha256:6cf6c4b6aa9874c2a3513d18788361fe16a1f947c57b06648e011c17711e0214', 'digest': 'sha256:6cf6c4b6aa9874c2a3513d18788361fe16a1f947c57b06648e011c17711e0214', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '3.34.15-Prizren', 'Qt': '5.15.13', 'Python': '3.12.3', 'GDAL': '3.8.4', 'PROJ': '9.4.0', 'NumPy': '1.26.4', 'SciPy': '1.11.4', 'scikit-learn': '1.4.1.post1', 'matplotlib': '3.6.3', 'pandas': '2.1.4'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Neither gdal.UseExceptions() nor gdal.DontUseExceptions() has been explicitly called. In GDAL 4.0, exceptions will be enabled by default.
- Warning: Pickle, copy, and deepcopy support will be removed from itertools in Python 3.14.
- Warning: The get_cmap function will be deprecated in a future version. Use ``matplotlib.colormaps[name]`` or ``matplotlib.colormaps.get_cmap(obj)`` instead.
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations.

## QGIS 3.40

Image: {'tag': 'qgis/qgis:3.40.15-noble', 'image': 'qgis/qgis@sha256:d664f1eca1ef4f615efd92b944c90896622bc75f0446357dc50c2e56b379ddd9', 'digest': 'sha256:d664f1eca1ef4f615efd92b944c90896622bc75f0446357dc50c2e56b379ddd9', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '3.40.15-Bratislava', 'Qt': '5.15.13', 'Python': '3.12.3', 'GDAL': '3.8.4', 'PROJ': '9.4.0', 'NumPy': '1.26.4', 'SciPy': '1.11.4', 'scikit-learn': '1.4.1.post1', 'matplotlib': '3.6.3', 'pandas': '2.1.4'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Neither gdal.UseExceptions() nor gdal.DontUseExceptions() has been explicitly called. In GDAL 4.0, exceptions will be enabled by default.
- Warning: Pickle, copy, and deepcopy support will be removed from itertools in Python 3.14.
- Warning: The get_cmap function will be deprecated in a future version. Use ``matplotlib.colormaps[name]`` or ``matplotlib.colormaps.get_cmap(obj)`` instead.
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations.

## QGIS 3.44

Image: {'tag': 'qgis/qgis:3.44.15-noble', 'image': 'qgis/qgis@sha256:497c1629c68ced7735dc25c25e33ada0040f5144099e92b78fae978bdf233466', 'digest': 'sha256:497c1629c68ced7735dc25c25e33ada0040f5144099e92b78fae978bdf233466', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '3.44.15-Solothurn', 'Qt': '5.15.13', 'Python': '3.12.3', 'GDAL': '3.8.4', 'PROJ': '9.4.0', 'NumPy': '1.26.4', 'SciPy': '1.11.4', 'scikit-learn': '1.4.1.post1', 'matplotlib': '3.6.3', 'pandas': '2.1.4'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Neither gdal.UseExceptions() nor gdal.DontUseExceptions() has been explicitly called. In GDAL 4.0, exceptions will be enabled by default.
- Warning: Pickle, copy, and deepcopy support will be removed from itertools in Python 3.14.
- Warning: The get_cmap function will be deprecated in a future version. Use ``matplotlib.colormaps[name]`` or ``matplotlib.colormaps.get_cmap(obj)`` instead.
- Warning: Tight layout not applied. The bottom and top margins cannot be made large enough to accommodate all axes decorations.

## QGIS 4.0

Image: {'tag': 'qgis/qgis:4.0.3-questing', 'image': 'qgis/qgis@sha256:7f3ee7c526eb8f5c71d670cc6bf2c640bc2d6fdf57a928749bb76239c942c90b', 'digest': 'sha256:7f3ee7c526eb8f5c71d670cc6bf2c640bc2d6fdf57a928749bb76239c942c90b', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '4.0.3-Norrköping', 'Qt': '6.9.2', 'Python': '3.13.7', 'GDAL': '3.10.3', 'PROJ': '9.6.0', 'NumPy': '2.2.4', 'SciPy': '1.15.3', 'scikit-learn': '1.4.2', 'matplotlib': '3.10.1+dfsg1', 'pandas': '2.2.3'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Neither gdal.UseExceptions() nor gdal.DontUseExceptions() has been explicitly called. In GDAL 4.0, exceptions will be enabled by default.
- Warning: The get_cmap function was deprecated in Matplotlib 3.7 and will be removed in 3.11. Use ``matplotlib.colormaps[name]`` or ``matplotlib.colormaps.get_cmap()`` or ``pyplot.get_cmap()`` instead.
- Warning: vert: bool will be deprecated in a future version. Use orientation: {'vertical', 'horizontal'} instead.

## QGIS 4.2

Image: {'tag': 'qgis/qgis:4.2.3-questing', 'image': 'qgis/qgis@sha256:8996496c15887a8fae0da05fa38103093ddbf104525bcbd67bf733a914fb1444', 'digest': 'sha256:8996496c15887a8fae0da05fa38103093ddbf104525bcbd67bf733a914fb1444', 'origin': 'Official QGIS Docker Hub'}

Environment: {'QGIS': '4.2.3-Belém do Pará', 'Qt': '6.9.2', 'Python': '3.13.7', 'GDAL': '3.10.3', 'PROJ': '9.6.0', 'NumPy': '2.2.4', 'SciPy': '1.15.3', 'scikit-learn': '1.4.2', 'matplotlib': '3.10.1+dfsg1', 'pandas': '2.2.3'}

- plugin_import: PASS 
- classFactory: PASS 
- initGui_unload_signals: PASS 
- main_window: PASS 
- data_loading: PASS 
- numerical_baseline: PASS 
- semivariogram_geostatistics: PASS 
- spatial_diagnostics: PASS 
- regression_kriging: PASS 
- framework: PASS 
- map_comparison: PASS 
- report: PASS 
- repeated_open_close: PASS 
- Warning: Neither gdal.UseExceptions() nor gdal.DontUseExceptions() has been explicitly called. In GDAL 4.0, exceptions will be enabled by default.
- Warning: The get_cmap function was deprecated in Matplotlib 3.7 and will be removed in 3.11. Use ``matplotlib.colormaps[name]`` or ``matplotlib.colormaps.get_cmap()`` or ``pyplot.get_cmap()`` instead.
- Warning: vert: bool will be deprecated in a future version. Use orientation: {'vertical', 'horizontal'} instead.

## Verified support

Actually executed: 3.14.15-Pi, 3.16.16-Hannover, 3.22.16-Białowieża, 3.28.15-Firenze, 3.34.15-Prizren, 3.40.15-Bratislava, 3.44.15-Solothurn, 4.0.3-Norrköping, 4.2.3-Belém do Pará
Metadata is not changed by this workflow. Static checks and unavailable runtimes do not justify expanding support.

