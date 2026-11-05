"""Framework uses the same bounded grid search as the individual windows."""
from .localization import _dialog, _new, _ui
from .ml_search_settings import method_defaults
from copy import deepcopy


def search_settings(saved=None):
    defaults = {m: method_defaults(m) for m in ('RF', 'SVM', 'RK')}
    result = dict(schema=3, strategy="randomized",
                  grids={m: v['grid_params'] for m, v in defaults.items()},
                  budgets={m: dict(folds=v['folds'], iterations=v['iterations']) for m, v in defaults.items()})
    if saved:
        saved = deepcopy(saved)
        # Prior provisional builds used a different SVM convention. Start from
        # the effective V2.0 individual defaults when upgrading that settings schema.
        if saved.get('schema', 1) < 3 and 'SVM' in saved.get('grids', {}):
            saved['grids']['SVM'] = deepcopy(defaults['SVM']['grid_params'])
        for method in defaults:
            result['grids'][method].update(saved.get('grids', {}).get(method, {}))
            result['budgets'][method].update(saved.get('budgets', {}).get(method, {}))
            for key in ('folds', 'iterations'):
                if key in saved:
                    result['budgets'][method][key] = saved[key]
    # Old exhaustive settings must never bypass the individual iteration limit.
    for method in defaults:
        budget = result['budgets'][method]
        budget['folds'] = max(2, int(budget['folds']))
        budget['iterations'] = max(1, int(budget['iterations']))
        for name, values in result['grids'][method].items():
            if values['max'] < values['min'] or values['step'] <= 0:
                raise ValueError("Search maximum must be at least the minimum, and step must be positive.")
    return result


def for_method(settings, method):
    values = search_settings(settings)
    return dict(grid_params=deepcopy(values['grids'][method]), **values['budgets'][method])


def current_settings(framework):
    return search_settings(getattr(framework, "_ml_search_settings", None) or framework.state.__dict__.get("ml_search_settings"))


def install_search_controls(framework):
    from qgis.PyQt.QtWidgets import QPushButton
    layout = getattr(framework.dlg, "horizontalLayout_frameworkValidationButtonsTop", None)
    if layout is None or hasattr(framework, "ml_search_button"):
        return
    button = _new(QPushButton, framework.dlg)
    button.setObjectName("btnFrameworkMLSearch")
    _ui(button, 'setToolTip', "Automatic RF, SVM and RK hyperparameter search for Framework validation and interpolation. Configure it here without opening individual method tabs. Execution details are recorded in the report.")
    button.clicked.connect(lambda: edit_search_settings(framework))
    layout.insertWidget(1, button)
    framework.ml_search_button = button
    refresh_search_controls(framework)


def refresh_search_controls(framework):
    button = getattr(framework, "ml_search_button", None)
    if button is not None:
        _ui(button, 'setText', "ML grid search")


def edit_search_settings(framework):
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QSpinBox,
        QDoubleSpinBox, QTabWidget, QWidget, QGridLayout, QLabel, QDialogButtonBox, QMessageBox)
    from .compat import enum_value, qt_exec
    from .theme import apply_theme
    saved = current_settings(framework)
    dialog = QDialog(framework.dlg)
    _ui(dialog, 'setWindowTitle', "Framework automatic ML search")
    root = QVBoxLayout(dialog)
    intro = _new(QLabel, "Framework uses the same reproducible grid sampling and default ranges as the individual windows. The iteration limit bounds the number of combinations evaluated for each method. These settings can be changed here without opening the individual windows.")
    intro.setWordWrap(True); root.addWidget(intro)
    tabs = QTabWidget(); controls = {}; budgets = {}
    for method in ("RF", "SVM", "RK"):
        page = QWidget(); page_layout = QVBoxLayout(page); form = QFormLayout()
        folds = QSpinBox(); folds.setRange(2, 20 if method == 'RK' else 10)
        folds.setValue(saved['budgets'][method]['folds'])
        iterations = QSpinBox(); iterations.setRange(1, {'RF': 200, 'SVM': 100, 'RK': 1000}[method])
        iterations.setValue(saved['budgets'][method]['iterations'])
        _ui(form, 'addRow', "Search CV folds", folds)
        _ui(form, 'addRow', "Maximum sampled combinations", iterations)
        page_layout.addLayout(form); budgets[method] = dict(folds=folds, iterations=iterations)
        grid = QGridLayout(); page_layout.addLayout(grid)
        for column, title in enumerate(("Parameter", "Minimum", "Maximum", "Step")):
            grid.addWidget(_new(QLabel, title), 0, column)
        controls[method] = {}
        for row, (name, values) in enumerate(saved['grids'][method].items(), 1):
            grid.addWidget(_new(QLabel, name), row, 0); controls[method][name] = {}
            for column, key in enumerate(('min', 'max', 'step'), 1):
                widget = QDoubleSpinBox() if method == 'SVM' else QSpinBox()
                if method == 'SVM':
                    widget.setDecimals(6)
                    widget.setRange(0. if name == 'epsilon' and key != 'step' else .000001, 999999.)

                else:
                    widget.setRange(1, 100000)
                widget.setValue(values[key]); grid.addWidget(widget, row, column)
                controls[method][name][key] = widget
        page_layout.addStretch(1)
        _ui(tabs, 'addTab', page, "RK RF trend" if method == 'RK' else method)
    root.addWidget(tabs)
    note = _new(QLabel, "The parameter ranges and search routines follow the individual V2.0 windows. RF/RK use MAE and SVM uses RMSE. The iteration limit bounds the combinations evaluated. The report records the effective values and any completed-search reuse.")
    note.setWordWrap(True); root.addWidget(note)
    buttons = QDialogButtonBox(enum_value(QDialogButtonBox, 'StandardButton', 'Ok') | enum_value(QDialogButtonBox, 'StandardButton', 'Cancel') | enum_value(QDialogButtonBox, 'StandardButton', 'RestoreDefaults'))
    _ui(buttons.button(enum_value(QDialogButtonBox, 'StandardButton', 'RestoreDefaults')), 'setText', 'Restore Defaults')
    def populate_defaults():
        defaults = search_settings()
        for method, parameters in controls.items():
            for name, fields in parameters.items():
                for key, widget in fields.items(): widget.setValue(defaults['grids'][method][name][key])
            for key, widget in budgets[method].items(): widget.setValue(defaults['budgets'][method][key])
    buttons.button(enum_value(QDialogButtonBox, 'StandardButton', 'RestoreDefaults')).clicked.connect(populate_defaults)
    def accept():
        values = dict(schema=3, budgets={m: {k: w.value() for k, w in b.items()} for m, b in budgets.items()},
            grids={m: {n: {k: w.value() for k, w in f.items()} for n, f in p.items()} for m, p in controls.items()})
        try:
            dialog.settings = search_settings(values)
        except ValueError as error:
            _dialog(QMessageBox.warning, dialog, "Search settings", str(error)); return
        dialog.accept()
    buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); root.addWidget(buttons)
    apply_theme(dialog); dialog.resize(690, 510)
    if qt_exec(dialog) == enum_value(QDialog, 'DialogCode', 'Accepted'):
        framework._ml_search_settings = dialog.settings
        framework.state.__dict__['ml_search_settings'] = dialog.settings
        refresh_search_controls(framework)
