# RF and RK diagnostic uncertainty maps

Version 2.1 adds a Map output selector to RF, RK and Framework. Interpolation exports aligned GeoTIFFs for the prediction and available diagnostic components. Standard deviations use response units; variances use squared response units. Each map has independent display settings and records its parent prediction execution.

RF tree standard deviation is the sample SD across the fitted trees' individual predictions, using T−1 in the variance denominator. It measures tree disagreement, not the standard error of the forest mean or a calibrated prediction interval. It excludes outcome noise and model bias. At least two trees are required; zero disagreement does not prove certainty.

RK residual standard deviation is conditional ordinary-kriging SD for the residual process, with the fitted RF trend and variogram held fixed. It excludes RF trend uncertainty, variogram parameter uncertainty and covariate error. RF trend tree dispersion is available separately. The components are not added as a total RK predictive variance.

The Framework report retains the prediction figure when a diagnostic output is selected and includes uncertainty maps in a separate section. This build does not implement calibrated prediction intervals.

RF and RK each have an **Add SD layer** checkbox, checked by default like OK. It controls publication on the next interpolation run: checked adds RF tree SD or RK residual-kriging SD to QGIS; unchecked adds no uncertainty layer. Prediction layers remain published. Variances and RK RF-trend spread are not automatically added. All calculated components remain available in the plugin selector, saved rasters and reports regardless of the checkbox. Framework has its own Add SD layer checkbox, enabled for the selected Kriging, RF or RK method and independent of the standalone checkboxes. SD publication choices are frozen with execution metadata.
