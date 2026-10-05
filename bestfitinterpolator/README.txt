Best Fit Interpolator
=====================

Best Fit Interpolator is a QGIS plugin for selecting, validating, and applying spatial interpolation methods for environmental, soil, and precision-agriculture data.

The plugin supports deterministic, geostatistical, machine-learning, and hybrid methods, including IDW, TPS, Ordinary Kriging, REML-assisted kriging, Random Forest, SVM, and Regression Kriging.

Version 1.2 Local Evaluation
----------------------------
- Framework can prepare, validate, and run RF, SVM, and RK without first running their individual method pages.
- Framework observed-vs-predicted plots use shared axes across methods, and RF/SVM previews use observed target-value limits to avoid misleading SVM-only autoscaling.
- Runtime profiles are classified as normal (up to 500 valid samples), dense (501 to 10,000), and massive/productivity-scale (above 10,000).
- Massive datasets above 10,000 valid samples use up to 10,000 spatially representative samples for Framework method-comparison validation; point maps use rasterized scatter or hexbin views so the display can use all points without creating thousands of interactive vector markers.
- Moran's I uses all valid samples, keeps k=8 and 199 permutations, and is optimized with spatial indexing plus exact-result caching instead of sample-based approximation.
- Productivity-scale datasets above 10,000 samples activate the massive profile: RF is capped at 300 trees with minimum leaf size 5, SVM uses a 128-component Nyström approximation, massive ML validation uses a reproducible hold-out split, semivariograms use fewer legible lags, and IDW/Moran/variogram stages avoid dense pairwise distance matrices.
- RF/SVM final interpolation writes GeoTIFF rasters in row blocks with tiled/BigTIFF output and switches the in-plugin map preview to sampled or hexbin drawing for large grids, so a completed model fit does not have to allocate a full display raster in memory.
- Data and Framework diagnostics stop early with a CRS alert when point and polygon layers do not share the same CRS.
- Dense-method choices are disclosed to the user and written to raster metadata where applicable.

Version 1.1
-----------
- Synchronized Framework and Geostatistics semivariogram previews.
- Spatial compatibility checks before interpolation.
- Popup alerts for warnings and errors.
- TPS and REML interpolation fixes.
- Standardized R² validation labels.
- About tab with documentation, support, article, and author links.

Main features
-------------
- Data diagnostics and spatial-pattern support.
- Semivariogram preview and kriging tools.
- Framework-guided method selection.
- Cross-validation metrics and observed-vs-predicted plots.
- Interpolation maps and PDF report support.

Authors
-------
Laura Delgado Bejarano
Lucas Rios do Amaral

Contact
-------
ladelgadobe@unal.edu.co

LinkedIn
--------
Laura Delgado Bejarano:
https://www.linkedin.com/in/laura-delgado-bejarano-09b6681a2/

Lucas Rios do Amaral:
https://www.linkedin.com/in/lucas-rios-do-amaral-bb302449/

Reference article
-----------------
Laura Delgado Bejarano, Agda Loureiro Gonçalves Oliveira, João Vitor Fiolo Pozzuto, Dario Castañeda Sánchez, and Lucas Rios do Amaral (2026). Performance of interpolation methods in digital soil mapping: the influence of data characteristics. Precision Agriculture, 27, Article 10.

DOI:
https://doi.org/10.1007/s11119-025-10311-8

Repository
----------
https://github.com/ladelgadobe/BestFitInterpolation
