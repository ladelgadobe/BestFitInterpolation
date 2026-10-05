"""Grid safety, display-only controls, report state and repeated output checks."""
import tempfile
from pathlib import Path
import numpy as np
from osgeo import gdal,osr
from bestfitinterpolator.map_comparison import difference_arrays,difference_statistics,check_grids,compare_rasters
from bestfitinterpolator.map_controls import common_value_range,MapDisplayControls,MatplotlibMapDisplay
from bestfitinterpolator.report_model import ReportState,ReportSection,ReportTable,report_html
from bestfitinterpolator.report_builder import export_report_pdf,create_document,configure_printer
from bestfitinterpolator.compat import enum_value
from bestfitinterpolator.mpl_compat import FigureCanvas
from matplotlib.figure import Figure


def test_difference_zero_sign_and_nodata():
    a=np.array([[1.,2],[np.nan,-9999.]])
    result=difference_arrays(a,a,nodata_a=-9999,nodata_b=-9999)
    np.testing.assert_array_equal(result[0],[0.,0.]); assert np.all(np.isnan(result[1]))
    b=np.array([[0.,4],[1.,2.]])
    diff=difference_arrays(a,b,nodata_a=-9999)
    np.testing.assert_array_equal(diff[0],[1.,-2.])
    assert difference_statistics(diff)["mean"]==-.5


def test_mismatched_grid_detection():
    a=dict(shape=(2,2),crs="EPSG:31983",transform=(0,1,0,2,0,-1))
    for b in (dict(a,shape=(2,3)),dict(a,crs="EPSG:4326"),dict(a,transform=(.5,1,0,2,0,-1))):
        try: check_grids(a,b)
        except ValueError: pass
        else: raise AssertionError("Mismatched grid was accepted")


def test_gdal_exact_full_grid_difference():
    with tempfile.TemporaryDirectory() as folder:
        crs=osr.SpatialReference();crs.ImportFromEPSG(31983)
        arrays=[np.arange(25.).reshape(5,5),np.arange(25.).reshape(5,5)+2]
        arrays[0][1,2]=-9999
        paths=[]
        for i,array in enumerate(arrays):
            path=str(Path(folder)/("map"+str(i)+".tif"));paths.append(path)
            ds=gdal.GetDriverByName("GTiff").Create(path,5,5,1,gdal.GDT_Float64)
            ds.SetProjection(crs.ExportToWkt());ds.SetGeoTransform((0,1,0,5,0,-1));ds.GetRasterBand(1).SetNoDataValue(-9999);ds.GetRasterBand(1).WriteArray(array);ds=None
        previews,stats,grid,out=compare_rasters(*paths)
        assert stats["count"]==24 and stats["mean"]==stats["median"]==-2.
        assert np.isnan(previews[2][1,2])
        ds=gdal.Open(out);assert ds.RasterXSize==5;ds=None
        Path(out).unlink()


def test_full_grid_statistics_include_unsampled_extreme():
    with tempfile.TemporaryDirectory() as folder:
        crs=osr.SpatialReference();crs.ImportFromEPSG(31983)
        a=np.arange(700.*10.).reshape(700,10);b=a+2.
        a[101,3]=90000.;a[333,7]=np.nan
        paths=[]
        for i,array in enumerate((a,b)):
            path=str(Path(folder)/("map"+str(i)+".tif"));paths.append(path)
            ds=gdal.GetDriverByName("GTiff").Create(path,10,700,1,gdal.GDT_Float64)
            ds.SetProjection(crs.ExportToWkt());ds.SetGeoTransform((0,1,0,700,0,-1))
            ds.GetRasterBand(1).SetNoDataValue(float("nan"));ds.GetRasterBand(1).WriteArray(array);ds=None
        previews,statistics,grid,out=compare_rasters(*paths)
        assert grid["preview_step"]==2 and previews[0].shape==(350,5)
        assert np.nanmax(previews[0])<90000. and grid["value_range_a"][1]==90000.
        reference=difference_statistics(difference_arrays(a,b))
        assert statistics==reference
        ds=gdal.Open(out);np.testing.assert_allclose(ds.ReadAsArray(),difference_arrays(a,b),rtol=0,atol=0,equal_nan=True);ds=None
        Path(out).unlink()


