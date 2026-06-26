import numpy as np
from scipy.spatial import distance_matrix
from sklearn.model_selection import KFold

try:
    from .array_shape_utils import ensure_xy_components, ensure_values_1d
except Exception:  # pragma: no cover
    from array_shape_utils import ensure_xy_components, ensure_values_1d  # type: ignore


# IDW Interpolation Function
def idw_interpolation(x, y, z, xi, yi, p, n):
    train_xy = ensure_xy_components(x, y, "training coordinates")
    query_xy = ensure_xy_components(xi, yi, "prediction coordinates")
    z = ensure_values_1d(z, "training values")
    k_neighbors = max(1, min(int(n), train_xy.shape[0]))
    dist = distance_matrix(query_xy, train_xy)
    dist[dist == 0] = 1e-10  # Avoid division by zero
    sorted_indices = np.argsort(dist, axis=1)[:, :k_neighbors]  # Select n neighbors
    dist = np.take_along_axis(dist, sorted_indices, axis=1)
    weights = 1 / dist ** p
    weights /= weights.sum(axis=1)[:, np.newaxis]
    z_neighbors = np.take_along_axis(z[None, :], sorted_indices, axis=1)
    zi = np.sum(weights * z_neighbors, axis=1)
    return zi


# Function for Optimizing p and n
def optimize_idw(x, y, z, k=5):
    train_xy = ensure_xy_components(x, y, "training coordinates")
    z = ensure_values_1d(z, "training values")
    x = train_xy[:, 0]
    y = train_xy[:, 1]
    p_values = np.arange(0.5, 6.5, 0.5)
    n_values = np.arange(4, 17, 1)

    kf = KFold(n_splits=min(k, len(x)), shuffle=True, random_state=42)  # Ajustar n_splits a datos disponibles
    results = []

    all_mae = []
    all_sae = []

    for p in p_values:
        for n in n_values:
            mae_scores = []
            sae_scores = []
            for train_index, test_index in kf.split(x):
                # Validar índices
                if max(train_index) >= len(x) or max(test_index) >= len(x):
                    raise ValueError("KFold indices exceed data bounds. Check data size.")

                x_train, x_test = x[train_index], x[test_index]
                y_train, y_test = y[train_index], y[test_index]
                z_train, z_test = z[train_index], z[test_index]

                z_pred = idw_interpolation(x_train, y_train, z_train, x_test, y_test, p, n)
                mae_scores.append(mean_absolute_error(z_pred, z_test))
                sae_scores.append(std_error(z_pred, z_test))

            avg_mae = np.mean(mae_scores)
            avg_sae = np.mean(sae_scores)
            all_mae.append(avg_mae)
            all_sae.append(avg_sae)
            results.append((p, n, avg_mae, avg_sae))

    max_abs_ae = max(all_mae)
    min_sae = min(all_sae)
    max_sae = max(all_sae)

    best_p, best_n, best_isi = None, None, float('inf')
    final_results = []

    for (p, n, mae, sae) in results:
        isi = calculate_isi(mae, sae, max_abs_ae, min_sae, max_sae)
        final_results.append((p, n, mae, sae, isi))
        if isi < best_isi:
            best_p, best_n, best_isi = p, n, isi

    return best_p, best_n, best_isi, final_results



# Adaptación al plugin
def run_idw_plugin(data, variable_name, polygon_layer, pixel_size):
    # Extraer datos
    x = data['x'].values
    y = data['y'].values
    z = data[variable_name].values

    # Extraer límites del polígono
    xmin, ymin, xmax, ymax = polygon_layer.extent().toRectF().getCoords()
    x_grid = np.arange(xmin, xmax, pixel_size)
    y_grid = np.arange(ymin, ymax, pixel_size)
    xi, yi = np.meshgrid(x_grid, y_grid)

    # Filtrar puntos dentro del polígono
    grid_points = np.c_[xi.ravel(), yi.ravel()]
    polygon = Polygon([(point.x(), point.y()) for point in polygon_layer.getFeatures()])
    mask = np.array([polygon.contains(Point(pt[0], pt[1])) for pt in grid_points])
    xi_within = grid_points[mask][:, 0]
    yi_within = grid_points[mask][:, 1]

    # Optimizar parámetros
    best_p, best_n, _, _ = optimize_idw(x, y, z)

    # Interpolar
    zi = idw_interpolation(x, y, z, xi_within, yi_within, best_p, best_n)

    return xi_within, yi_within, zi, best_p, best_n
