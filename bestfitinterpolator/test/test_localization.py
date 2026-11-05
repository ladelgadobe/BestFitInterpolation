"""Language changes preserve model identifiers, user inputs and numeric output."""
import json
import re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QComboBox, QLabel, QCheckBox, QListWidget, QPlainTextEdit, QWidget, QPushButton
from bestfitinterpolator import localization as loc
from bestfitinterpolator.BestFitInterpolator import BestFitInterpolatorDialog
from bestfitinterpolator.report_model import ReportState, ReportSection, ReportTable, report_html


@pytest.fixture(autouse=True)
def english():
    loc._set_language('en')
    yield
    loc._set_language('en')


def test_catalog_has_both_languages_and_identical_value_placeholders():
    for source,translations in loc.CATALOG.items():
        assert set(translations)=={'es','pt_BR'}
        for text in translations.values():
            assert text and sorted(re.findall(r'\{p\d+\}',source))==sorted(re.findall(r'\{p\d+\}',text))
            if '(*' in source:
                assert re.findall(r'\*[^\s;)]*',source)==re.findall(r'\*[^\s;)]*',text)


def test_formatted_translations_preserve_values_and_paths():
    loc._set_language('es')
    value='Could not save graph:\nC:/Prediction/suelo_á.tif'
    assert loc.tr(value)=='No se pudo guardar el gráfico:\nC:/Prediction/suelo_á.tif'
    assert loc.tr('Lowest cross-validation RMSE = 0.123456')=='Menor RMSE de validación cruzada = 0.123456'
    assert loc.tr('Prediction² (variance)')=='Prediction² (varianza)'
    assert loc.tr('Prediction — kriging SD')=='Prediction — DE de Kriging'
    loc._set_language('pt_BR')
    assert loc.tr('Prediction² (variance)')=='Prediction² (vari\u00e2ncia)'
    assert loc.tr('Prediction (SD)')=='Prediction (DP)'


def test_nested_profile_notice_translates_dynamic_fragments_and_keeps_counts():
    from bestfitinterpolator.performance_policy import massive_data_capacity_note
    for code,current in (('es','Selección actual:'),('pt_BR','Seleção atual:')):
        loc._set_language(code)
        note=loc.tr(massive_data_capacity_note(114))
        assert current in note and '114' in note and '100,000+' in note
        assert 'Current selection' not in note
        status=loc.tr('Current selection: 114 valid samples → massive.')
        assert current in status and '114' in status and 'massive' not in status


def test_message_bar_translates_without_changing_paths_or_severity():
    received=[]
    loc._set_language('es')
    loc._message(lambda *args,**kwargs:received.append((args,kwargs)),
                 'Warning','Failed to export raster: G:/Prediction/Clay.tif',level=2,duration=8)
    args,kwargs=received[0]
    assert args==('Advertencia','No se pudo exportar el ráster: G:/Prediction/Clay.tif')
    assert kwargs==dict(level=2,duration=8)


def test_fixed_combo_translates_without_mutating_source_data_or_emitting_selection():
    combo=QComboBox();loc._ui(combo,'addItem','Automatic','automatic');loc._ui(combo,'addItem','Spherical','spherical')
    combo.setCurrentIndex(1);signals=[];combo.currentIndexChanged.connect(signals.append)
    loc._set_language('pt_BR')
    loc._block(combo,lambda:[combo.setItemText(i,loc.tr(loc._item_text(combo,i))) for i in range(combo.count())])
    assert combo.currentText()=='Esférico' and loc._combo_text(combo)=='Spherical'
    assert combo.currentData()=='spherical' and not signals
    assert loc._find_text(combo,'Spherical')==1
    loc._select_text(combo,'Automatic');assert loc._combo_text(combo)=='Automatic' and combo.currentData()=='automatic'


def test_user_layer_names_are_never_assigned_translation_roles():
    combo=QComboBox();combo.addItem('Prediction','a-layer-id')
    loc._set_language('es')
    assert loc._combo_text(combo)=='Prediction' and combo.currentText()=='Prediction'
    assert combo.itemData(0,loc.SOURCE_ROLE) is None


def test_static_list_refresh_never_duplicates_items_or_changes_source_values():
    choices=QListWidget();loc._ui(choices,'addItems',('Overview','Validation'))
    assert choices.count()==2 and choices.item(0).text()=='Overview'
    assert ('addItems',) not in getattr(choices,'_bfi_i18n',{})
    for code in ('es','pt_BR','en'):
        loc._set_language(code);loc.localize_widget(choices)
        assert choices.count()==2 and choices.item(0).text()=='Overview'


