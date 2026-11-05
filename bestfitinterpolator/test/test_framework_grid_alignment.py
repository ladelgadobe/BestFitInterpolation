"""Verify bounded shared ranges and safe reuse of real completed searches."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from bestfitinterpolator.framework_search import search_settings, for_method
from bestfitinterpolator.ml_search_settings import method_defaults
from bestfitinterpolator.framework_search_cache import fit, lookup, remember
from bestfitinterpolator.search_provenance import model_search_record, search_details


def test_default_budgets_match_individual_windows_and_exhaustive_cannot_bypass_them():
    settings = search_settings({'strategy': 'exhaustive'})
    assert settings['strategy'] == 'randomized'
    for method, iterations in (('RF', 10), ('RK', 10), ('SVM', 12)):
        assert for_method(settings, method) == method_defaults(method)
        assert for_method(settings, method)['iterations'] == iterations


def test_svm_candidates_preserve_the_v20_individual_convention():
    from bestfitinterpolator.SVM_Interpolation import _build_param_grid
    values = for_method(search_settings(), 'SVM')['grid_params']
    assert values['C']['min'] == .13 and values['gamma']['min'] == .01
    combinations = _build_param_grid(values)
    assert len(combinations) == 16 * 1 * 6
    assert min(p['C'] for p in combinations) == 2. ** .13
    assert max(p['C'] for p in combinations) == 2. ** 30.13
    assert {p['gamma'] for p in combinations} == {2. ** .01}


def test_rf_mtry_never_exceeds_available_predictors():
    from bestfitinterpolator.RF_Interpolation import _build_param_distributions
    grid, _ = _build_param_distributions(True, {}, method_defaults('RF')['grid_params'], 1)
    assert grid['max_features'] == [1]


def training():
    random = np.random.default_rng(12)
    frame = pd.DataFrame(random.normal(size=(18, 2)), columns=['x', 'y'])
    frame['target'] = frame.x * 2 + frame.y ** 2
    return frame


def tiny_grid(method):
    if method == 'SVM':
        return dict(C=dict(min=.5, max=1., step=.5), gamma=dict(min=.1, max=.2, step=.1),
                    epsilon=dict(min=.1, max=.1, step=.1))
    return dict(ntree=dict(min=5, max=10, step=5), mtry=dict(min=1, max=2, step=1),
                nodesize=dict(min=1, max=1, step=1))


@pytest.mark.parametrize('method', ['RF', 'SVM', 'RK'])
def test_reuse_removes_cv_fits_but_refits_final_model_on_all_rows(method, monkeypatch):
    if method == 'SVM':
        from bestfitinterpolator.SVM_Interpolation import _tune_svm as tune
        from sklearn.svm import SVR as Estimator
    else:
        from bestfitinterpolator.RF_Interpolation import _tune_random_forest as tune
        from sklearn.ensemble import RandomForestRegressor as Estimator
    calls = []
    original = Estimator.fit
    def fitted(self, X, y, *args, **kwargs):
        calls.append(len(y))
        return original(self, X, y, *args, **kwargs)
    monkeypatch.setattr(Estimator, 'fit', fitted)
    frame = training(); owner = SimpleNamespace()
    kwargs = dict(X=frame[['x', 'y']].to_numpy(), y=frame.target.to_numpy(),
                  use_grid_search=True, manual_params={}, grid_params=tiny_grid(method),
                  cv_folds=2, max_iterations=2, random_state=20)
    model, parameters = fit(owner, method, frame, 'target', ['x', 'y'], tune, kwargs)
    assert calls == [9, 9, 9, 9, 18]
    prediction = model.predict(kwargs['X'])
    model, selected = fit(owner, method, frame, 'target', ['x', 'y'], tune, kwargs)
    assert calls == [9, 9, 9, 9, 18, 18]
    assert selected == parameters
    np.testing.assert_array_equal(prediction, model.predict(kwargs['X']))
    record = model_search_record(model)
    assert record['status'] == 'reused' and not record['executed']
    assert record['evaluated_combinations'] == 0
    assert record['origin_search']['evaluated_combinations'] == 2
    assert 'Additional search combinations evaluated' in str(search_details({'search_summary': record}))
    assert 'Manual parameters' not in str(search_details({'search_summary': record}))


@pytest.mark.parametrize('change', ['values', 'target', 'coordinates', 'features', 'order', 'rows', 'grid', 'folds', 'iterations'])
def test_cache_invalidates_when_training_inputs_or_search_settings_change(change):
    owner = SimpleNamespace(); frame = training(); features = ['x', 'y']; grid = tiny_grid('RF')
    target = 'target'; folds, iterations = 2, 2
    key, _ = lookup(owner, 'RF', frame, target, features, grid, folds, iterations)
    remember(owner, 'RF', key, {'ntree': 5}, dict(status='completed', executed=True))
    assert lookup(owner, 'RF', frame, target, features, grid, folds, iterations)[1]
    if change == 'values': frame.loc[0, 'target'] += 1
    if change == 'target': frame['other'] = frame.target; target = 'other'
    if change == 'coordinates': frame.loc[0, 'x'] += 1
    if change == 'features': features.reverse()
    if change == 'order': frame = frame.iloc[::-1]
    if change == 'rows': frame = frame.iloc[:-1]
    if change == 'grid': grid['ntree']['max'] = 15
    if change == 'folds': folds += 1
    if change == 'iterations': iterations += 1
    assert lookup(owner, 'RF', frame, target, features, grid, folds, iterations)[1] is None


def test_manual_results_and_cancelled_search_are_not_cached():
    frame = training(); owner = SimpleNamespace()
    key, _ = lookup(owner, 'RF', frame, 'target', ['x', 'y'], tiny_grid('RF'), 2, 2)
    remember(owner, 'RF', key, {}, dict(status='manual', executed=False))
    assert not hasattr(owner, '_framework_search_cache')
    def cancelled(**kwargs):
        raise KeyboardInterrupt('Cancelled')
    with pytest.raises(KeyboardInterrupt):
        fit(owner, 'RF', frame, 'target', ['x', 'y'], cancelled,
            dict(grid_params=tiny_grid('RF'), cv_folds=2, max_iterations=2))
    assert not hasattr(owner, '_framework_search_cache')


def test_requested_budget_change_invalidates_even_with_identical_dense_limits():
    owner = SimpleNamespace(); frame = training(); grid = tiny_grid('RF')
    budget = dict(folds=5, iterations=10)
    key, _ = lookup(owner, 'RF', frame, 'target', ['x', 'y'], grid, 3, 8, budget)
    remember(owner, 'RF', key, {}, dict(status='completed', executed=True))
    assert lookup(owner, 'RF', frame, 'target', ['x', 'y'], grid, 3, 8, budget)[1]
    assert lookup(owner, 'RF', frame, 'target', ['x', 'y'], grid, 3, 8, dict(folds=5, iterations=12))[1] is None
