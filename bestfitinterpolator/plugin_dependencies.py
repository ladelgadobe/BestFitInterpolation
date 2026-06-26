# -*- coding: utf-8 -*-
"""
Dependency checks for optional machine learning features.
All code comments are in English.
"""

from qgis.PyQt.QtWidgets import QMessageBox


def check_sklearn(parent=None):
    """
    Check whether scikit-learn is available.

    Returns
    -------
    tuple[bool, str]
        (is_available, error_message)
    """
    try:
        import sklearn  # noqa: F401
        return True, ""
    except Exception as exc:
        msg = (
            "Random Forest requires scikit-learn, but it could not be imported.\n\n"
            "Please install the missing Python dependencies for this plugin.\n"
            "If QPIP is installed, reopen or reactivate the plugin and accept the dependency installation.\n"
            f"\nTechnical details:\n{exc}"
        )
        return False, msg


def show_dependency_error(title, message, parent=None):
    """
    Show a standard dependency error dialog.
    """
    QMessageBox.warning(parent, title, message)