def test_refresh_retains_the_original_english_source():
    label=QLabel();loc._ui(label,'setText','Prediction')
    loc._set_language('es');loc._ui(label,'setText','Prediction')
    assert label.text()=='Predicción'
    # Theme/visibility refreshes may pass the already translated display text.
    loc._ui(label,'setText',label.text())
    loc._set_language('en')
    method,args,kwargs=label._bfi_i18n[('setText',)]
    loc._ui(label,method,*args,**kwargs);assert label.text()=='Prediction'


def test_theme_refresh_does_not_capture_a_translated_button_as_its_source():
    from bestfitinterpolator.theme import refresh_controls
    root=QWidget();loc._set_language('pt_BR')
    button=loc._new(QPushButton,'Contact by email',root)
    assert button.text()=='Entrar em contato por e-mail'
    refresh_controls(root)
    for code,expected in (('en','Contact by email'),('es','Contactar por correo'),('pt_BR','Entrar em contato por e-mail')):
        loc._set_language(code)
        method,args,kwargs=button._bfi_i18n[('setText',)]
        loc._ui(button,method,*args,**kwargs);refresh_controls(root)
        assert button.text()==expected


def test_plot_styling_keeps_the_original_title_for_subsequent_languages():
    from matplotlib.figure import Figure
    from bestfitinterpolator.theme import style_figure
    figure=Figure();axes=figure.subplots();axes.set_title('K-Fold Cross-Validation')
    for code in ('es','pt_BR','en','pt_BR','es','en'):
        loc._set_language(code);style_figure(figure);style_figure(figure)
        assert axes.get_title()==loc.tr('K-Fold Cross-Validation')


def test_figure_translation_preserves_all_numeric_artists():
    from matplotlib.figure import Figure
    figure=Figure();axes=figure.add_subplot(111)
    line,=axes.plot([1.,2.,3.],[4.,5.,6.]);axes.set_xlabel('Observed');axes.set_ylabel('Predicted')
    before=line.get_xydata().copy()
    for code,expected in (('es','Predicho'),('pt_BR','Predito'),('en','Predicted')):
        loc._set_language(code);loc.translate_figure(figure)
        assert axes.get_ylabel()==expected
        np.testing.assert_array_equal(line.get_xydata(),before)


def test_report_translates_display_without_mutating_snapshot_or_user_notes():
    state=ReportState(study_name='Prediction',notes='Data',sections=[ReportSection('validation','Validation Results',tables=[ReportTable(('Method','Value'),(('RF',.25),))])])
    loc._set_language('es');translated=report_html(state)
    assert 'Resultados de validación' in translated and '<span data-bfi-user>Prediction</span>' in translated
    assert '<span data-bfi-user>Data</span>' in translated
    assert state.sections[0].title=='Validation Results' and state.sections[0].tables[0].rows==( ('RF',.25), )


def test_dialog_translation_preserves_initial_file_path():
    received=[]
    def getSaveFileName(*args):received.append(args);return args[2],args[3]
    loc._set_language('pt_BR')
    result=loc._dialog(getSaveFileName,None,'Save graph','C:/Prediction/Data.png','PNG (*.png)')
    assert received[0][1]=='Salvar gráfico' and result[0]=='C:/Prediction/Data.png'


def test_summary_translation_preserves_user_field_and_numbers():
    text='Mode: Univariate.\nVariable: Prediction\nSamples: 24.\nSpatial pattern: Clustered.'
    summary=QPlainTextEdit()
    loc._set_language('es');loc._ui(summary,'setPlainText',text)
    translated=summary.toPlainText()
    assert 'Modo: Univariado.' in translated and 'Variable: Prediction' in translated
    assert 'Muestras: 24.' in translated and 'Patrón espacial: Agrupado.' in translated
    loc._set_language('en')
    method,args,kwargs=summary._bfi_i18n[('setPlainText',)]
    loc._ui(summary,method,*args,**kwargs);assert summary.toPlainText()==text


def test_preference_is_plugin_scoped_and_deferred_while_jobs_run(tmp_path):
    preferences=QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat)
    preferences.setValue('locale/userLocale','es_ES')
    dialog=BestFitInterpolatorDialog(str(Path(__file__).resolve().parents[1]));plugin=SimpleNamespace(dlg=dialog,framework_ctrl=None)
    controller=loc.LanguageController(plugin,preferences)
    try:
        assert loc.language()=='es' and dialog.mainTabs.tabText(0)=='Datos'
        dialog._bfi_jobs={object()};controller.request('pt_BR')
        assert loc.language()=='es' and controller.pending=='pt_BR'
        dialog._bfi_jobs.clear();controller._finish_pending()
        assert loc.language()=='pt_BR' and preferences.value(loc.SETTING)=='pt_BR'
        assert preferences.value('locale/userLocale')=='es_ES'
    finally:
        controller.dispose();dialog.deleteLater()
