"""Memory-bounded dispersion of the fitted forest's individual tree outputs."""
import numpy as np
from .numerical_runtime import responsive_numerical

RF_DESCRIPTION = (
    "Sample standard deviation across the fitted forest's individual tree predictions (ddof=1). "
    "This diagnostic describes tree disagreement, not the standard error of the forest mean "
    "or a calibrated prediction interval. It excludes outcome noise and model bias. "
    "The variance output is the square of this standard deviation. "
    "At least two trees are required; identical trees can give zero dispersion without implying certainty.")
RK_DESCRIPTION = (
    "Conditional point-support standard deviation of ordinary kriging of the RF residuals, "
    "with the fitted RF trend and residual variogram held fixed. "
    "It excludes RF trend uncertainty, variogram parameter uncertainty and covariate error. "
    "The variance output is the square of this standard deviation. "
    "It is not total RK predictive uncertainty or a calibrated prediction interval.")


@responsive_numerical
def forest_prediction_dispersion(model, predictors, chunk_size=4096, progress_fn=None):
    """Return the forest mean, tree SD and variance without a trees-by-grid array.

    The running mean has the same mathematical definition as model.predict.
    Welford's update avoids cancellation for large response offsets. With one
    tree the diagnostic is undefined and is returned as NaN, not false certainty.
    """
    predictors = np.asarray(predictors)
    if predictors.ndim != 2:
        raise ValueError('Forest predictors must be a two-dimensional matrix.')
    trees = list(getattr(model, 'estimators_', ()))
    if not trees:
        raise ValueError('Fit the Random Forest before computing tree dispersion.')
    if getattr(model, 'n_outputs_', 1) != 1:
        raise ValueError('Tree dispersion requires a single response variable.')
    if predictors.shape[1] != getattr(model, 'n_features_in_', predictors.shape[1]):
        raise ValueError('Predictors must match the fitted forest feature order.')
    if not np.isfinite(predictors).all():
        raise ValueError('Use finite, complete predictors for forest dispersion.')
    chunk_size = max(1, int(chunk_size))
    count = len(predictors)
    means = np.empty(count, dtype=float)
    variances = np.full(count, np.nan, dtype=float)
    total = max(1, count * len(trees))
    for start in range(0, count, chunk_size):
        end = min(count, start + chunk_size)
        block = np.asarray(predictors[start:end], dtype=np.float32)
        mean = np.zeros(end - start, dtype=float)
        m2 = np.zeros(end - start, dtype=float)
        for index, tree in enumerate(trees, start=1):
            prediction = np.asarray(tree.predict(block), dtype=float).ravel()
            if prediction.shape != mean.shape or not np.isfinite(prediction).all():
                raise ValueError('Every tree must return one finite prediction per grid cell.')
            delta = prediction - mean
            mean += delta / index
            m2 += delta * (prediction - mean)
            if progress_fn is not None and (index % max(1, len(trees)//10) == 0 or index == len(trees)):
                done = start * len(trees) + (end-start) * index
                progress_fn(int(1000 * done / total), 1000,
                            'Computing RF prediction and tree dispersion')
        means[start:end] = mean
        if len(trees) > 1:
            variances[start:end] = np.maximum(m2 / (len(trees)-1), 0.)
    return dict(prediction=means, variance=variances, std=np.sqrt(variances), tree_count=len(trees))
