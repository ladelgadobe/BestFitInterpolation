"""Check executed tuning records against actual model fits and report snapshots."""
from types import SimpleNamespace
import numpy as np
from bestfitinterpolator.RF_Interpolation import _tune_random_forest
from bestfitinterpolator.SVM_Interpolation import _tune_svm
from bestfitinterpolator.search_provenance import model_search_record, search_details
from bestfitinterpolator.interpolation_result import parameter_snapshot
from bestfitinterpolator.report_model import snapshot_framework_report, report_html


def data():
    X = np.random.default_rng(42).normal(size=(18, 2))
    return X, X[:, 0] * 2 + X[:, 1] ** 2


def rf_grid(single=False):
    return dict(ntree=dict(min=5, max=5 if single else 10, step=5),
                mtry=dict(min=1, max=1 if single else 2, step=1),
                nodesize=dict(min=1, max=1, step=1))


def test_rf_record_matches_number_of_actual_fits(monkeypatch):
    from sklearn.ensemble import RandomForestRegressor
    calls = []
    original = RandomForestRegressor.fit
    def fit(self, X, y, *args, **kwargs):
        calls.append(len(y))
        return original(self, X, y, *args, **kwargs)
    monkeypatch.setattr(RandomForestRegressor, 'fit', fit)
    X, y = data()
    model, params = _tune_random_forest(X, y, True, {}, rf_grid(), cv_folds=2, max_iterations=2)
    record = model_search_record(model)
    assert calls == [9, 9, 9, 9, 18]
    assert record['executed'] and record['evaluated_combinations'] == 2
    assert record['total_combinations'] == 4 and record['effective_folds'] == 2
    assert record['objective'] == 'MAE' and record['best_score'] == params['cv_mae']
    assert record['selected_parameters'] == {k: params[k] for k in ('ntree', 'mtry', 'nodesize')}


def test_manual_fit_does_not_claim_search():
    X, y = data()
    model, _ = _tune_random_forest(X, y, False, dict(ntree=5, mtry=1, nodesize=1), {})
    record = model_search_record(model)
    assert not record['requested'] and not record['executed']
    assert record['evaluated_combinations'] == 0 and record['effective_folds'] == 0
    assert 'Manual parameters; search not run' in str(search_details({'search_summary': record}))


def test_rf_single_grid_configuration_preserves_v20_direct_fit():
    X, y = data()
    model, _ = _tune_random_forest(X, y, True, {}, rf_grid(single=True))
    record = model_search_record(model)
    assert record['requested'] and not record['executed']
    assert record['status'] == 'single_configuration' and record['evaluated_combinations'] == 0


def test_svm_search_record_matches_scored_configurations(monkeypatch):
    from bestfitinterpolator import SVM_Interpolation as svm
    calls = []
    original = svm._cv_rmse_for_params
    def score(X, y, params, **kwargs):
        calls.append(dict(params))
        return original(X, y, params, **kwargs)
    monkeypatch.setattr(svm, '_cv_rmse_for_params', score)
    X, y = data()
    grid = dict(C=dict(min=.5, max=1., step=.5), gamma=dict(min=.1, max=.2, step=.1),
                epsilon=dict(min=.1, max=.1, step=.1))
    model, params = _tune_svm(X, y, grid_params=grid, cv_folds=2, max_iterations=2)
    record = model_search_record(model)
    assert len(calls) == record['evaluated_combinations'] == 2
    assert record['objective'] == 'RMSE' and record['best_score'] == params['cv_rmse']
    assert record['selected_parameters'] in calls


def test_report_uses_completed_snapshot_after_configuration_changes():
    X, y = data()
    model, params = _tune_random_forest(X, y, True, {}, rf_grid(), cv_folds=2, max_iterations=2)
    config = dict(search_summary=model_search_record(model), resolved_params=params, search_mode='grid')
    snapshot = parameter_snapshot(config)
    config['search_summary']['selected_parameters']['ntree'] = 9999
    config['search_mode'] = 'manual'
    framework = SimpleNamespace(plugin=None,
        state=SimpleNamespace(validation_results=[dict(method='RFE', configuration=snapshot)]),
        _collect_legacy_report_html=lambda: '<html><body><h2>Validation Results</h2><p>Scores</p></body></html>')
    state = snapshot_framework_report(framework)
    rendered = report_html(state)
    assert 'Machine learning hyperparameter selection' in rendered
    assert 'RF - Framework performance validation' in rendered
    assert 'Reproducible random search' in rendered and '9999' not in rendered
    assert 'Search repeated inside performance-validation folds' in rendered
    assert next(s for s in state.sections if s.key == 'ml_hyperparameters').mandatory


def test_old_configuration_is_not_misrepresented_as_a_completed_search():
    assert 'Execution details not recorded' in str(search_details({'search_mode': 'grid'}))


def test_manual_svm_record_is_explicit():
    X, y = data()
    model, _ = _tune_svm(X, y, use_grid_search=False, manual_params=dict(C=1., gamma=.1, epsilon=.1))
    assert model_search_record(model)['status'] == 'manual'


def test_exhaustive_search_evaluates_all_combinations_despite_iteration_budget():
    X, y = data()
    model, _ = _tune_random_forest(X, y, True, {}, rf_grid(), cv_folds=2,
                                  max_iterations=1, search_strategy='exhaustive')
    record = model_search_record(model)
    assert record['algorithm'] == 'grid_search'
    assert record['evaluated_combinations'] == record['total_combinations'] == 4


def test_framework_settings_are_independent_and_always_search():
    from bestfitinterpolator.framework_search import search_settings
    first = search_settings()
    first['grids']['RF']['ntree']['max'] = 5
    second = search_settings()
    assert second['grids']['RF']['ntree']['max'] == 1000
    assert second['strategy'] == 'randomized'


def test_framework_svm_ranges_preserve_effective_v20_defaults():
    from bestfitinterpolator.framework_search import search_settings
    from bestfitinterpolator.SVM_Interpolation import _build_param_grid
    grid = _build_param_grid(search_settings()['grids']['SVM'])
    assert min(p['C'] for p in grid) == 2. ** .13
    assert max(p['C'] for p in grid) == 2. ** 30.13
    assert {p['gamma'] for p in grid} == {2. ** .01}
