# Best Fit Interpolator

<p align="center">
  <img src="icon.png" alt="Best Fit Interpolator icon" width="140">
</p>

<p align="center">
  <strong>A QGIS plugin for selecting, validating, and applying the most suitable spatial interpolation method for environmental and soil data.</strong>
</p>

<p align="center">
  <a href="https://github.com/ladelgadobe/BestFitInterpolation/issues">Report an issue</a> |
  <a href="https://doi.org/10.1007/s11119-025-10311-8">Reference article</a> |
  <a href="mailto:ladelgadobe@unal.edu.co">Contact</a>
</p>

## Overview

Best Fit Interpolator is a QGIS plugin designed to support spatial interpolation workflows, especially in digital soil mapping and precision agriculture. It helps users inspect their data, compare interpolation methods, validate predictions, and generate interpolation maps from point samples and polygon boundaries.

The plugin combines deterministic, geostatistical, machine-learning, and hybrid approaches in a single workflow:

- Inverse Distance Weighting (IDW)
- Thin Plate Spline (TPS)
- Ordinary Kriging (OK)
- REML-assisted kriging
- Random Forest (RF)
- Support Vector Machine (SVM)
- Regression Kriging (RK)

## Main Features

- Data diagnostics for point samples, variables, polygon limits, sample size, and spatial pattern.
- Semivariogram preview and geostatistical tools for kriging workflows.
- Cross-validation with RMSE, RMSE %, MAE, Pearson r, R², and LCCC.
- Observed-vs-predicted plots for comparing model behavior.
- Framework-guided method selection inspired by the reference article.
- Interpolation map generation directly inside QGIS.
- PDF report support for framework validation outputs.

## Version 1.2 Local Evaluation

- Framework can prepare, validate, and run RF, SVM, and RK without first running their individual method pages.
- Framework observed-vs-predicted plots use shared axes across methods; RF/SVM previews use observed target-value limits to avoid misleading SVM-only autoscaling.
- Runtime profiles are classified as normal (up to 500 valid samples), dense (501 to 10,000), and massive/productivity-scale (above 10,000).
- Massive datasets above 10,000 valid samples use up to 10,000 spatially representative samples for Framework method-comparison validation; point maps use rasterized scatter or hexbin views so the display can use all points without creating thousands of interactive vector markers.
- Moran's I uses all valid samples, keeps k=8 and 199 permutations, and is optimized with spatial indexing plus exact-result caching instead of sample-based approximation.
- Productivity-scale datasets above 10,000 samples activate the massive profile: RF is capped at 300 trees with minimum leaf size 5, SVM uses a 128-component Nyström approximation, massive ML validation uses a reproducible hold-out split, semivariograms use fewer legible lags, and IDW/Moran/variogram stages avoid dense pairwise distance matrices.
- RF/SVM final interpolation writes GeoTIFF rasters in row blocks with tiled/BigTIFF output and switches the in-plugin map preview to sampled or hexbin drawing for large grids, so a completed model fit does not have to allocate a full display raster in memory.
- Data and Framework diagnostics stop early with a CRS alert when point and polygon layers do not share the same CRS.
- Dense-method choices are disclosed to the user and written to raster metadata where applicable.

## Version 1.1

- Keeps the Framework semivariogram preview synchronized with Geostatistics.
- Blocks interpolation for incompatible CRS or missing spatial overlap.
- Presents warnings and errors as popup alerts without interrupting routine information messages.
- Fixes TPS routing and REML prediction errors.
- Standardizes R² labels and automatic cross-validation guidance.
- Adds an About tab with documentation, support, article, and author links.

## Framework Guidance

The Framework tab guides method selection using the data characteristics and the decision structure proposed in the reference article.

<p align="center">
  <img src="framework_univariate.png" alt="Univariate interpolation framework" width="720">
</p>

<p align="center">
  <img src="framework_full.png" alt="Full interpolation framework with covariates" width="720">
</p>

## Installation

### From the QGIS Plugin Repository

1. Open **Plugins > Manage and Install Plugins** in QGIS.
2. Search for **Best Fit Interpolator**.
3. Select the plugin and click **Install Plugin**.

### From a ZIP release

1. Download the plugin ZIP from the [latest GitHub release](https://github.com/ladelgadobe/BestFitInterpolation/releases/latest).
2. In QGIS, open **Plugins > Manage and Install Plugins > Install from ZIP**.
3. Select the downloaded ZIP and click **Install Plugin**.

Machine-learning and hybrid methods require additional Python packages. If they
are not already available, the plugin asks for permission to install them into
its local `_deps` directory the first time one of these methods is used. This
step requires an internet connection but does not require administrator access.

Developers can also clone this repository and copy the `bestfitinterpolator`
folder into their QGIS plugins directory.

Typical QGIS plugin directory on Windows:

```text
C:\Users\<user>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

## Authors

- [Laura Delgado Bejarano](https://www.linkedin.com/in/laura-delgado-bejarano-09b6681a2/)
- [Lucas Rios do Amaral](https://www.linkedin.com/in/lucas-rios-do-amaral-bb302449/)

Contact: [ladelgadobe@unal.edu.co](mailto:ladelgadobe@unal.edu.co)

## Citation

Laura Delgado Bejarano, Agda Loureiro Gonçalves Oliveira, João Vitor Fiolo Pozzuto, Dario Castañeda Sánchez, and Lucas Rios do Amaral (2026). *Performance of interpolation methods in digital soil mapping: the influence of data characteristics*. Precision Agriculture, 27, Article 10. https://doi.org/10.1007/s11119-025-10311-8

## Repository

- Homepage: https://github.com/ladelgadobe/BestFitInterpolation
- Issues: https://github.com/ladelgadobe/BestFitInterpolation/issues


## Development delivery — 2026-10-03

This incremental development ZIP adds Spatial Data Diagnostics, shared advanced semivariogram settings, Framework Map Comparison and a paginated Report Builder. Verified in QGIS 3.44.8; other versions remain untested. See [implementation report](docs/IMPLEMENTATION_REPORT.md) and [compatibility matrix](docs/COMPATIBILITY_MATRIX.md). Metadata remains 1.2; this is not a published release.


## Interface refinement — 2026-10-03

Clean session reset on reopening; Data → Outlier diagnostic; gradient palettes in popup settings; synchronized Larger View; compact RK controls; evaluated-method Comparison; explicit executed-method provenance. See [UI revision report](docs/UI_REVISION_REPORT.md).


## Interface feedback — 2026-10-03

Validation has no palette controls. IDW/TPS have separate subtle borders. RF runs only from Interpolation; RK panels stay side by side with a shared Adjust semivariogram dialog. Framework starts empty and isolates standalone results. Compare maps retains full grid extents. Report includes a navigable session summary and portable HTML export with embedded images.


## Compatibility and report preview — 2026-10-05

The current build opens HTML reports as temporary browser previews with working navigation and collapsible sections. Framework Comparison contains maps only; method metrics remain in Validation. QGIS 3.14, 3.16, 3.22, 3.28, 3.34, 3.40, 3.44, 4.0 and 4.2 passed the functional matrix. Exact runtimes, scientific dependencies and limitations are in [the measured compatibility report](docs/QGIS_COMPATIBILITY_REPORT.md). Earlier dated delivery paragraphs describe historical states. Plugin users do not need Docker. The repository has fast/full CI and a required compatibility gate. Metadata remains 1.2; no release is published.
