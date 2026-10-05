"""Synthetic statistical and Anselin diagnostic regression cases."""
import numpy as np
from bestfitinterpolator.diagnostics_engine import statistical_flags,DiagnosticsEngine,DiagnosticsState,build_neighbors,classify


def test_statistical_extreme_and_consensus():
    v=np.r_[np.zeros(30),100.]
    r=statistical_flags(v,methods=("IQR","MAD","Z"))
    assert r["votes"][-1]==3 and r["statistical"][-1]
    assert np.isinf(r["scores"]["MAD"][-1])
    assert not np.any(r["flags"]["MAD"][:-1])
    assert not statistical_flags(v,methods=("IQR",),consensus="At least N",at_least=2)["statistical"][-1]
    assert statistical_flags(v,methods=("IQR","MAD"),consensus="All")["statistical"][-1]


def test_constant_and_missing_values():
    xy=np.column_stack((np.arange(20),np.zeros(20)))
    result=DiagnosticsEngine().calculate(xy,np.ones(20),dict(permutations=99))
    assert np.all(result["lisa"]=="NS") and not np.any(result["statistical"])
    xy[1]=np.nan;v=np.ones(20);v[2]=np.nan
    result=DiagnosticsEngine().calculate(xy,v,dict(permutations=99))
    assert np.all(result["combined"][[1,2]]=="Missing/Invalid")
    assert result["global_moran"]["I"]==0.


def test_duplicate_coordinates_and_small_samples():
    xy=np.array([[0,0],[0,0],[1,1],[2,2.]])
    neighbors=build_neighbors(xy,k=8)
    assert all(i not in row and len(row)==3 for i,row in enumerate(neighbors))
    result=DiagnosticsEngine().calculate(xy,np.arange(4.),dict(permutations=99))
    assert np.all(result["pseudo_p"]==1.)
    for n in (0,1,2):
        result=DiagnosticsEngine().calculate(xy[:n],np.arange(float(n)),dict(permutations=99))
        assert len(result["lisa"])==n


def test_hh_ll_hl_lh_significance_and_reproducibility():
    grid=np.array([(x,y) for x in range(10) for y in range(10)],float)
    coords=np.vstack((grid,grid+[100,0]))
    rng=np.random.default_rng(10)
    values=np.r_[10+rng.normal(0,.1,100),-10+rng.normal(0,.1,100)]
    values[55]=-15;values[155]=15
    engine=DiagnosticsEngine(); settings=dict(permutations=499,seed=42)
    result=engine.calculate(coords,values,settings)
    assert result["lisa"][55]=="LH" and result["lisa"][155]=="HL"
    assert np.count_nonzero(result["lisa"]=="HH")>30 and np.count_nonzero(result["lisa"]=="LL")>30
    assert not np.any(result["spatial_outlier"][np.isin(result["lisa"],("HH","LL"))])
    repeated=DiagnosticsEngine().calculate(coords,values,settings)
    np.testing.assert_array_equal(result["pseudo_p"],repeated["pseudo_p"])
    neighbors=engine._neighbors;spatial=engine._spatial
    engine.calculate(coords,values,dict(settings,alpha=.01,k=2.5))
    assert engine._neighbors is neighbors and engine._spatial is spatial


def test_combined_classes_keep_clusters_distinct():
    spatial=dict(centered=np.array([1.,-1,1,-1,1,-1,1]),spatial_lag=np.array([-1.,1,1,-1,-1,1,1]),
        pseudo_p=np.array([.01,.01,.01,.01,.01,.8,.8]),neighbors=np.ones(7))
    stat=np.array([True,False,False,False,False,True,False])
    lisa,outlier,combined=classify(stat,spatial)
    assert list(combined)==["Statistical + Spatial","Spatial only","HH cluster","LL cluster","Spatial only","Statistical only","Normal"]


