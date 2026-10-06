"""Numerical regressions for displayed REML fits and Framework model metrics."""
import numpy as np
from .test_development_numerical_baseline import legacy_policy
from bestfitinterpolator import semivariogram_engine as engine
from bestfitinterpolator.framework_tab import FrameworkTabController
from bestfitinterpolator.variogram_utils import max_pairwise_distance,nearest_neighbor_distance,safe_lag_width


def test_reml_validation_returns_optimized_parameters_for_the_displayed_curve():
    rng=np.random.default_rng(17); xy=rng.uniform(0.,12.,(8,2)); z=np.sin(xy[:,0]/3.)+.15*xy[:,1]
    for token in ('spherical','exponential','gaussian'):
        current=engine.SemivariogramEngine('ok_reml')
        row=current._evaluate_model_cv(token,xy[:,0],xy[:,1],z,10.,2.)
        fit=engine.fit_ok_reml_interface(np.column_stack((xy,z)),current._model_text_from_token(token),
            init_from_mom={key:row[key] for key in ('nugget','psill','range')},random_state=123)
        assert row['selection']=='reml_cv'
        np.testing.assert_allclose(row['fitted_params'],[fit[key] for key in ('nugget','psill','range')],rtol=0,atol=0)


def test_framework_popup_cv_preserves_framework_metrics_and_ranking():
    names=('_run_ok_framework_cv','_guess_initial_params','_normalize_model_token','_model_func','_validation_row_from_predictions',
        '_pearson_r','_lccc','_ok_model_code_for_reml')
    old=legacy_policy('framework_tab.py','FrameworkTabController',names)
    rng=np.random.default_rng(3); xy=rng.uniform(0,20,(8,2)); z=np.sin(xy[:,0]/3)+.15*xy[:,1]
    x,y=xy.T; cutoff=.5*max_pairwise_distance(x,y); lag=safe_lag_width(x,y,cutoff,nearest_neighbor_distance(x,y))
    old.state=type('State',(),{'variogram_model':'Spherical'})()
    old._is_ok_model_auto=lambda model:False
    old._pairwise_distances=lambda x,y:np.array([max_pairwise_distance(x,y)])
    old._safe_lag_width=safe_lag_width; old._nearest_neighbor_dist=nearest_neighbor_distance
    old._automatic_fold_indices=FrameworkTabController._automatic_fold_indices
    old._method_group=lambda model:'Geostatistics'
    for mode in ('MoM','REML'):
        old._resolve_ok_fit_method=lambda n:mode
        rows=engine.SemivariogramEngine('framework_sdi').validate_framework(x,y,z,cutoff,lag,mode,
            FrameworkTabController._automatic_fold_indices(len(z),x,y))
        assert len(rows)==3 and all(not row.get('error') for row in rows)
        assert rows==sorted(rows,key=lambda r:(-r['r2'],r['rmse']))
        for row in rows:
            pred=old._run_ok_framework_cv(x,y,z,model_name=row['model'])
            expected=old._validation_row_from_predictions(row['model'],z,pred)
            for key in ('rmse','rmse_pct','mae','r2','lccc'):
                assert row[key]==expected[key],(mode,row['model'],key,row[key],expected[key])
            assert row['pearson']==expected['r']
