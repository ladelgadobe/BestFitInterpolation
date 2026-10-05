"""Contracts for the first version 1.2 performance and Framework changes."""

import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dense_moran_reference(coords, values, k, permutations, seed):
    diff = coords[:, None, :] - coords[None, :, :]
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)
    np.fill_diagonal(dist2, np.inf)
    neighbors = np.argpartition(dist2, kth=k - 1, axis=1)[:, :k]
    centered = values - float(np.mean(values))
    denominator = float(np.sum(centered ** 2))
    observed = float(np.sum(centered * np.mean(centered[neighbors], axis=1)) / denominator)

    rng = np.random.default_rng(seed)
    simulated = []
    for _ in range(max(19, permutations)):
        permuted = rng.permutation(centered)
        simulated.append(
            float(
                np.sum(permuted * np.mean(permuted[neighbors], axis=1))
                / denominator
            )
        )
    simulated = np.asarray(simulated, dtype=float)
    z_score = float((observed - np.mean(simulated)) / np.std(simulated, ddof=1))
    return observed, z_score


def test_moran_tree_backend_preserves_the_legacy_statistic():
    diagnostics = _load_module("spatial_diagnostics")
    rng = np.random.default_rng(42)
    coords = rng.normal(size=(80, 2))
    values = rng.normal(size=80)

    actual = diagnostics.compute_moran_index_knn(
        coords,
        values,
        k=8,
        n_permutations=39,
        random_seed=20,
    )
    expected_i, expected_z = _dense_moran_reference(
        coords,
        values,
        k=8,
        permutations=39,
        seed=20,
    )

    assert np.isclose(actual["I"], expected_i)
    assert np.isclose(actual["z"], expected_z)
    assert actual["k"] == 8
    assert actual["n"] == 80


def test_dense_framework_policy_bounds_search_but_not_small_data():
    policy = _load_module("performance_policy")

    assert policy.framework_search_limits(500, 10, 12) == (10, 12, False)
    assert policy.framework_search_limits(501, 10, 12) == (3, 8, True)
    assert "Framework data profile: dense" in policy.dense_framework_notice(
        501,
        3,
        8,
    )


def test_idw_chunking_preserves_dense_matrix_results():
    from bestfitinterpolator.IDW_optimized import idw_interpolation

    rng = np.random.default_rng(7)
    x = rng.uniform(0.0, 10.0, 40)
    y = rng.uniform(0.0, 10.0, 40)
    z = rng.normal(size=40)
    xi = np.concatenate([x[:2], rng.uniform(0.0, 10.0, 31)])
    yi = np.concatenate([y[:2], rng.uniform(0.0, 10.0, 31)])

    one_block = idw_interpolation(x, y, z, xi, yi, 2.0, 8, chunk_size=1000)
    many_blocks = idw_interpolation(x, y, z, xi, yi, 2.0, 8, chunk_size=3)

    assert np.allclose(many_blocks, one_block)
    assert np.allclose(many_blocks[:2], z[:2])


def test_framework_ml_validation_no_longer_requires_prior_interpolation():
    framework_source = (ROOT / "framework_tab.py").read_text(encoding="utf-8-sig")
    ml_source = (ROOT / "machine_learning_tab.py").read_text(encoding="utf-8-sig")
    rk_source = (ROOT / "RF_RegressionKriging.py").read_text(encoding="utf-8-sig")

    assert "prepare_framework_validation" in framework_source
    assert "prepare_framework_validation" in ml_source
    assert "prepare_framework_validation" in rk_source
    assert "run_framework_interpolation" in framework_source
    assert 'self.iface = getattr(plugin, "iface", None)' in framework_source
    assert '"source": "framework"' in ml_source
    assert '"source": "framework"' in rk_source
    assert "from .SVM_Interpolation import _make_pipeline" in ml_source
