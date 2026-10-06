"""Copied map views preserve visible content on historical Matplotlib releases."""
from unittest.mock import patch
import numpy as np
from matplotlib.figure import Figure
from bestfitinterpolator.mpl_compat import clone_figure


def test_historical_transform_clone_preserves_map_and_independence():
    figure = Figure()
    axis = figure.subplots()
    values = np.ma.array([[1., 2.], [3., 4.]], mask=[[False, True], [False, False]])
    axis.imshow(values, cmap='plasma', vmin=1., vmax=5., extent=(2., 4., 6., 8.))
    axis.set_xlim(2.5, 3.5)
    axis.set_title('Executed TPS')
    with patch('copy.deepcopy', side_effect=NotImplementedError('Historical TransformNode')):
        copied = clone_figure(figure)
    image = copied.axes[0].images[0]
    np.testing.assert_array_equal(image.get_array().mask, values.mask)
    np.testing.assert_allclose(image.get_array().compressed(), values.compressed())
    assert image.get_cmap().name == 'plasma' and image.get_clim() == (1., 5.)
    assert copied.axes[0].get_xlim() == (2.5, 3.5)
    assert copied.axes[0].get_title() == 'Executed TPS'
    image.set_cmap('viridis')
    assert axis.images[0].get_cmap().name == 'plasma'
