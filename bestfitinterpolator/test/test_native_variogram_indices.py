"""Exercise 32-bit bin indices even when CI uses a 64-bit interpreter."""
import numpy as np
from bestfitinterpolator import variogram_utils as variogram


class Native32NumPy:
    intp = np.int32

    def __init__(self):
        self.calls = 0
        self.count_dtypes = []

    def __getattr__(self, name):
        return getattr(np, name)

    def zeros(self, shape, dtype=float):
        if np.issubdtype(dtype, np.integer):
            self.count_dtypes.append(np.dtype(dtype))
        return np.zeros(shape, dtype=dtype)

    def bincount(self, bins, **kwargs):
        assert bins.dtype == np.dtype(np.int32), "32-bit bincount received non-native indices"
        self.calls += 1
        # Modern NumPy accepts these too; values and accumulation are unchanged.
        return np.bincount(bins, **kwargs)


def run_with_32bit_indices(args, **kwargs):
    original = variogram.np
    native = Native32NumPy()
    try:
        variogram.np = native
        result = variogram.bin_experimental_variogram(*args, return_info=True, **kwargs)
    finally:
        variogram.np = original
    assert native.calls > 0
    assert native.count_dtypes == [np.dtype(np.int64)], "Pair counts must retain 64-bit storage"
    return result


def test_exact_variogram_accepts_32bit_native_indices():
    args = ([0., 1., 2., 4.], [0., 0., 0., 0.], [0., 2., 3., 7.], 4., 1.)
    lags, gamma, info = run_with_32bit_indices(args)
    np.testing.assert_array_equal(lags, [1., 2., 3.5])
    np.testing.assert_array_equal(gamma, [1.25, 6.25, 18.5])
    assert not info['sampled'] and info['pairs_total'] == 6


def test_sampled_variogram_accepts_32bit_native_indices_without_numerical_change():
    rng = np.random.default_rng(12)
    xy = rng.uniform(0., 20., (80, 2))
    z = np.sin(xy[:, 0]) + xy[:, 1]
    args = (xy[:, 0], xy[:, 1], z, 15., 2.)
    expected = variogram.bin_experimental_variogram(*args, max_pairs=130, return_info=True)
    actual = run_with_32bit_indices(args, max_pairs=130)
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
    assert actual[2] == expected[2] and actual[2]['sampled']


def test_condensed_pair_ordinals_keep_64bit_precision():
    # Pair ordinals can exceed int32 even though row and bin indices cannot.
    n = 100000
    ordinal = np.array([3000000000, n * (n - 1) // 2 - 1], dtype=np.int64)
    i, j = variogram._condensed_indices_to_pairs(ordinal, n)
    recovered = n * i - i * (i + 1) // 2 + j - i - 1
    np.testing.assert_array_equal(recovered, ordinal)
    assert i.dtype == j.dtype == np.dtype(np.int64)
    assert np.all((0 <= i) & (i < j) & (j < n))
