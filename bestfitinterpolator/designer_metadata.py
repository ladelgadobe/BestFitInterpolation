"""Read bundled Designer labels/defaults without DTD or entity processing."""
from functools import lru_cache
from pathlib import Path
from qgis.PyQt.QtCore import QXmlStreamReader


def parse_designer_metadata(data):
    """Read only widget metadata, rejecting DTDs, entities and excessive input."""
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('Designer XML exceeds the metadata size limit.')
    reader = QXmlStreamReader(data)
    root, stack, count = None, [], 0
    while not reader.atEnd():
        reader.readNext()
        if reader.isDTD() or reader.isEntityReference():
            raise ValueError('DTD and entity declarations are forbidden in Designer XML.')
        if reader.isStartElement():
            count += 1
            if count > 50000 or len(stack) >= 256:
                raise ValueError('Designer XML exceeds the metadata structure limit.')
            attributes = reader.attributes()
            node = dict(tag=str(reader.name()), name=str(attributes.value('name')),
                        widget_class=str(attributes.value('class')), text='', children=[])
            if stack:
                stack[-1]['children'].append(node)
            elif root is None:
                root = node
            stack.append(node)
        elif reader.isCharacters() and stack:
            stack[-1]['text'] += str(reader.text())
        elif reader.isEndElement():
            stack.pop()
    if reader.hasError():
        raise ValueError('Invalid Designer XML: ' + reader.errorString())
    if root is None or root['tag'] != 'ui':
        raise ValueError('Expected a Designer ui document.')

    def property_text(node, name):
        for child in node['children']:
            if child['tag'] == 'property' and child['name'] == name and child['children']:
                return child['children'][0]['text']
        return None

    values, combos, pending = {}, {}, [root]
    while pending:
        node = pending.pop()
        pending.extend(reversed(node['children']))
        if node['tag'] != 'widget':
            continue
        value = property_text(node, 'value')
        if value is not None:
            values[node['name']] = value
        if node['widget_class'] == 'QComboBox':
            combos[node['name']] = [property_text(item, 'text')
                                    for item in node['children'] if item['tag'] == 'item']
    return dict(values=values, combos=combos)


@lru_cache(maxsize=1)
def designer_metadata():
    return parse_designer_metadata(
        Path(__file__).with_name('BestFitInterpolator_dialog_base.ui').read_bytes())
