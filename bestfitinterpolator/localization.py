"""Offline presentation translations; calculation identifiers remain in English.

Catalogs use full strings or {p0}, {p1} placeholders for formatted values.
Only plugin-owned presentation calls are registered. QGIS and user data are
never translated globally. Combo source text is retained in a separate role.
"""
import html
import json
import os
import re
import weakref
from functools import lru_cache
from html.parser import HTMLParser
from qgis.PyQt.QtCore import QObject, QSettings, QTimer, QEvent, QTranslator
from qgis.PyQt.QtWidgets import (QWidget, QComboBox, QLabel, QHBoxLayout,
    QAbstractButton, QGroupBox, QTabWidget, QApplication, QStyledItemDelegate)
from .compat import enum_value, is_alive

LANGUAGES = (('en', 'English'), ('es', 'Español'), ('pt_BR', 'Português'))
SETTING = 'BestFitInterpolator/language'
SOURCE_ROLE = 256 + 173
_language = 'en'
_objects = weakref.WeakSet()
_catalog_path = os.path.join(os.path.dirname(__file__), 'i18n', 'catalog.json')
with open(_catalog_path, encoding='utf-8') as _file:
    CATALOG = json.load(_file)


def normalize_language(value):
    value = str(value or '').lower().replace('-', '_')
    return 'pt_BR' if value.startswith('pt') else ('es' if value.startswith('es') else 'en')


def language():
    return _language


def _pattern(source):
    pieces = re.split(r'(\{p\d+\})', source)
    names = []; expression = ''
    for piece in pieces:
        if re.fullmatch(r'\{p\d+\}', piece):
            name = piece[1:-1]
            expression += '(?P<' + name + '>.*?)' if name not in names else '(?P=' + name + ')'
            names.append(name)
        else:
            expression += re.escape(piece)
    return re.compile(expression, re.S), names


_templates = [(source, values, _pattern(source)[0]) for source, values in CATALOG.items() if re.search(r'\{p\d+\}', source)]
# Specific sentences take precedence over short generic templates.
_templates.sort(key=lambda row: len(re.sub(r'\{p\d+\}', '', row[0])), reverse=True)
_semantic_templates = {
    'Theoretical ({p0})',
    'Based on your data: n = {p0} | MI p = {p1} | Pattern = {p2} | SDI = {p3} | Recommended: {p4}',
    'Framework interpolation and validation: {p0} data profile ({p1} valid samples).',
    'Current selection: {p0} valid samples → {p1}.',
    'Best Fit Interpolator classifies the selected point dataset by valid sample count:\n\n• Normal: up to {p0} valid samples.\n• Dense: {p1} to {p2} valid samples.\n• Massive: more than {p3} valid samples.\n\n{p4}\n\n{p5}',
    'Massive mode has no fixed sample-count stop and includes productivity datasets around {p0}+ samples. Practical runtime still depends on sample count, raster grid cells, covariates, and the selected method.{p1}',
}


@lru_cache(maxsize=4096)
def _translated(text, code):
    if code == 'en' or not text: return text
    values = CATALOG.get(text)
    if values is not None: return values.get(code, text)
    numbered = re.fullmatch(r'(\d+\.\s+)(.+)', text, re.S)
    if numbered:
        translated = _translated(numbered.group(2), code)
        if translated != numbered.group(2): return numbered.group(1) + translated
    if text.endswith(':'):
        translated = _translated(text[:-1], code)
        if translated != text[:-1]: return translated + ':'
    if text.endswith('.') and text[:-1] in CATALOG:
        return _translated(text[:-1], code) + '.'
    if '&' in text and len(text) < 24:
        translated = _translated(text.replace('&', ''), code)
        if translated != text.replace('&', ''): return translated
    stripped = text.strip()
    if stripped != text:
        translated = _translated(stripped, code)
        if translated != stripped: return text[:len(text)-len(text.lstrip())] + translated + text[len(text.rstrip()):]
    for source, values, pattern in _templates:
        match = pattern.fullmatch(text)
        if match:
            translated = values.get(code, source)
            def replacement(token):
                captured = match.group(token.group()[1:-1])
                return _translated(captured, code) if source in _semantic_templates else captured
            return re.sub(r'\{p\d+\}', replacement, translated)
    # Multi-line dialogs retain their original layout and protected values.
    if '\n' in text:
        return '\n'.join(_translated(part, code) for part in text.split('\n'))
    if ': ' in text:
        prefix, value = text.split(': ', 1)
        if prefix in CATALOG:
            if prefix in ('Mode', 'Spatial pattern', 'SDI status', 'Performance profile', 'Decision path', 'Interpolated', 'OK fit'):
                value = _translated(value, code)
            return _translated(prefix, code) + ': ' + value
    return text