def test_palette_and_range_do_not_change_pixels():
    values=np.array([[1.,2],[3.,4.]])
    fig=Figure();canvas=FigureCanvas(fig);ax=fig.add_subplot(111);im=ax.imshow(values)
    controls=MapDisplayControls();display=MatplotlibMapDisplay(canvas,controls)
    controls.palette.setCurrentText("Plasma");controls.automatic.setChecked(False);controls.minimum.setValue(0);controls.maximum.setValue(10)
    display.restyle()
    np.testing.assert_array_equal(im.get_array(),values)
    assert im.get_clim()==(0.,10.)
    assert common_value_range(values,values+10)==(1.,14.)
    masked=np.ma.array([[1.,-9999.],[3.,4.]],mask=[[False,True],[False,False]])
    im.set_data(masked);controls.automatic.setChecked(True);display.restyle()
    assert im.get_clim()==(1.,4.)


def test_optional_sections_and_same_report_source():
    state=ReportState(sections=[ReportSection("required","Validation",mandatory=True,tables=[ReportTable(("Method","RMSE"),(("IDW",1.),))]),ReportSection("optional","Comparison",body="comparison",enabled=False)])
    assert "IDW" in report_html(state) and "comparison" not in report_html(state)
    state.sections[1].enabled=True
    assert "comparison" in report_html(state)
    with tempfile.TemporaryDirectory() as folder:
        for i in range(2):
            path=str(Path(folder)/("report"+str(i)+".pdf"));export_report_pdf(state,path)
            assert Path(path).read_bytes().startswith(b"%PDF") and Path(path).stat().st_size>1000


def test_scoped_and_legacy_enum_feature_detection():
    class Legacy: Value=5
    class Modern:
        class Scope: Value=7
    assert enum_value(Legacy,"Scope","Value")==5
    assert enum_value(Modern,"Scope","Value")==7


def test_python_specific_dependencies_and_nan_snapshot_comparison():
    from bestfitinterpolator.compat import ml_dependency_requirements,arrays_equal_with_nan
    assert "scipy>=1.7,<1.8" in ml_dependency_requirements((3,7))
    assert "scikit-learn>=1.1,<1.4" in ml_dependency_requirements((3,8))
    assert "scikit-learn>=1.4" in ml_dependency_requirements((3,12))
    assert arrays_equal_with_nan([1.,np.nan],[1.,np.nan])
    assert not arrays_equal_with_nan([1.,np.nan],[2.,np.nan])


def test_branding_export_is_complete_reused_and_can_be_disabled():
    from io import BytesIO
    from matplotlib.image import imread
    from bestfitinterpolator.theme import save_figure,style_figure,apply_branding_to_figure
    fig=Figure(figsize=(3.2,2.4));FigureCanvas(fig)
    ax=fig.add_axes((.1,.2,.3,.65));ax.plot([0.,1.],[0.,1.])
    apply_branding_to_figure(fig,enabled=True)
    style_figure(fig);brand=fig._bfi_brand_artist
    style_figure(fig);assert fig._bfi_brand_artist is brand
    output=BytesIO();save_figure(fig,output,format="png",dpi=100,bbox_inches="tight")
    output.seek(0);pixels=imread(output)
    orange=(pixels[:,:,0]>.9)&(pixels[:,:,1]>.35)&(pixels[:,:,1]<.85)&(pixels[:,:,2]<.7)
    ys,xs=np.where(orange)
    assert len(xs)>20 and xs.max()-xs.min()>=10 and ys.max()-ys.min()>=10
    assert xs.max()<pixels.shape[1]-3
    apply_branding_to_figure(fig,enabled=False);style_figure(fig)
    assert fig._bfi_brand_artist is None
