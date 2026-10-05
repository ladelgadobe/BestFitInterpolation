"""Exact aligned-grid differences, with independent preview/display state."""
from dataclasses import dataclass, field
import os
import tempfile
import numpy as np


@dataclass
class MapComparisonState:
    method_a: str = ""
    method_b: str = ""
    palette_a: str = "viridis"
    palette_b: str = "viridis"
    same_palette: bool = True
    same_range: bool = True
    same_extent: bool = True
    value_range: tuple = (0.,1.)
    value_range_b: tuple = (0.,1.)
    scale: float = 0.
    view_extent: tuple = field(default_factory=tuple)
    difference_path: str = ""
    statistics: dict = field(default_factory=dict)
    include_report: bool = False
    previews: tuple = field(default_factory=tuple)
    grid: dict = field(default_factory=dict)


def check_grids(a,b):
    if a["shape"]!=b["shape"]: raise ValueError("Raster dimensions differ; regenerate both methods on the same Framework grid.")
    if not a.get("crs") or not b.get("crs"): raise ValueError("Both rasters must have a declared CRS.")
    if a["crs"]!=b["crs"]:
        from osgeo import osr
        sa,sb=osr.SpatialReference(),osr.SpatialReference(); sa.SetFromUserInput(a["crs"]); sb.SetFromUserInput(b["crs"])
        if not sa.IsSame(sb): raise ValueError("Raster CRS differs. No resampling was performed.")
    ga,gb=np.array(a["transform"]),np.array(b["transform"])
    pixel=max(abs(ga[1]),abs(ga[5]),1.e-12)
    if not np.allclose(ga,gb,rtol=0.,atol=pixel*1.e-7):
        raise ValueError("Raster extent, pixel size or alignment differs. Regenerate on the same grid; no silent resampling is permitted.")


def difference_arrays(a,b,nodata_a=None,nodata_b=None):
    a,b=np.asarray(a,float),np.asarray(b,float)
    if a.shape!=b.shape: raise ValueError("Array dimensions differ")
    valid=np.isfinite(a)&np.isfinite(b)
    if nodata_a is not None: valid &= a!=nodata_a
    if nodata_b is not None: valid &= b!=nodata_b
    diff=np.full(a.shape,np.nan); diff[valid]=a[valid]-b[valid]
    return diff


def difference_statistics(diff):
    values=np.asarray(diff)[np.isfinite(diff)]
    return dict(count=int(values.size),mean=float(np.mean(values)) if values.size else np.nan,
        median=float(np.median(values)) if values.size else np.nan,minimum=float(np.min(values)) if values.size else np.nan,
        maximum=float(np.max(values)) if values.size else np.nan)


def compare_rasters(path_a,path_b,cancelled=lambda:False):
    from osgeo import gdal
    da,db=gdal.Open(path_a),gdal.Open(path_b)
    if da is None or db is None: raise ValueError("Could not open both raster results.")
    def metadata(ds): return dict(shape=(ds.RasterYSize,ds.RasterXSize),crs=ds.GetProjection(),transform=ds.GetGeoTransform())
    ma,mb=metadata(da),metadata(db); check_grids(ma,mb)
    rows,cols=ma["shape"]
    fd,diff_path=tempfile.mkstemp(prefix="bfi_difference_",suffix=".tif"); os.close(fd)
    out=gdal.GetDriverByName("GTiff").Create(diff_path,cols,rows,1,gdal.GDT_Float64,options=["TILED=YES","COMPRESS=LZW","BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(ma["transform"]); out.SetProjection(ma["crs"]); out.GetRasterBand(1).SetNoDataValue(float("nan"))
    fd,work_path=tempfile.mkstemp(prefix="bfi_difference_values_",suffix=".dat"); os.close(fd)
    mm=np.memmap(work_path,dtype=float,mode="w+",shape=(rows*cols,))
    ba,bb=da.GetRasterBand(1),db.GetRasterBand(1)
    count=0; total=0.; low=np.inf; high=-np.inf
    map_lows=[np.inf,np.inf]; map_highs=[-np.inf,-np.inf]
    try:
        for y in range(0,rows,128):
            if cancelled(): raise InterruptedError("Map comparison cancelled")
            h=min(128,rows-y)
            a=ba.ReadAsArray(0,y,cols,h).astype(float); b=bb.ReadAsArray(0,y,cols,h).astype(float)
            a[ba.GetMaskBand().ReadAsArray(0,y,cols,h)==0]=np.nan
            b[bb.GetMaskBand().ReadAsArray(0,y,cols,h)==0]=np.nan
            for index,(array,band) in enumerate(((a,ba),(b,bb))):
                nodata=band.GetNoDataValue()
                if nodata is not None: array[array==nodata]=np.nan
                finite=array[np.isfinite(array)]
                if finite.size:
                    map_lows[index]=min(map_lows[index],float(finite.min()))
                    map_highs[index]=max(map_highs[index],float(finite.max()))
            diff=difference_arrays(a,b); out.GetRasterBand(1).WriteArray(diff,0,y)
            values=diff[np.isfinite(diff)]; size=int(values.size)
            if size:
                mm[count:count+size]=values; count+=size
                total+=float(np.sum(values,dtype=np.float64)); low=min(low,float(values.min())); high=max(high,float(values.max()))
        out.FlushCache()
        if cancelled(): raise InterruptedError("Map comparison cancelled")
        # Exact median partitions the packed disk-backed values without a full copy.
        statistics=dict(count=count,mean=total/count if count else np.nan,
                        median=float(np.median(mm[:count],overwrite_input=True)) if count else np.nan,
                        minimum=low if count else np.nan,maximum=high if count else np.nan)
        step=max(1,int(np.ceil(max(rows,cols)/650.)))
        # Preview sampling is explicit; signed differences and statistics use all pixels.
        ri=np.arange(0,rows,step); ci=np.arange(0,cols,step)
        a=np.vstack([ba.ReadAsArray(0,int(y),cols,1)[0,ci] for y in ri]).astype(float)
        b=np.vstack([bb.ReadAsArray(0,int(y),cols,1)[0,ci] for y in ri]).astype(float)
        for array,band in ((a,ba),(b,bb)):
            nodata=band.GetNoDataValue()
            if nodata is not None: array[array==nodata]=np.nan
            mask=np.vstack([band.GetMaskBand().ReadAsArray(0,int(y),cols,1)[0,ci] for y in ri])
            array[mask==0]=np.nan
        difference=out.GetRasterBand(1)
        d=np.vstack([difference.ReadAsArray(0,int(y),cols,1)[0,ci] for y in ri]).astype(float)
        previews=(a,b,d)
        ma["preview_step"]=step
        ma["value_range_a"]=(map_lows[0],map_highs[0])
        ma["value_range_b"]=(map_lows[1],map_highs[1])
        return previews,statistics,ma,diff_path
    except Exception:
        out=None
        if os.path.isfile(diff_path): os.remove(diff_path)
        raise
    finally:
        del mm
        if os.path.isfile(work_path): os.remove(work_path)
        da=db=out=None
