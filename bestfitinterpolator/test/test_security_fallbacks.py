"""Recoverable UI and metadata failures retain their established fallbacks."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
# Patch the controller's Qt class even when other tests install import doubles.
from bestfitinterpolator.BestFitInterpolator import BestFitInterpolator, BestFitInterpolatorDialog, QMessageBox
from bestfitinterpolator.machine_learning_tab import MachineLearningTabController
from bestfitinterpolator.compat import LOG, enum_value


class SecurityFallbackTest(unittest.TestCase):
    def test_close_confirmation_errors_still_close_and_reset_the_session(self):
        for error in (AttributeError('Missing Qt member'), TypeError('Qt argument mismatch'),
                      RuntimeError('Deleted Qt wrapper')):
            with self.subTest(error=type(error).__name__):
                plugin = SimpleNamespace(_on_dialog_closed=Mock())
                owner = SimpleNamespace(_bfi_plugin=plugin)
                event = SimpleNamespace(ignore=Mock(), accept=Mock())
                with patch.object(QMessageBox, 'question', side_effect=error), patch.object(LOG, 'debug') as debug:
                    BestFitInterpolatorDialog.closeEvent(owner, event)
                plugin._on_dialog_closed.assert_called_once_with()
                event.accept.assert_called_once_with()
                event.ignore.assert_not_called()
                debug.assert_called_once()

    def test_close_confirmation_acceptance_and_cancellation_are_unchanged(self):
        for answer in ('Yes', 'No'):
            with self.subTest(answer=answer):
                plugin = SimpleNamespace(_on_dialog_closed=Mock())
                event = SimpleNamespace(ignore=Mock(), accept=Mock())
                with patch.object(QMessageBox, 'question', return_value=enum_value(QMessageBox, 'StandardButton', answer)):
                    BestFitInterpolatorDialog.closeEvent(SimpleNamespace(_bfi_plugin=plugin), event)
                if answer == 'Yes':
                    plugin._on_dialog_closed.assert_called_once_with()
                    event.accept.assert_called_once_with()
                    event.ignore.assert_not_called()
                else:
                    plugin._on_dialog_closed.assert_not_called()
                    event.ignore.assert_called_once_with()
                    event.accept.assert_not_called()

    def test_crs_precheck_errors_still_run_the_blocking_coverage_check(self):
        for error in (AttributeError('Missing CRS API'), TypeError('CRS call mismatch'),
                      RuntimeError('Deleted QGIS wrapper')):
            for counts, allowed in (((5, 2), True), ((5, 5), False)):
                with self.subTest(error=type(error).__name__, counts=counts):
                    points = SimpleNamespace(crs=Mock(side_effect=error))
                    polygon = SimpleNamespace(crs=Mock())
                    owner = SimpleNamespace(dlg=None, _point_polygon_coverage_counts=Mock(return_value=counts))
                    with patch.object(QMessageBox, 'critical') as critical, patch.object(LOG, 'debug') as debug:
                        actual = BestFitInterpolator._validate_interpolation_spatial_coverage(owner, points, polygon, 'value')
                    self.assertEqual(actual, allowed)
                    owner._point_polygon_coverage_counts.assert_called_once_with(points, polygon, 'value')
                    self.assertEqual(critical.call_count, int(not allowed))
                    debug.assert_called_once()

    def test_color_limits_use_valid_metadata_and_preserve_fallback_math(self):
        limits = MachineLearningTabController._grid_color_limits
        self.assertEqual(limits({'value_limits': ('1', '4')}, object()), (1., 4.))
        for primary in (None, [1.], ('bad', 4), (None, 4), (10**1000, 4),
                        (np.nan, 4), (1, np.inf), (4, 1), (1, 1)):
            with self.subTest(primary_type=type(primary).__name__):
                actual = limits({'value_limits': primary}, [-10., 0., 10., np.nan, np.inf])
                self.assertEqual(actual, (-10.4, 10.4))
        self.assertEqual(limits(None, [-10., 0., 10.]), (-10.4, 10.4))
        self.assertIsNone(limits({}, [np.nan, np.inf]))
        self.assertIsNone(limits({}, [3., 3.]))
