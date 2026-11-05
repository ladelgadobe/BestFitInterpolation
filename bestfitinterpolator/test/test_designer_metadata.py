"""Designer metadata must preserve the UI and reject XML entity declarations."""
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from bestfitinterpolator.designer_metadata import designer_metadata, parse_designer_metadata


def test_all_shipped_values_and_combo_labels_match_the_original_designer_file():
    path = Path(__file__).resolve().parents[1] / 'BestFitInterpolator_dialog_base.ui'
    root = ET.parse(str(path)).getroot()
    values, combos = {}, {}
    for widget in root.iter('widget'):
        value = widget.find("property[@name='value']")
        if value is not None and len(value):
            values[widget.attrib['name']] = value[0].text or ''
        if widget.attrib.get('class') == 'QComboBox':
            combos[widget.attrib['name']] = [
                item.find("property[@name='text']/string").text or ''
                if item.find("property[@name='text']/string") is not None else None
                for item in widget.findall('item')]
    assert designer_metadata() == dict(values=values, combos=combos)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_dtd_and_external_entities_are_rejected_before_expansion(encoding):
    xml = ('<?xml version="1.0" encoding="' + encoding + '"?>'
           '<!DOCTYPE ui [<!ENTITY secret SYSTEM "file:///never-read-this-file">]>'
           '<ui><widget class="QComboBox" name="test"><item>'
           '<property name="text"><string>&secret;</string></property>'
           '</item></widget></ui>').encode(encoding)
    with pytest.raises(ValueError, match='DTD and entity'):
        parse_designer_metadata(xml)


def test_malformed_xml_is_rejected_instead_of_returning_partial_defaults():
    with pytest.raises(ValueError, match='Invalid Designer XML'):
        parse_designer_metadata(b'<ui><widget name="incomplete"></ui>')


def test_predefined_entities_unicode_and_empty_labels_are_preserved():
    xml = ('<ui><widget class="QComboBox" name="choices">'
           '<item><property name="text"><string>Português &amp; Español</string></property></item>'
           '<item><property name="text"><string/></property></item>'
           '</widget></ui>').encode('utf-8')
    assert parse_designer_metadata(xml)['combos']['choices'] == ['Português & Español', '']