class CatalogTranslator(QTranslator):
    """Scoped Qt translator backed by the bundled, human-readable catalog."""
    def translate(self, context, source, disambiguation=None, n=-1):
        return _translated(source, _language) if context == 'BestFitInterpolator' else ''


_translator = CatalogTranslator()


def tr(value):
    return _translator.translate('BestFitInterpolator', value) if isinstance(value, str) else value


class _HtmlTranslation(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False); self.parts = []; self.protected = 0
    def handle_starttag(self, tag, attrs):
        self.parts.append(self.get_starttag_text())
        if tag in ('style', 'script') or any(key == 'data-bfi-user' for key, value in attrs): self.protected += 1
    def handle_startendtag(self, tag, attrs): self.parts.append(self.get_starttag_text())
    def handle_endtag(self, tag):
        self.parts.append('</' + tag + '>')
        if tag in ('style', 'script') and self.protected: self.protected -= 1
        if tag == 'span' and self.protected: self.protected -= 1
    def handle_data(self, data): self.parts.append(data if self.protected else tr(data))
    def handle_entityref(self, name): self.parts.append('&' + name + ';')
    def handle_charref(self, name): self.parts.append('&#' + name + ';')
    def handle_decl(self, decl): self.parts.append('<!' + decl + '>')
    def handle_comment(self, data): self.parts.append('<!--' + data + '-->')


def translate_html(value):
    if _language == 'en' or not isinstance(value, str): return value
    # Whole HTML templates are translated before text nodes so placeholders
    # preserve markup, paths, numeric values and user-supplied names.
    translated = tr(value)
    if translated != value: return translated
    parser = _HtmlTranslation(); parser.feed(value); parser.close()
    return ''.join(parser.parts)


def _display(value):
    if isinstance(value, str): return translate_html(value) if '<' in value and '>' in value else tr(value)
    if isinstance(value, (list, tuple)): return type(value)(_display(item) for item in value)
    return value


def _remember(obj, method, args, kwargs=None):
    try:
        records = obj.__dict__.setdefault('_bfi_i18n', {})
        key = (method, args[0]) if method.startswith('setTab') else (method,)
        previous = records.get(key)
        index = 1 if method.startswith('setTab') else 0
        if previous and len(args) > index and len(previous[1]) > index:
            old = previous[1][index]
            if isinstance(old, str) and args[index] == _display(old):
                args = previous[1]
        records[key] = (method, tuple(args), dict(kwargs or {}))
        _objects.add(obj)
    except (AttributeError, TypeError): pass


def _block(obj, function):
    previous = obj.blockSignals(True)
    try: return function()
    finally: obj.blockSignals(previous)


