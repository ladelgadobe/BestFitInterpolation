#!/usr/bin/env Rscript
# ok_bridge.R
# Reads a JSON input, fits variogram by MoM (WLS/gstat) or REML (geoR),
# runs CV (krige.cv), and writes a JSON output.
# All console messages kept minimal for robust parsing.

suppressPackageStartupMessages({
  library(jsonlite)
  library(sf)
  library(sp)
  library(gstat)
  library(geoR)
  library(hydroGOF)
  library(epiR)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript ok_bridge.R input.json output.json")
}
in_path  <- args[1]
out_path <- args[2]

j <- jsonlite::fromJSON(in_path, simplifyVector = TRUE)

# ---- read points ----
# j$points_path can be shp/gpkg/geojson/csv
read_points <- function(j){
  if (grepl("\\.(shp|gpkg|geojson)$", tolower(j$points_path))) {
    s <- sf::st_read(j$points_path, quiet = TRUE)
    if (!is.null(j$z_field)) {
      if (!(j$z_field %in% names(s))) stop("z_field not in layer")
      z <- s[[j$z_field]]
    } else if (!is.null(j$z_column)) {
      z <- s[[j$z_column]]
    } else stop("No z field specified")
    crs <- sf::st_crs(s)
    # coords
    xy <- sf::st_coordinates(sf::st_geometry(s))
    dados <- data.frame(x = xy[,1], y = xy[,2], z = as.numeric(z))
  } else if (grepl("\\.csv$", tolower(j$points_path))) {
    dados <- read.csv(j$points_path, sep = j$csv_sep %||% ",", stringsAsFactors = FALSE)
    if (!all(c(j$x_col, j$y_col, j$z_col) %in% names(dados))) stop("CSV columns not found")
    dados <- dados[, c(j$x_col, j$y_col, j$z_col)]
    names(dados) <- c("x","y","z")
  } else {
    stop("Unsupported points_path")
  }
  dados <- na.omit(dados)
  sp::coordinates(dados) <- ~ x + y
  dados
}

`%||%` <- function(a,b) if (is.null(a)) b else a

# ---- build experimental variogram ----
build_exp_vario <- function(dados, j){
  cut <- as.numeric(j$cutoff)
  wid <- as.numeric(j$width)
  if (is.na(cut) || is.na(wid) || cut <= 0 || wid <= 0) stop("Invalid cutoff/width")
  vexp <- gstat::variogram(z ~ 1, dados, cutoff = cut, width = wid)
  # Keep only non-empty bins
  vexp <- vexp[is.finite(vexp$gamma) & vexp$npair > 0, ]
  list(
    dist = vexp$dist,
    gamma = vexp$gamma,
    npair = vexp$npair,
    vexp = vexp
  )
}

# ---- initials (Kerry & Oliver style) ----
initial_params <- function(dist, gamma){
  if (length(gamma) < 2L) return(list(co = 0, c = max(gamma,1e-6), a = max(dist,1)))
  ord <- order(dist)
  d <- dist[ord]; g <- gamma[ord]
  topn <- max(1, length(g) %/% 3)
  sill_total <- median(g[(length(g)-topn+1):length(g)], na.rm = TRUE)
  co <- max(g[1], 0)
  c  <- max(sill_total - co, 1e-9)
  # practical range at 95% of sill_total
  target <- 0.95 * sill_total
  idx <- which(g >= target)[1]
  a_pr <- if (is.finite(idx)) d[idx] else max(d, na.rm = TRUE)
  list(co = co, c = c, a = max(a_pr, 1e-6))
}

# ---- map model strings ----
to_gstat_model <- function(m){
  m <- tolower(m)
  if (startsWith(m,"sph")) "Sph" else if (startsWith(m,"exp")) "Exp" else "Gau"
}
to_geor_model <- function(m){
  m <- tolower(m)
  if (startsWith(m,"sph")) "spherical" else if (startsWith(m,"exp")) "exponential" else "gaussian"
}

# ---- WLS fit (gstat) ----
fit_wls <- function(vexp, model, init){
  # gstat::fit.variogram takes model with initials; we use weights ~ 1
  psill <- init$c
  co    <- init$co
  a     <- init$a
  vgm0  <- gstat::vgm(psill = psill, model = model, range = a, nugget = co)
  fit   <- try(gstat::fit.variogram(vexp, vgm0, fit.method = 7), silent = TRUE) # WLS (Cressie)
  if (inherits(fit,"try-error")) {
    # fallback: method=2 (OLS)
    fit <- gstat::fit.variogram(vexp, vgm0, fit.method = 2)
  }
  list(co = fit$psill[1], c = fit$psill[2], a = fit$range[2], vgm = fit)
}

# ---- REML fit (geoR) ----
fit_reml <- function(dados, vexp, model, init){
  # Build geoR geodata
  xy <- sp::coordinates(dados)
  z  <- dados$z
  gd <- geoR::as.geodata(cbind(xy, z))
  # geoR initials: ini.cov.pars = c(partial sill, range)
  fit <- geoR::likfit(
    geodata = gd,
    ini.cov.pars = c(init$c, init$a),
    nugget = max(init$co, 0),
    cov.model = to_geor_model(model),
    lik.method = "REML",
    messages = FALSE
  )
  # Convert to gstat vgm
  gs <- gstat::vgm(psill = as.numeric(fit$sigmasq), model = to_gstat_model(model),
                   range = as.numeric(fit$phi), nugget = as.numeric(fit$nugget))
  list(co = as.numeric(fit$nugget), c = as.numeric(fit$sigmasq), a = as.numeric(fit$phi), vgm = gs)
}

# ---- CV metrics with gstat::krige.cv ----
run_cv <- function(dados, vgm_model){
  kv <- gstat::krige.cv(z ~ 1, locations = dados, model = vgm_model)
  df <- as.data.frame(kv)
  obs  <- as.numeric(df$observed)
  pred <- as.numeric(df$var1.pred)
  # metrics
  r2   <- summary(lm(pred ~ obs))$r.squared
  rmse <- hydroGOF::rmse(pred, obs)
  ccc  <- as.numeric(epiR::epi.ccc(obs, pred)$rho.c[, "est"])
  list(obs = obs, pred = pred, r2 = r2, rmse = rmse, ccc = ccc)
}

# ---- main flow ----
dados <- read_points(j)
ve    <- build_exp_vario(dados, j)
init  <- initial_params(ve$dist, ve$gamma)
gs_model <- to_gstat_model(j$model)

# Fit method: Auto (by N) should be decided in Python, but accept override from JSON
n <- nrow(as.data.frame(dados))
fit_method <- j$fit_method %||% if (n >= 100) "MoM" else "REML"

fit <- if (toupper(fit_method) == "REML") {
  fit_reml(dados, ve$vexp, j$model, init)
} else {
  fit_wls(ve$vexp, gs_model, init)
}

cv <- run_cv(dados, fit$vgm)

# ---- output JSON ----
out <- list(
  method   = fit_method,
  model    = j$model,
  cutoff   = j$cutoff,
  width    = j$width,
  n_lags   = floor(as.numeric(j$cutoff) / as.numeric(j$width)),
  exp_variogram = list(
    dist  = unname(ve$dist),
    gamma = unname(ve$gamma),
    npair = unname(ve$npair)
  ),
  params = list(Co = fit$co, C = fit$c, A = fit$a),
  cv = list(
    r2 = cv$r2, rmse = cv$rmse, ccc = cv$ccc,
    obs = unname(cv$obs), pred = unname(cv$pred)
  )
)

jsonlite::write_json(out, out_path, pretty = FALSE, auto_unbox = TRUE)
