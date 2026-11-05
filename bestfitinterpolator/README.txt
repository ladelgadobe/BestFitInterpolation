Best Fit Interpolator
=====================

Best Fit Interpolator is a QGIS plugin for selecting, validating, and applying spatial interpolation methods for environmental, soil, and precision-agriculture data.

The plugin supports deterministic, geostatistical, machine-learning, and hybrid methods, including IDW, TPS, Ordinary Kriging, REML-assisted kriging, Random Forest, SVM, and Regression Kriging.

Version 2.1
-----------
- Offline English, Spanish and Brazilian Portuguese interface with a saved language selector, translated dialogs, plots and new reports.
- Ordinary and linear Universal Kriging with conditional SD/variance maps; joint constrained weighted least-squares MoM fitting and explicit model-scale/practical-range conventions.
- RF tree-dispersion maps and RK conditional residual-kriging uncertainty, with an optional Add SD layer control for standalone and Framework runs.
- Automatic bounded RF/SVM/RK grid search in Framework using the individual workflows' routines and defaults, configurable budgets, exact-input cache reuse and report provenance.
- Independent Framework and standalone maps, models, metrics and SD choices; Framework previews stay empty until a successful Framework interpolation.
- Independent raster-file predictor readers, coverage accounting, responsive validation with cancellation and hidden Windows helper processes.
- Reports distinguish initial recommendations, validation winners, next selections and actual executions, and display the complete map comparison at the report width.
- Updated 51-page English manual, retaining its stable filename and the original Auto, LOOCV and K-Fold validation workflow.

Version 2.0
-----------
- Outlier diagnostic combines IQR, MAD and optional Z flags with Global Moran and Local Moran/LISA; sample exclusions remain explicit user decisions.
- Reopening starts a clean session. IDW and TPS controls are separated; Regression Kriging keeps RF and residual kriging side by side with a shared adjustment dialog.
- MoM shows experimental semivariances and its model; REML shows the fitted theoretical model only. Advanced dialogs compare all three models and explain the numerical selection.
- Framework can prepare, validate and run RF, SVM and RK directly, and reports the method that successfully produced the final interpolation.
- Comparison shows aligned maps and their signed difference. Report includes an interactive summary, temporary browser HTML with collapsible sections, and PDF export.
- Map settings show palette gradients in a popup and preserve colors, scale and value limits in Larger View. Validation plots have no palette controls.
- Normal, dense and massive profiles bound tuning, prediction blocks and spatial neighborhoods; the actual validation strategy and sample count are disclosed.
- Automatic Global Moran uses all valid samples with spatial indexing and adaptive permutation counts. Outlier diagnostic retains its explicit neighborhood and permutation settings.
- Qt5/Qt6 and Matplotlib compatibility fixes restore embedded previews; native NumPy indices support 32-bit QGIS and machine-learning dependencies are isolated by Python/platform ABI.
- The updated English manual uses current Paulínia screenshots and documents outlier parameters, MoM/REML, map comparison, reports and dense/massive workflows.

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

User Manual
-----------
https://github.com/ladelgadobe/BestFitInterpolation/blob/main/BestFitInterpolator_User_Manual.pdf

Repository
----------
https://github.com/ladelgadobe/BestFitInterpolation
