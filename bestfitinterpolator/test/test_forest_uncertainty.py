"""Independent checks for tree spread, predictions and unavailable uncertainty."""
from types import SimpleNamespace
import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor
from bestfitinterpolator.forest_uncertainty import forest_prediction_dispersion
from bestfitinterpolator.RF_Interpolation import rf_interpolation


def test_forest_moments_match_explicit_tree_matrix_for_every_chunk_size():
    rng=np.random.default_rng(42); X=rng.normal(size=(71,3));y=3+X[:,0]+rng.normal(size=71)
    forest=RandomForestRegressor(n_estimators=19,random_state=20,n_jobs=1).fit(X,y)
    query=rng.normal(size=(23,3))
    independent=np.vstack([tree.predict(query) for tree in forest.estimators_])
    for chunk in (1,7,100):
        result=forest_prediction_dispersion(forest,query,chunk_size=chunk)
        np.testing.assert_allclose(result['prediction'],forest.predict(query),atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(result['variance'],np.var(independent,axis=0,ddof=1),atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(result['std']**2,result['variance'],atol=1e-12)


def test_one_tree_reports_unavailable_dispersion_instead_of_zero():
    X=np.arange(20.).reshape(10,2);y=np.arange(10.)
    forest=RandomForestRegressor(n_estimators=1,random_state=20,n_jobs=1).fit(X,y)
    result=forest_prediction_dispersion(forest,X)
    np.testing.assert_allclose(result['prediction'],forest.predict(X))
    assert np.isnan(result['variance']).all() and np.isnan(result['std']).all()


def test_constant_response_gives_zero_tree_disagreement():
    X=np.arange(20.).reshape(10,2)
    forest=RandomForestRegressor(n_estimators=7,random_state=20,n_jobs=1).fit(X,np.full(10,9.))
    result=forest_prediction_dispersion(forest,X)
    np.testing.assert_allclose(result['prediction'],9.)
    np.testing.assert_array_equal(result['variance'],np.zeros(10))


def test_rf_outputs_preserve_missing_grid_rows_and_original_predictions():
    import pandas as pd
    rng=np.random.default_rng(20);X=rng.uniform(size=(40,2));y=np.sin(X[:,0])+X[:,1]
    points=pd.DataFrame(dict(x=X[:,0],y=X[:,1],value=y))
    grid=pd.DataFrame(dict(x=[.1,np.nan,.7],y=[.3,.5,.9],__flat_index=[8,2,5]))
    result=rf_interpolation(points,grid,'value',['x','y'],False,dict(ntree=13,mtry=2,nodesize=1),{})
    output=result['grid_with_pred']
    assert output['__flat_index'].tolist()==[8,2,5]
    columns=['value_pred']+list(result['uncertainty_columns'].values())
    assert output.loc[1,columns].isna().all()
    np.testing.assert_allclose(output.loc[[0,2],'value_pred'].to_numpy(float),
        result['model'].predict(grid.loc[[0,2],['x','y']].to_numpy(float)),atol=1e-12)
    assert output.loc[[0,2],result['uncertainty_columns']['rf_std']].ge(0).all()


def test_invalid_predictors_and_unfitted_forests_fail_explicitly():
    with pytest.raises(ValueError,match='Fit the Random Forest'):
        forest_prediction_dispersion(SimpleNamespace(),np.ones((2,2)))
    forest=RandomForestRegressor(n_estimators=2,random_state=1).fit([[0,0],[1,1]],[0,1])
    with pytest.raises(ValueError,match='finite'):
        forest_prediction_dispersion(forest,np.array([[np.nan,1.]]))