def _ui(obj, method, *args, **kwargs):
    """Translate a presentation call and retain its source for later refreshes."""
    values = list(args)
    if method == 'setText' and getattr(obj, '_bfi_i18n_user', False):
        return obj.setText(*args, **kwargs)
    if method in ('addItems', 'addItem') and not isinstance(obj, QComboBox):
        result = getattr(obj, method)(*args, **kwargs)
        from qgis.PyQt.QtWidgets import QListWidget
        if isinstance(obj, QListWidget) and not getattr(obj, '_bfi_translation_delegate', None):
            obj._bfi_translation_delegate = TranslationDelegate(obj)
            obj.setItemDelegate(obj._bfi_translation_delegate)
        return result
    if method in ('addItem', 'addItems') and isinstance(obj, QComboBox):
        if method == 'addItems':
            for text in values[0]: _ui(obj, 'addItem', text)
            return
        index = obj.count()
        result = obj.addItem(*args, **kwargs)
        if values and isinstance(values[0], str):
            obj.setItemData(index, values[0], SOURCE_ROLE)
            _block(obj, lambda: obj.setItemText(index, tr(values[0])))
            _objects.add(obj)
        return result
    if method == 'addTab':
        if values and isinstance(values[-1], str): values[-1] = tr(values[-1])
        index = obj.addTab(*values, **kwargs)
        if args and isinstance(args[-1], str): _remember(obj, 'setTabText', (index, args[-1]))
        return index
    if method == 'addRow':
        if values and isinstance(values[0], str): values[0] = tr(values[0])
        result = obj.addRow(*values, **kwargs)
        if len(args) > 1 and isinstance(args[0], str):
            label = obj.labelForField(args[1])
            if label is not None: _remember(label, 'setText', (args[0],))
        return result
    if method == 'addAction':
        for index, value in enumerate(values[:2]):
            if isinstance(value, str): values[index] = tr(value); break
        action = obj.addAction(*values, **kwargs)
        for value in args[:2]:
            if isinstance(value, str) and action is not None: _remember(action, 'setText', (value,)); break
        return action
    text_index = 1 if method in ('setTabText', 'setTabToolTip') else 0
    if len(values) > text_index:
        values[text_index] = _display(values[text_index])
        _remember(obj, method, args, kwargs)
        if isinstance(obj, QLabel) and method == 'setText' and isinstance(values[text_index], str) and len(values[text_index]) > 32:
            obj.setWordWrap(True)
            if obj.maximumHeight() < obj.fontMetrics().height() * 2: obj.setMaximumHeight(16777215)
    return getattr(obj, method)(*values, **kwargs)


def _new(factory, *args, **kwargs):
    values = list(args); name = factory.__name__
    indices = (0, 1) if name == 'QProgressDialog' else ((1,) if name == 'QAction' and values and not isinstance(values[0], str) else (0,))
    for index in indices:
        if index < len(values) and isinstance(values[index], str): values[index] = _display(values[index])
    obj = factory(*values, **kwargs)
    for index in indices:
        if index >= len(args) or not isinstance(args[index], str): continue
        method = ('setLabelText' if index == 0 else 'setCancelButtonText') if name == 'QProgressDialog' else ('setTitle' if name == 'QGroupBox' else 'setText')
        _remember(obj, method, (args[index],))
    return obj


def _dialog(function, *args, **kwargs):
    # Dialog captions/prompts and file filters are display text; the initial
    # filename/directory argument is deliberately left untouched.
    values = list(args)
    name = getattr(function, '__name__', '')
    file_dialog = name in ('getOpenFileName', 'getOpenFileNames', 'getSaveFileName', 'getExistingDirectory')
    for index in (1, 2):
        if index < len(values) and isinstance(values[index], str) and not (index == 2 and file_dialog):
            values[index] = _display(values[index])
    if name in ('getOpenFileName', 'getOpenFileNames', 'getSaveFileName') and len(values) > 3:
        values[3] = tr(values[3])
    return function(*values, **kwargs)


def _message(function, *args, **kwargs):
    """Translate only this plugin's QGIS message-bar calls."""
    return function(*(_display(value) for value in args),
                    **{key: _display(value) if key in ('title', 'text') else value
                       for key, value in kwargs.items()})


def _item_text(combo, index):
    if isinstance(combo, QComboBox):
        source = combo.itemData(index, SOURCE_ROLE)
        if source is not None: return source
    return combo.itemText(index)


