# Compatibility audit before implementation

Audit date: 2026-10-05. Current source: development_20261002/bestfitinterpolator. Clean Git checkout: github_sync_BestFitInterpolation, origin https://github.com/ladelgadobe/BestFitInterpolation.git. The checkout predates the recent interface work; the verified development source will be brought into that same plugin directory. No second QGIS-specific codebase is planned.

## Current compatibility risks

- Metadata currently declares minimum 3.14 and maximum 4.99, with version 1.2. These are existing declarations, not evidence of tested compatibility. Only local QGIS 3.44.8 / Qt 5.15.13 / Python 3.12.13 has recorded execution (100 checks plus the offscreen integration session).
- There is no GitHub Actions workflow in the local checkout. The current runner assumes a Windows QGIS installation and a workspace-specific baseline directory. It cannot serve as a portable multi-version runner without changes.
- Existing tests mix AST/text contracts, mathematical checks, unittest cases and real Qt/QGIS widgets. Historical baseline checks depend on a separate local source copy. Portable CI needs small committed numerical fixtures and independent assertions.
- Controller lifecycle and Matplotlib figure disposal are critical: initialization can catch exceptions, so tests must assert controller presence and collect Qt callback errors instead of accepting a successful top-level import.

## Potential QGIS 3.x problems

- The plugin uses QgsApplication/QgsTask, memory and raster layers, project signals, geometry types, CRS units and Qt widgets. Existing compat.py uses feature detection for geometry and unit aliases. These paths need actual runtime checks on the oldest image.
- Provider availability and GDAL/PROJ versions vary. Runtime tests must construct point/polygon layers and a small GeoTIFF, check validity and use isolated profiles.
- Old Docker images and their package repositories may be unavailable. The requested and actual QGIS major/minor must match before tests; substitution cannot count as execution.

## Potential QGIS 4.x problems

- qgis.PyQt imports and a small compatibility module are already used. QAction placement, scoped enums, exec/exec_, QTextDocument printing and deleted-object handling are adapted, but this does not prove Qt6 compatibility.
- QVariant assumptions, remaining legacy Qt references, Matplotlib Qt backend fallback and runtime-loaded Designer XML require checker and Qt6 execution. The QGIS 4 checker must run in dry-run mode and its findings need explicit review.
- Minimum and maximum actually tested remain 3.44.8. Do not expand metadata based on static analysis or a green import-only job.

## Qt5/Qt6 risks

- Widget creation, overloaded signals, print preview, persistent temporary HTML lifetime and repeated open/close must be exercised. QTextBrowser does not provide browser-native details/summary or JavaScript, so interactive HTML must open in a real browser; native overview links need correct dispatch.
- mpl_compat.py chooses QtAgg with older Qt5Agg fallback. CI must instantiate FigureCanvas and draw a figure, not just import matplotlib.

## Python-version risks

- Top-level production modules previously parsed with the Python 3.7 grammar. Dataclasses and postponed annotations require at least Python 3.7. Runtime annotations and library calls still need checks, not only grammar parsing.
- The new runner and fixture code must avoid modern union/builtin generic annotations, match/case, pathlib missing_ok and platform-specific DLL setup in Linux paths. CI orchestration can use a modern Python while container code must retain the older syntax.

## Dependency risks

- Scientific dependencies: NumPy, SciPy, pandas, scikit-learn, joblib/threadpoolctl, Matplotlib and GDAL. Optional R/rpy2 bridges need an explicit coverage limitation when unavailable; the ordinary and residual kriging paths must still execute.
- NumPy default_rng requires >=1.17. The plugin's version-aware ML bootstrap already has different Python bounds; system packages in historical images may predate those requirements.
- Cross-version fixtures must use documented tolerances rather than binary floating-point equality, preserve seeds and distinguish a numerical difference from an import/API/dependency error.
- CI must report QGIS, Qt, Python, GDAL, PROJ and scientific package versions before calculations and retain logs on failure.

## Implementation decision

Create a generic headless runner and numerical baseline in the currently working 3.44 runtime first. Resolve official Docker tags dynamically, record image digests and verify the actual QGIS version. Fast targets: 3.14, 3.44, 4.0 and latest stable 4.x. Full targets add 3.16, 3.22, 3.28, 3.34, 3.40 and 4.2; deduplicate latest stable when it aliases 4.2. Missing environments are explicitly recorded as STATICALLY_CHECKED or UNAVAILABLE; required-target gaps cannot produce a successful gate. Historical compilation is an opt-in fallback from an official pinned source, never an automatic expensive PR build.

Sources checked: [official QGIS Docker repository](https://github.com/qgis/qgis-docker), [official checker](https://github.com/qgis/pyqgis4-checker), [QGIS roadmap](https://www.qgis.org/resources/roadmap/). Current published roadmap lists stable 4.2.3. A future run must rediscover rather than assume that version.
