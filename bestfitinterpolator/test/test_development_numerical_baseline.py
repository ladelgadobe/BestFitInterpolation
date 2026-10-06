"""Direct comparisons with mathematical policies extracted from original 1.2."""
import ast
import os
import typing
from pathlib import Path
import numpy as np
from qgis.PyQt.QtCore import QCoreApplication
from bestfitinterpolator import semivariogram_engine as engine

BASE=Path(os.environ.get("BFI_BASELINE_ROOT",str(Path(__file__).resolve().parents[3]/"local_build_v1_2_20260902/bestfitinterpolator")))


def legacy_policy(file,cls,names):
    tree=ast.parse((BASE/file).read_text(encoding="utf-8-sig"))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    body=[n for n in node.body if isinstance(n,ast.FunctionDef) and n.name in names]
    module=ast.Module(body=[ast.ClassDef(name="Legacy",bases=[],keywords=[],body=body,decorator_list=[])],type_ignores=[])
    namespace=dict(vars(engine));namespace["QCoreApplication"]=QCoreApplication
    namespace.update({name:getattr(typing,name) for name in ("Optional","Dict","Any","List")})
    exec(compile(ast.fix_missing_locations(module),"legacy_math","exec"),namespace)
    obj=namespace["Legacy"]();obj._use_reml=False
    obj._bin_variogram=lambda x,y,z,cutoff,lag:engine.bin_experimental_variogram(x,y,z,cutoff,lag)
    return obj


def test_ordinary_fitting_and_validation_equal_baseline():
    names=("_normalize_model_token","_model_func","_guess_initial_params","_model_text_from_token","_validation_metrics","_evaluate_model_cv")
    rng=np.random.default_rng(3);xy=rng.uniform(0,20,(12,2));v=np.sin(xy[:,0])+rng.normal(0,.1,12)
    lags,gamma=engine.bin_experimental_variogram(xy[:,0],xy[:,1],v,15.,2.)
    for file,profile in (("ok_r_integration_MoM.py","ok_mom"),("ok_r_integration_reml.py","ok_reml")):
        old=legacy_policy(file,"OKTabController",names);new=engine.SemivariogramEngine(profile,use_reml=False)
        for model in ("spherical","exponential","gaussian"):
            np.testing.assert_allclose(old._guess_initial_params(lags,gamma,15.,model),new._guess_initial_params(lags,gamma,15.,model),rtol=0,atol=0)
            expected=old._evaluate_model_cv(model,xy[:,0],xy[:,1],v,15.,2.)
            actual=new._evaluate_model_cv(model,xy[:,0],xy[:,1],v,15.,2.)
            for key in ("rmse","mae","r2","pearson","lccc","nugget","psill","range"):
                np.testing.assert_allclose(actual[key],expected[key],rtol=0,atol=0,equal_nan=True)


def test_residual_fitting_and_validation_equal_baseline():
    names=("_model_func","_guess_initial_params","_fit_variogram_candidates","_validation_metrics","_residual_model_cv_metrics","_select_best_variogram_fit")
    old=legacy_policy("RF_RegressionKriging.py","RegressionKrigingRFController",names);new=engine.SemivariogramEngine("residual")
    rng=np.random.default_rng(8);xy=rng.uniform(0,30,(15,2));v=rng.normal(size=15)
    lags,gamma=engine.bin_experimental_variogram(xy[:,0],xy[:,1],v,20.,3.)
    expected=old._fit_variogram_candidates(lags,gamma,20.);actual=new._fit_variogram_candidates(lags,gamma,20.)
    assert expected==actual
    for a,b in zip(expected,actual):
        ea=old._residual_model_cv_metrics(xy[:,0],xy[:,1],v,a);eb=new._residual_model_cv_metrics(xy[:,0],xy[:,1],v,b)
        for key in ("rmse","mae","r2","pearson","lccc"):np.testing.assert_allclose(ea[key],eb[key],rtol=0,atol=0,equal_nan=True)


def test_actual_reml_validation_equal_baseline():
    names=("_normalize_model_token","_model_func","_guess_initial_params","_model_text_from_token","_validation_metrics","_evaluate_model_cv")
    old=legacy_policy("ok_r_integration_reml.py","OKTabController",names)
    old._use_reml=True
    new=engine.SemivariogramEngine("ok_reml",use_reml=True)
    assert engine._HAS_REML and engine.cv_ok_reml_interface is not None
    rng=np.random.default_rng(17);xy=rng.uniform(0.,12.,(8,2));v=np.sin(xy[:,0]/3.)+.15*xy[:,1]
    original=engine.cv_ok_reml_interface;completed=[]
    def tracked(*args,**kwargs):
        result=original(*args,**kwargs);completed.append(True);return result
    old._evaluate_model_cv.__globals__["cv_ok_reml_interface"]=tracked
    try:
        engine.cv_ok_reml_interface=tracked
        expected=old._evaluate_model_cv("exponential",xy[:,0],xy[:,1],v,10.,2.)
        actual=new._evaluate_model_cv("exponential",xy[:,0],xy[:,1],v,10.,2.)
    finally:
        engine.cv_ok_reml_interface=original
    assert len(completed)==2,"Both comparisons must execute REML successfully, without falling back to MoM"
    for key in ("rmse","mae","r2","pearson","lccc","nugget","psill","range"):
        np.testing.assert_allclose(actual[key],expected[key],rtol=0,atol=0,equal_nan=True)


def test_core_algorithms_and_policies_are_unchanged():
    root=Path(__file__).resolve().parents[1]
    for name in ("IDW_optimized.py","Thin_plate_spline.py","kriging_ordinary.py","kriging_reml.py","RF_Interpolation.py","SVM_Interpolation.py","performance_policy.py","validation_policy.py","variogram_utils.py"):
        # Qt-only imports differ; numerical functions retain the same AST.
        def functions(path):
            tree=ast.parse(path.read_text(encoding="utf-8-sig"));return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
        assert functions(root/name)==functions(BASE/name),name


def test_framework_and_sdi_heuristics_equal_baseline():
    names=("_guess_initial_params","_normalize_model_token","_model_func")
    cases=((np.array([]),np.array([]),10.),(np.array([1.,2.,4.,8.]),np.array([.2,.8,1.2,1.]),10.),
           (np.array([1.,2.]),np.zeros(2),5.),(np.array([np.nan,-1.,3.]),np.array([5.,-3.,2.]),7.))
    for file,cls,profile in (("framework_tab.py","FrameworkTabController","framework"),("framework_sdi_dialog.py","FrameworkSDIDialog","framework_sdi")):
        old=legacy_policy(file,cls,names);new=engine.SemivariogramEngine(profile)
        for model in ("spherical","exponential","gaussian","Sph","Exp","Gau"):
            for lags,gamma,cutoff in cases:
                np.testing.assert_allclose(old._guess_initial_params(lags,gamma,cutoff,model),new._guess_initial_params(lags,gamma,cutoff,model),rtol=0,atol=0)
            np.testing.assert_array_equal(old._model_func(np.arange(12.),model,.3,1.2,5.),new._model_func(np.arange(12.),model,.3,1.2,5.))