def _combo_text(combo):
    return _item_text(combo, combo.currentIndex()) if isinstance(combo, QComboBox) else combo.currentText()


def _find_text(combo, text, *args):
    if isinstance(combo, QComboBox):
        for index in range(combo.count()):
            if _item_text(combo, index) == text: return index
    return combo.findText(text, *args)


def _select_text(combo, text):
    index = _find_text(combo, text)
    if index >= 0: combo.setCurrentIndex(index)
    else: combo.setCurrentText(text)


def _tab_text(tabs, index):
    record = getattr(tabs, '_bfi_i18n', {}).get(('setTabText', index))
    return record[1][1] if record else tabs.tabText(index)


class TranslationDelegate(QStyledItemDelegate):
    """Present translated result classes while preserving model/source values."""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = tr(option.text)


def localize_widget(root):
    """Register static labels and Qt standard buttons in a plugin-owned tree."""
    if not is_alive(root): return
    from qgis.PyQt.QtWidgets import QTableWidget, QListWidget, QTreeWidget, QDialogButtonBox, QMessageBox
    for obj in [root] + root.findChildren(QWidget):
        if isinstance(obj, (QDialogButtonBox, QMessageBox)):
            for button in obj.buttons():
                standard = obj.standardButton(button)
                for name in ('Ok', 'Cancel', 'Yes', 'No', 'Apply', 'Close', 'Reset', 'Help', 'Save', 'Open', 'Discard'):
                    if standard == enum_value(type(obj), 'StandardButton', name):
                        _ui(button, 'setText', 'OK' if name == 'Ok' else name); break
        records = getattr(obj, '_bfi_i18n', {})
        for method, getter in (('setWindowTitle', 'windowTitle'), ('setToolTip', 'toolTip'), ('setStatusTip', 'statusTip'),
            ('setWhatsThis', 'whatsThis'), ('setAccessibleName', 'accessibleName')):
            if (method,) not in records:
                value = getattr(obj, getter)()
                if value: _ui(obj, method, value)
        if isinstance(obj, (QLabel, QAbstractButton)) and ('setText',) not in records and not getattr(obj, '_bfi_i18n_user', False):
            # Native language names in the selector are intentionally unchanged.
            _ui(obj, 'setText', obj.text())
        if isinstance(obj, QGroupBox) and ('setTitle',) not in records: _ui(obj, 'setTitle', obj.title())
        if isinstance(obj, QTabWidget):
            for index in range(obj.count()):
                if ('setTabText', index) not in records: _ui(obj, 'setTabText', index, obj.tabText(index))
        if isinstance(obj, (QTableWidget, QTreeWidget)) and not getattr(obj, '_bfi_translation_delegate', None):
            obj._bfi_translation_delegate = TranslationDelegate(obj); obj.setItemDelegate(obj._bfi_translation_delegate)


def translate_figure(figure):
    from matplotlib.text import Text
    for text in figure.findobj(Text):
        current = text.get_text()
        previous = getattr(text, '_bfi_language_display', None)
        if previous != current: text._bfi_language_source = current
        source = getattr(text, '_bfi_language_source', current)
        translated = tr(source)
        if current != translated: text.set_text(translated)
        text._bfi_language_display = translated


def _set_language(code):
    global _language
    _language = normalize_language(code)


