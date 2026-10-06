# Historical development evidence

This directory records development checks dated below. Current release information is in [the plugin README](../README.md) and [version 2.0 notes](../../docs/releases/2.0.md).

# Best Fit Interpolator update 2026-10-05

Incremental delivery based on the local 1.2 source. The base source is preserved
and this revision uses a distinct ZIP name. This build has not been published.

Plugin titles, buttons, context menus, report headings and Larger View names use plain text without decorative ellipses or dashes. Long graph names wrap instead of adding ellipses.

- Closing and reopening starts a clean session in Data with initial settings.
- Data → Outlier diagnostic: IQR/MAD/Z, Global Moran, Anselin LISA and explicit Keep/Exclude/Reset. Its clickable info explains the workflow, HL/LH/HH/LL/NS classes and main parameters briefly; full explanations belong in the manual.
- About shows a larger 144 px logo with aspect ratio preserved and sharp rendering on high DPI screens.
- Spatial graph corner gear → popup display settings with eight gradient palettes, range and map scale. Validation has fixed scientific colors and no palette control.
- Larger View preserves the current map and synchronizes display settings.
- IDW and TPS have discreet separate borders. RF interpolation runs only from Interpolation.
- RK retains RF and residual kriging side by side, with one Adjust semivariogram dialog and a visible Interpolate action.
- Framework → Comparison contains maps only, with every valid alternative available in the map selectors and exact A−B. Method metrics remain in Validation.
- Framework → Interpolation starts empty and shows only results executed from Framework. Standalone runs and comparison generation cannot replace it.
- Framework → Report has a navigable summary, validation, executed output and diagnostics, PDF options, and View HTML. HTML opens automatically in the browser from a temporary file, with embedded images, working section links, and Expand all / Collapse all. No download path is requested.

104 checks pass in QGIS 3.44.8 on Windows. Five clean session reopenings and IDW/TPS/OK/RF/SVM/RK integration pass. Comparison offers all six validated methods in its selectors. Every tab was reviewed in real Qt at 1000×700 and 800×600; Full Covariates also fits a small screen and retains editable scalar correlation and colorbar. Current multi-version results, exact runtimes, dependencies and limits are recorded in [QGIS compatibility report](QGIS_COMPATIBILITY_REPORT.md).

The repository has fast PR/push compatibility tests, a full manual/weekly/release matrix, official image discovery with immutable digests, a read-only QGIS 4 checker and a strict required gate. Plugin users do not need Docker. A single source serves Qt5 and Qt6.

The mathematical methods and existing selection/validation policies are retained for identical inputs. Explicit exclusions change model inputs. No source-layer features are deleted.

Read [the current UI revision report](UI_REVISION_REPORT.md), [the 24-point implementation report](IMPLEMENTATION_REPORT.md), [compatibility matrix and reproduction commands](COMPATIBILITY_MATRIX.md), [initial audit](AUDIT.md), and [change inventory](CHANGE_INVENTORY.md).

The archive root is `bestfitinterpolator/`. Use QGIS “Install from ZIP” in a test profile to review the development build. Plugin metadata remains version 1.2; its maximum QGIS version expresses eligibility, not tested compatibility. The package contains no binary dependency environments.

Source tests live in `bestfitinterpolator/test`; workspace runners are in `tools`. Numerical baseline checks require the preserved original source, or `BFI_BASELINE_ROOT` pointing to that source when reproducing elsewhere.
