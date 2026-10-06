"""Copied map views preserve visible content on historical Matplotlib releases."""
from unittest.mock import patch
import unittest
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.transforms import TransformNode
from bestfitinterpolator.mpl_compat import clone_figure, FigureCanvas


def test_historical_transform_clone_preserves_map_and_independence():
    figure = Figure()
    axis = figure.subplots()
    values = np.ma.array([[1., 2.], [3., 4.]], mask=[[False, True], [False, False]])
    axis.imshow(values, cmap='plasma', vmin=1., vmax=5., extent=(2., 4., 6., 8.))
    axis.set_xlim(2.5, 3.5)
    axis.set_title('Executed TPS')
    with patch.object(TransformNode, '__deepcopy__',
                      side_effect=NotImplementedError('Historical TransformNode'), create=True):
        copied = clone_figure(figure)
    image = copied.axes[0].images[0]
    np.testing.assert_array_equal(image.get_array().mask, values.mask)
    np.testing.assert_allclose(image.get_array().compressed(), values.compressed())
    assert image.get_cmap().name == 'plasma' and image.get_clim() == (1., 5.)
    assert copied.axes[0].get_xlim() == (2.5, 3.5)
    assert copied.axes[0].get_title() == 'Executed TPS'
    image.set_cmap('viridis')
    assert axis.images[0].get_cmap().name == 'plasma'


class FigureCloneGraphTest(unittest.TestCase):
    def test_artists_transforms_canvas_callbacks_and_cycles_are_independent(self):
        figure = Figure()
        canvas = FigureCanvas(figure)
        axis = figure.subplots()
        values = np.ma.array([[1., 2.], [3., 4.]], mask=[[0, 1], [0, 0]])
        image = axis.imshow(values, cmap='plasma', vmin=0., vmax=5.)
        line, = axis.plot([0., 1.], [1., 0.])
        points = axis.scatter([.2, .8], [.3, .7], c=[1., 3.])
        patch_artist = axis.add_patch(Rectangle((.1, .2), .2, .3))
        axis.set_title('Original map')
        figure.colorbar(image, ax=axis)
        canvas.draw()
        source_events = []
        connection = canvas.mpl_connect('draw_event', lambda event: source_events.append(event))
        source_transform = axis.transData.transform([[0., 0.], [1., 1.]])
        source_size = figure.get_size_inches().copy()
        source_dpi = figure.dpi
        source_limits = axis.get_xlim()
        try:
            # Exercise both the runtime's normal path and a legacy transform refusal.
            for historical in (False, True):
                with self.subTest(historical=historical):
                    if historical:
                        with patch.object(TransformNode, '__deepcopy__',
                                          side_effect=NotImplementedError('Historical TransformNode'),
                                          create=True):
                            cloned = clone_figure(figure)
                    else:
                        cloned = clone_figure(figure)
                    self.assertIsNot(cloned, figure)
                    self.assertIsNot(cloned.canvas, canvas)
                    self.assertIsNot(cloned.axes[0], axis)
                    self.assertIs(cloned.axes[0].figure, cloned)
                    self.assertIsNot(cloned.axes[0].transData, axis.transData)
                    copied_image = cloned.axes[0].images[0]
                    self.assertIsNot(copied_image, image)
                    self.assertIsNot(copied_image.norm, image.norm)
                    self.assertIs(cloned.axes[1]._colorbar.mappable, copied_image)
                    np.testing.assert_array_equal(copied_image.get_array().mask, values.mask)
                    np.testing.assert_allclose(copied_image.get_array().compressed(), values.compressed())
                    np.testing.assert_allclose(cloned.axes[0].transData.transform([[0., 0.], [1., 1.]]), source_transform)
                    if hasattr(figure, '_cachedRenderer'):
                        self.assertIsNone(cloned._cachedRenderer)
                    copied_canvas = FigureCanvas(cloned)
                    copied_canvas._bfi_display_source = True
                    copied_events = []
                    copied_connection = copied_canvas.mpl_connect('draw_event', lambda event: copied_events.append(event))
                    try:
                        self.assertIs(cloned.canvas.figure, cloned)
                        self.assertIsNot(copied_canvas.callbacks, canvas.callbacks)
                        copied_canvas.draw()
                        self.assertEqual(len(copied_events), 1)
                        self.assertEqual(source_events, [])
                        copied_image.get_array()[0, 0] = 99.
                        copied_image.set_cmap('viridis')
                        copied_image.set_clim(-2., 9.)
                        cloned.axes[1]._colorbar.update_normal(copied_image)
                        cloned.axes[0].lines[0].set_ydata([5., 6.])
                        cloned.axes[0].collections[0].set_offsets([[4., 5.]])
                        cloned.axes[0].patches[0].set_xy((4., 5.))
                        cloned.axes[0].set_title('Changed copy')
                        cloned.axes[0].set_xlim(-3., 3.)
                        cloned.set_size_inches(8., 6.)
                        cloned.set_dpi(120.)
                        copied_canvas.draw()
                        self.assertEqual(image.get_cmap().name, 'plasma')
                        self.assertEqual(image.get_clim(), (0., 5.))
                        self.assertEqual(image.get_array()[0, 0], 1.)
                        self.assertEqual(axis.get_title(), 'Original map')
                        self.assertEqual(axis.get_xlim(), source_limits)
                        self.assertEqual(patch_artist.get_xy(), (.1, .2))
                        self.assertEqual(figure.dpi, source_dpi)
                        np.testing.assert_array_equal(line.get_ydata(), [1., 0.])
                        np.testing.assert_array_equal(points.get_offsets(), [[.2, .3], [.8, .7]])
                        np.testing.assert_array_equal(figure.get_size_inches(), source_size)
                        np.testing.assert_allclose(axis.transData.transform([[0., 0.], [1., 1.]]), source_transform)
                        self.assertEqual(source_events, [])
                        cloned.axes[0].lines[0].remove()
                        cloned.axes[0].patches[0].remove()
                        self.assertEqual(len(cloned.axes[0].lines), 0)
                        self.assertEqual(len(cloned.axes[0].patches), 0)
                        self.assertEqual(len(axis.lines), 1)
                        self.assertEqual(len(axis.patches), 1)
                    finally:
                        copied_canvas.mpl_disconnect(copied_connection)
                        copied_canvas.close()
        finally:
            canvas.mpl_disconnect(connection)
            canvas.close()
