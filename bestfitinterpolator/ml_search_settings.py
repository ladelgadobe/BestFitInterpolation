"""One source of search defaults for individual windows and Framework.

The shipped UI owns the defaults; reading it does not require opening a tab.
The individual V2.0 readers retain their original rounding and range convention.
"""
from copy import deepcopy
from functools import lru_cache
from decimal import Decimal, ROUND_HALF_UP
from .designer_metadata import designer_metadata


@lru_cache(maxsize=1)
def _defaults():
    values = designer_metadata()['values']
    def value(name):
        return float(values[name])
    result = {}
    for method in ('RF', 'SVM', 'RK'):
        cast = float if method == 'SVM' else int
        names = ('C', 'gamma', 'epsilon') if method == 'SVM' else ('ntree', 'mtry', 'nodesize')
        result[method] = dict(grid_params={p: {k: cast(value('spin{}_{}_{}'.format(method, p, k)))
                                            for k in ('min', 'max', 'step')} for p in names},
                              folds=int(value('spin{}SearchK'.format(method))),
                              iterations=int(value('spin{}SearchIter'.format(method))))
    # V2.0 sets SVM controls to two decimals, then its reader clamps positive
    # C/gamma fields to 0.01. Mirror those effective defaults without opening tabs.
    for parameter, fields in result['SVM']['grid_params'].items():
        for key, value in fields.items():
            rounded = float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            fields[key] = max(0.0 if parameter == 'epsilon' and key != 'step' else .01, rounded)
    return result


def method_defaults(method):
    return deepcopy(_defaults()[method])


def read_method_settings(dialog, method):
    result = method_defaults(method)
    def read(name, fallback):
        widget = getattr(dialog, name, None)
        return widget.value() if widget is not None and hasattr(widget, 'value') else fallback
    cast = float if method == 'SVM' else int
    for parameter, fields in result['grid_params'].items():
        for key, default in fields.items():
            fields[key] = cast(read('spin{}_{}_{}'.format(method, parameter, key), default))
    result['folds'] = max(2, int(read('spin{}SearchK'.format(method), result['folds'])))
    result['iterations'] = max(1, int(read('spin{}SearchIter'.format(method), result['iterations'])))
    return result
