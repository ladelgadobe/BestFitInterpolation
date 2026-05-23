# Best Fit Interpolator

Best Fit Interpolator is a QGIS plugin for selecting, validating, and running spatial interpolation methods for soil and environmental point datasets.

The plugin combines deterministic interpolation, geostatistical interpolation, machine learning methods, and a dynamic framework decision workflow based on dataset diagnostics.

## Main Features

- Point-layer and polygon-mask based interpolation workflow.
- Deterministic methods: IDW and Thin Plate Spline (TPS/Spline).
- Geostatistical methods: Ordinary Kriging (OK) with MoM and REML fitting support.
- Machine learning methods: Random Forest, SVM, RFE, and Regression Kriging workflows with covariates.
- Framework Decision tab with:
  - Univariate framework.
  - Full framework.
  - Dynamic vector decision tree rendered inside QGIS.
  - Active decision-path highlighting based on current dataset diagnostics.
- Spatial diagnostics including Moran's I p-value and SDI classification.
- Validation workflows including LOOCV, K-fold, LCCC, RMSE, MAE, R, and R2.
- PDF report export with selectable report sections and dynamic framework decision tree inclusion.

## Requirements

- QGIS 3.x.
- Python environment provided by QGIS.
- GDAL and PyQt as provided by QGIS.
- NumPy, SciPy, pandas, matplotlib, and scikit-learn.

This repository currently includes a bundled `_deps` directory used by the plugin to make the machine learning stack available in the QGIS Python environment on Windows.

## Installation

1. Download or clone this repository.
2. Copy the `bestfitinterpolator` folder into your QGIS plugins directory:

   ```text
   C:/Users/<USER>/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/
   ```

3. Restart QGIS.
4. Enable **Best Fit Interpolator** from the QGIS Plugin Manager.

## Development Notes

- Main plugin entry point: `BestFitInterpolator.py`.
- Main dialog UI: `BestFitInterpolator_dialog_base.ui`.
- Framework controller: `framework_tab.py`.
- Dynamic decision tree view: `framework_decision_tree_view.py`.
- Machine Learning tab controller: `machine_learning_tab.py`.
- Shared array shape helpers: `array_shape_utils.py`.

The dynamic framework decision tree is generated programmatically with PyQt/QGraphicsView. Static article images are not used for rendering the active framework visualization.

## Packaging

For QGIS plugin distribution, zip the plugin folder itself so the archive contains:

```text
bestfitinterpolator/
  __init__.py
  metadata.txt
  BestFitInterpolator.py
  ...
```

Do not zip only the files inside the folder; QGIS expects the top-level plugin directory to be present in the archive.

## Author

Laura Delgado Bejarano  
Lucas Rios do Amaral
Repository: <https://github.com/ladelgadobe/BestFitInterpolation>

## Reference
Delgado Bejarano, L., Loureiro Gonçalves Oliveira, A., Fiolo Pozzuto, J. V., Castañeda Sánchez, D., & Rios do Amaral, L. (2026). Performance of interpolation methods in digital soil mapping: the influence of data characteristics. Precision Agriculture, 27(1), 10. <https://link.springer.com/article/10.1007/s11119-025-10311-8>
