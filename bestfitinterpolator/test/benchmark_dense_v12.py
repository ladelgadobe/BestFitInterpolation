# -*- coding: utf-8 -*-
"""Standalone dense-core benchmark; run with the QGIS Python interpreter."""

from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from bestfitinterpolator.IDW_optimized import optimize_idw
from bestfitinterpolator.kriging_ordinary import ordinary_kriging_interpolation
from bestfitinterpolator.spatial_diagnostics import compute_moran_index_knn
from bestfitinterpolator.variogram_utils import bin_experimental_variogram, max_pairwise_distance


def timed(label, fn):
    start = time.perf_counter()
    value = fn()
    print(f"{label}: {time.perf_counter() - start:.3f}s")
    return value


def main():
    rng = np.random.default_rng(120)
    n = 2500
    xy = rng.random((n, 2)) * 1000.0
    z = np.sin(xy[:, 0] / 100.0) + np.cos(xy[:, 1] / 120.0) + rng.normal(0, 0.05, n)
    query = rng.random((1000, 2)) * 1000.0
    cutoff = 0.5 * timed("diameter", lambda: max_pairwise_distance(xy[:, 0], xy[:, 1]))
    timed("Moran k=8, 199 permutations", lambda: compute_moran_index_knn(xy, z, k=8, n_permutations=199))
    _, _, info = timed(
        "variogram",
        lambda: bin_experimental_variogram(
            xy[:, 0], xy[:, 1], z, cutoff, cutoff / 15.0, return_info=True
        ),
    )
    print(f"variogram pairs: {info['pairs_used']:,}/{info['pairs_total']:,}")
    timed("IDW optimization", lambda: optimize_idw(xy[:, 0], xy[:, 1], z, k=5))
    pred = timed(
        "local OK, 1,000 predictions",
        lambda: ordinary_kriging_interpolation(
            xy[:, 0], xy[:, 1], z,
            query[:, 0], query[:, 1],
            nugget=0.05, psill=1.0, var_range=300.0, model="Exp",
        ),
    )
    print(f"finite OK predictions: {np.isfinite(pred).sum()}/{pred.size}")


if __name__ == "__main__":
    main()
