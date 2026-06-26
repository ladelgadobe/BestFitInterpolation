#!/usr/bin/env Rscript

# Usage: Rscript ok_r_integration.R puntos.shp poligono.shp pixel_size salida.tif

args <- commandArgs(trailingOnly = TRUE)
if(length(args) < 4){
  stop("Usage: Rscript ok_r_integration.R <points_shp> <polygon_shp> <pixel_size> <output_tif>")
}

points_shp <- args[1]
polygon_shp <- args[2]
pixel_size <- as.numeric(args[3])
output_tif <- args[4]

suppressMessages({
  library(sf)
  library(terra)
  library(gstat)
})

# Leer datos de puntos y polígono
points <- st_read(points_shp, quiet = TRUE)
poly <- st_read(polygon_shp, quiet = TRUE)

# --- SELECCIÓN DE VARIABLE ---
# Usa el primer campo numérico del shapefile de puntos
# Si necesitas otro, cambia aquí:
num_fields <- sapply(points, is.numeric)
if(sum(num_fields) == 0) stop("No numeric fields found in points layer.")
var_name <- names(points)[which(num_fields)[1]]

cat("Usando variable:", var_name, "\n")

# Convertir a objeto Spatial para gstat
points_sp <- as(points, "Spatial")
poly_sp <- as(poly, "Spatial")

# Crear grilla dentro del polígono
bbox <- st_bbox(poly)
xseq <- seq(bbox$xmin, bbox$xmax, by=pixel_size)
yseq <- seq(bbox$ymin, bbox$ymax, by=pixel_size)
grd <- expand.grid(x = xseq, y = yseq)
grd_sf <- st_as_sf(grd, coords = c("x", "y"), crs = st_crs(poly))
inside <- st_within(grd_sf, poly, sparse = FALSE)[,1]
grd_in <- grd_sf[inside,]

if(nrow(grd_in) == 0) stop("No grid points inside the polygon.")

# Kriging: ajustar y predecir
vgm_mod <- variogram(as.formula(paste(var_name, "~1")), points_sp)
fit <- fit.variogram(vgm_mod, vgm("Sph"))
kriged <- krige(as.formula(paste(var_name, "~1")), points_sp, as(grd_in, "Spatial"), model=fit)

# Rasterizar y exportar GeoTIFF
rast_out <- rast(ext=ext(poly), resolution=pixel_size, crs=st_crs(poly)$wkt)
values(rast_out) <- NA
xy <- coordinates(kriged)
cell <- cellFromXY(rast_out, xy)
values(rast_out)[cell] <- kriged$var1.pred

writeRaster(rast_out, output_tif, overwrite=TRUE)

cat("Kriging finalizado. Raster exportado en:", output_tif, "\n")