def test_distance_islands_and_explicit_decisions():
    xy=np.array([[0.,0],[1,0],[2,0],[1000,1000]])
    result=DiagnosticsEngine().calculate(xy,np.arange(4.),dict(neighborhood="Distance threshold",distance=2.,permutations=99))
    assert result["neighborhood"]["isolated"]==1 and result["lisa"][-1]=="NS"
    state=DiagnosticsState("a","v",np.arange(4),xy,np.arange(4.))
    original=state.values.copy();state.decide([2],"Exclude")
    assert list(state.analysis_mask)==[True,True,False,True]
    state.decide([2],"Keep");assert np.all(state.analysis_mask)
    state.decide([2],"Reset");assert not state.decisions
    np.testing.assert_array_equal(state.values,original)


def test_optional_scipy_fallback_and_local_moment():
    import builtins
    from bestfitinterpolator import diagnostics_engine as module
    xy=np.array([[0.,0],[1.,0],[1.,1],[2.,1],[-1.,0],[20.,20]])
    expected=build_neighbors(xy,mode="Distance threshold",distance=1.5)
    tree=module.cKDTree
    try:
        module.cKDTree=None
        actual=build_neighbors(xy,mode="Distance threshold",distance=1.5)
    finally:
        module.cKDTree=tree
    for a,b in zip(actual,expected):np.testing.assert_array_equal(np.sort(a),np.sort(b))
    values=np.array([0.,2.,3.,6.,1.,10.])
    reference=module.spatial_statistics(values,actual,permutations=99)
    original_import=builtins.__import__
    def without_sparse(name,*args,**kwargs):
        if name=="scipy.sparse":raise ImportError("Optional dependency unavailable")
        return original_import(name,*args,**kwargs)
    try:
        builtins.__import__=without_sparse
        fallback=module.spatial_statistics(values,actual,permutations=99)
    finally:
        builtins.__import__=original_import
    np.testing.assert_allclose(reference["local_i"],fallback["local_i"],rtol=0,atol=0)
    assert reference["global_moran"]==fallback["global_moran"]
    z=values-values.mean();m2=np.mean(z*z)
    expected_i=np.array([z[i]*np.mean(z[row])/m2 if len(row) else 0. for i,row in enumerate(actual)])
    np.testing.assert_allclose(reference["local_i"],expected_i,rtol=0,atol=0)


def test_empty_analysis_mask_is_boolean():
    state=DiagnosticsState("empty","value",np.array([],dtype=int),np.empty((0,2)),np.array([]))
    assert state.analysis_mask.dtype==bool and state.analysis_mask.size==0


def test_reader_mask_covers_invalid_values_geometry_and_removed_ids():
    from types import SimpleNamespace
    from qgis.core import QgsProject,QgsVectorLayer,QgsFeature,QgsGeometry,QgsPointXY
    from bestfitinterpolator.diagnostics_ui import capture_data,feature_in_analysis
    layer=QgsVectorLayer("Point?crs=EPSG:31983&field=value:double","Mask invalid fixtures","memory")
    features=[]
    for i,value in enumerate((1.,np.nan,np.inf,1.,2.)):
        feature=QgsFeature(layer.fields());feature.setAttributes([value])
        if i!=3:feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(i),0.)))
        features.append(feature)
    layer.dataProvider().addFeatures(features);QgsProject.instance().addMapLayer(layer)
    plugin=SimpleNamespace(dlg=SimpleNamespace(Points=SimpleNamespace(currentText=lambda:layer.name()),Points_2=SimpleNamespace(currentText=lambda:"value")),diagnostics_states={})
    try:
        state,_=capture_data(plugin)
        actual=list(layer.getFeatures())
        assert state.analysis_mask.sum()==2 and layer.featureCount()==5
        assert [feature_in_analysis(plugin,layer,f) for f in actual]==list(state.analysis_mask)
        state.decide([state.ids[0]],"Exclude")
        state.decide([state.ids[1]],"Keep")
        assert [feature_in_analysis(plugin,layer,f) for f in actual]==list(state.analysis_mask)
        removed=int(state.ids[1]);state.decide([removed],"Exclude")
        layer.dataProvider().deleteFeatures([removed])
        refreshed,_=capture_data(plugin)
        assert removed not in refreshed.decisions and layer.featureCount()==4
    finally:
        QgsProject.instance().removeMapLayer(layer.id())
