# QGIS compatibility verification

The workflow measures real plugin behavior. A declared metadata range and an import-only smoke test are insufficient evidence of support.

The pre-change [audit](qgis_compatibility_audit.md) records existing risks. The committed baseline was captured in QGIS 3.44.8 / Qt 5.15.13 / Python 3.12.13 before compatibility changes. It covers IDW, TPS, RMSE/MAE/R²/LCCC, experimental lags and semivariance, spherical/exponential/Gaussian fits, ordinary kriging/CV, Moran/LISA, statistical votes and regression kriging. Relative tolerance is 1e-5 and absolute tolerance 1e-7; LISA classes must match exactly. CI never rewrites expected results.

## Matrix and statuses

- Fast, every push and PR: 3.14, 3.44, 4.0, latest stable 4.x.
- Full, manual, weekly and on a published release: 3.14, 3.16, 3.22, 3.28, 3.34, 3.40, 3.44, 4.0, 4.2, latest stable 4.x.
- Latest stable is resolved from official QGIS release tags. Duplicate major/minor targets retain their aliases but run once. To add a future version, edit ci/qgis_targets.json.
- Required targets block the compatibility gate on any failure, missing artifact or missing environment. Historical intermediate targets initially provide informative results, including failures. The repository's main branch now requires `compatibility-gate` from the GitHub Actions app, with strict updates and administrator enforcement. A fork should configure its own branch protection separately.
- Optional nightly is deliberately outside the required set. Its runtime can be invoked with `--requested nightly` on an explicitly pinned official nightly image; it must never replace a stable target.

EXECUTED means the requested QGIS major/minor matched the runtime and every functional case passed. FAILED means runtime setup or plugin tests failed with diagnostic evidence. STATICALLY_CHECKED means import/API/Qt/Python/dependency inventory ran, but that target did not execute; no PASS is displayed. UNAVAILABLE means no usable environment/evidence could be produced. Infrastructure errors remain visible even when static fallback is available.

The local starting point was QGIS 3.44.8. The full matrix subsequently executed every requested stable target successfully. Read exact runtimes, dependencies and limits in the [measured report](qgis_compatibility_report.md); image discovery alone proves availability, not plugin compatibility. Existing metadata 3.14–4.99 is retained as repository eligibility. The maximum actually executed is 4.2.3; future stable versions must pass the dynamically discovered required target.

## Containers and provenance

ci/resolve_images.py checks Docker Hub's official `qgis/qgis` namespace, including archived final tags. It records the selected tag and immutable digest. The container runner checks actual QGIS before loading the plugin and prints QGIS, Qt, Python, GDAL, PROJ, NumPy, SciPy, scikit-learn, Matplotlib and pandas versions. QGIS 4 requires Qt6.

All requested stable versions had discoverable official images on 2026-10-05, including archived `final-3_14_15_focal`. Focal uses Python 3.8 and suitable scientific packages; the Bionic variant with Python 3.6 and NumPy 1.13 is incompatible with the existing plugin requirements. Distribution suffixes separated by underscores or hyphens are recognized. Consequently no historical QGIS source build was added. If an image disappears, discovery and the static fallback produce an explicit coverage gap. The next fallback should be a separately reviewed cached build from a pinned official QGIS release commit and its official Dockerfile; full QGIS compilation is never silently performed on each PR. Unknown binary mirrors are not accepted.

docker/compatibility.Dockerfile adds distribution scientific packages to the official interpreter. Package versions are reported by every test. Dependency build failures are retained as infrastructure gaps, not hidden by replacing QGIS. Docker layers are cached by base image digest and Dockerfile. Runtime containers have networking disabled, read-only source mounts and assertions enabled, so unexpected package bootstrap or source edits cannot create a misleading PASS.

## Coverage

The shared Python entry point exercises all production imports, classFactory, two initGui/unload cycles with real QAction signals, main and nested tabs, Matplotlib widgets, point/variable/missing-value extraction, deterministic calculations, experimental and fitted semivariograms, ordinary kriging/CV, RF regression and residual kriging, IQR/MAD and Moran/LISA, Framework validation/ranking/selection, aligned maps and NoData, report state/tables/figures and three open/close cycles. PDF smoke tests run in selected targets. Qt callback exceptions and plugin errors fail the run even when a controller catches an exception.

The official pyqgis4-checker image is resolved to a digest and runs `--dry_run` over the entire plugin. Sources are mounted read-only and hashes are compared. Its log is an artifact. The tool's exit code alone does not establish cleanliness; ci/review_checker.py rejects unreviewed diagnostics. Explicit narrowly scoped reviews require a source guard and rationale in ci/checker_reviews.json.

The runner uses a small iface test double with real QgsApplication, QgsMapCanvas, layers, widgets and signals. It does not verify every action in a complete interactive QGIS desktop. External R/rpy2 integration is outside this matrix; ordinary SciPy and residual kriging are exercised. Static API inventories are not exhaustive substitutes for execution.

The Windows QGIS 4.2.3 distribution ships Qt 6.11.0 and Matplotlib 3.11.2; the official Linux image tested earlier shipped Qt 6.9.2 and Matplotlib 3.10.1. Linux execution did not establish Windows compatibility. A Windows reproduction exposed the removed `matplotlib.cm.get_cmap` API, which aborted embedded drawing and Framework initialization. The shared palette adapter now uses the public registry when available, with the legacy lookup reserved for historical Matplotlib. Runtime tests exercise both API branches, reject incomplete palette controls, and inspect actual Qt preview pixels after optimized IDW, Larger View and repeated Data/Framework/Geostatistics tab changes at 1000×700 and 800×600. Fresh-session tests also require recreated information buttons.

## Run locally

Docker is optional for developers and never required by plugin users. No additional desktop QGIS installation is needed:

```bash
bash scripts/test_qgis_version.sh 3.14
bash scripts/test_qgis_version.sh 4.2
python3 ci/resolve_images.py --mode full
python3 scripts/test_qgis_version.py 3.44
```

With an existing QGIS Python interpreter:

```bash
python3 scripts/run_qgis_tests.py --requested 3.44 --pdf
```

For an already installed Windows QGIS 4.2.3 (PowerShell), without modifying its user profile:

```powershell
$env:BFI_QGIS_INSTALL='C:\Program Files\QGIS 4.2.3'
& 'C:\Program Files\QGIS 4.2.3\bin\python-qgis.bat' scripts\run_qgis_tests.py --requested 4.2 --pdf --output compatibility-results\windows-4.2\result.json
```

The API-removal regressions and preview checks run in every CI target through the same entry point. Local Windows evidence is recorded separately from the Linux matrix; an unchanged QGIS version does not imply identical Qt/scientific dependencies on different operating systems.

To trigger full GitHub Actions, open Actions → QGIS compatibility → Run workflow → full. The same container runner is invoked locally and in CI. Download `qgis-compatibility-report` for Markdown/JSON, each runtime artifact for logs/figures/PDFs and `pyqgis4-checker` for the migration diagnostics. The final report includes actual versions, component results, warnings/errors and numerical differences against the baseline.

A deliberate push can also request the full matrix by including `[compatibility full]` in its commit message. The manual workflow has an optional nightly checkbox; nightly remains informational.

No compatibility badge is added before this workflow becomes stable. No release or merge is performed by the compatibility workflow.

Official references: [QGIS Docker](https://github.com/qgis/qgis-docker), [QGIS image test instructions](https://github.com/qgis/qgis-docker/blob/master/desktop/README.md), [pyqgis4-checker](https://github.com/qgis/pyqgis4-checker), [roadmap](https://www.qgis.org/resources/roadmap/).