class LanguageController(QObject):
    def __init__(self, plugin, settings=None):
        super().__init__(plugin.dlg)
        self.plugin = plugin; self.root = plugin.dlg
        self.settings = settings if settings is not None else QSettings()
        self.pending = None; self.refreshing = False
        saved = self.settings.value(SETTING, self.settings.value('locale/userLocale', 'en'))
        _set_language(saved)
        row = QHBoxLayout(); row.addStretch()
        self.label = _new(QLabel, 'Language', self.root)
        self.combo = QComboBox(self.root); self.combo.setObjectName('cmbBFILanguage'); self.combo.setMinimumWidth(145)
        for code, title in LANGUAGES: self.combo.addItem(title, code)
        self.combo.setCurrentIndex(self.combo.findData(language()))
        _ui(self.combo, 'setToolTip', 'Interface, plots and newly generated reports. Calculations and user data are unchanged.')
        row.addWidget(self.label); row.addWidget(self.combo)
        self.root.verticalLayout_root.insertLayout(0, row)
        # The Designer's static combo choices also retain their source labels.
        from .designer_metadata import designer_metadata
        for name, labels in designer_metadata()['combos'].items():
            combo = self.root.findChild(QComboBox, name)
            if combo is None: continue
            for index, label in enumerate(labels):
                if label is not None and index < combo.count(): combo.setItemData(index, label, SOURCE_ROLE)
            if combo.count(): _objects.add(combo)
        self.combo.currentIndexChanged.connect(lambda: self.request(self.combo.currentData()))
        self.timer = QTimer(self); self.timer.setInterval(250); self.timer.timeout.connect(self._finish_pending)
        self.timer.start()
        QApplication.instance().installEventFilter(self)
        localize_widget(self.root); self.apply(language(), persist=False)

    def _busy(self):
        from . import numerical_runtime
        if numerical_runtime._SESSION is not None: return True
        for obj in [self.root, self.plugin, getattr(self.plugin, 'framework_ctrl', None)] + self.root.findChildren(QWidget):
            if obj is not None and (getattr(obj, '_bfi_validation_running', False) or getattr(obj, '_bfi_jobs', ())): return True
        return False

    def request(self, code):
        if self._busy():
            self.pending = code
            _ui(self.label, 'setText', 'Language change pending until calculation finishes')
        else: self.apply(code)

    def _finish_pending(self):
        if self.pending is not None and not self._busy():
            code = self.pending; self.pending = None; self.apply(code)

    def apply(self, code, persist=True):
        if self.refreshing: return
        self.refreshing = True
        try:
            _set_language(code)
            if persist: self.settings.setValue(SETTING, language()); self.settings.sync()
            for obj in tuple(_objects):
                if isinstance(obj, QObject) and not is_alive(obj): continue
                if isinstance(obj, QComboBox):
                    def update():
                        for index in range(obj.count()):
                            source = obj.itemData(index, SOURCE_ROLE)
                            if source is not None: obj.setItemText(index, tr(source))
                    _block(obj, update)
                for method, args, kwargs in tuple(getattr(obj, '_bfi_i18n', {}).values()):
                    _ui(obj, method, *args, **kwargs)
            _ui(self.label, 'setText', 'Language')
            _block(self.combo, lambda: self.combo.setCurrentIndex(self.combo.findData(language())))
            from .mpl_compat import FigureCanvas
            for canvas in self.root.findChildren(FigureCanvas):
                translate_figure(canvas.figure); canvas.draw_idle()
            from .framework_decision_tree_view import FrameworkDecisionTreeView
            for view in self.root.findChildren(FrameworkDecisionTreeView):
                view.update_tree(view._framework_type, view._data_characteristics)
        finally: self.refreshing = False

    def eventFilter(self, obj, event):
        if event.type() == enum_value(QEvent, 'Type', 'Paint') and isinstance(obj, QLabel) and not getattr(obj, '_bfi_i18n_user', False):
            record = getattr(obj, '_bfi_i18n', {}).get(('setText',))
            if record and obj.text() != _display(record[1][0]) and tr(obj.text()) != obj.text():
                _ui(obj, 'setText', obj.text())
        if event.type() == enum_value(QEvent, 'Type', 'Show') and isinstance(obj, QWidget):
            parent = obj
            while parent is not None:
                if parent is self.root:
                    localize_widget(obj); break
                # Some plugin widgets store their owner in a Python ``parent``
                # attribute. Call Qt directly so that attribute cannot shadow it.
                parent = QObject.parent(parent)
        return False

    def dispose(self):
        self.timer.stop()
        app = QApplication.instance()
        if app is not None: app.removeEventFilter(self)
