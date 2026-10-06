"""Portable QGIS headless runner; the same entry point is used by Docker and CI."""
import argparse
import importlib
import json
import os
import platform
import sys
import tempfile
import traceback
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/compatibility'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')


def classify_error(message):
    for category, tokens in [('IMPORT', ('ImportError', 'ModuleNotFoundError')),
                             ('PYTHON', ('SyntaxError',)),
                             ('QT', ('Qt', 'sip', 'QWidget', 'QVariant')),
                             ('UI LIFECYCLE', ('deleted', 'destroyed', 'signal')),
                             ('NUMERICAL DIFFERENCE', ('Not equal to tolerance', 'NUMERICAL')),
                             ('DEPENDENCY', ('numpy', 'scipy', 'sklearn', 'pandas', 'matplotlib')),
                             ('QGIS API', ('Qgs', 'Qgis', 'qgis'))]:
        if any(token in message for token in tokens):
            return category
    return 'UNKNOWN'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--requested', required=True, help='Exact requested major.minor, or nightly')
    parser.add_argument('--output', default=str(ROOT / 'compatibility-results/local.json'))
    parser.add_argument('--pdf', action='store_true')
    parser.add_argument('--image', default='local installed runtime')
    parser.add_argument('--plugin-root', default=str(ROOT/'bestfitinterpolator'), help='Plugin source directory to exercise, including an installed copy')
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'requested': args.requested, 'actual': None, 'status': 'FAILED',
              'image': args.image, 'environment': {}, 'tests': {}, 'warnings': [], 'errors': []}
    dll_handles = []
    app = None
    try:
        plugin_root=Path(args.plugin_root).resolve()
        if plugin_root.name!='bestfitinterpolator' or not (plugin_root/'__init__.py').is_file():
            raise RuntimeError('The requested plugin source directory is invalid')
        sys.path.insert(0,str(plugin_root.parent))
        report['plugin_source']=str(plugin_root)
        if not __debug__:
            raise RuntimeError('Tests cannot run with assertions disabled; unset PYTHONOPTIMIZE and omit -O.')
        if os.name == 'nt':
            install = Path(os.environ.get('BFI_QGIS_INSTALL', r'C:\Program Files\QGIS 3.44.8'))
            qgis_dir = install / 'apps' / ('qgis-ltr' if (install / 'apps/qgis-ltr').exists() else 'qgis')
            qt_dir = install / 'apps' / ('Qt6' if (install / 'apps/Qt6').exists() else 'Qt5')
            sys.path.insert(0, str(qgis_dir / 'python'))
            os.environ['QT_PLUGIN_PATH'] = str(qt_dir / 'plugins')
            os.environ['QGIS_PREFIX_PATH'] = str(qgis_dir)
            if hasattr(os, 'add_dll_directory'):
                dll_handles = [os.add_dll_directory(str(p)) for p in (install / 'bin', qt_dir / 'bin', qgis_dir / 'bin')]
        else:
            for directory in ('/usr/share/qgis/python', '/usr/lib/python3/dist-packages'):
                if Path(directory).exists():
                    sys.path.append(directory)
        from qgis.core import QgsApplication, Qgis
        from qgis.PyQt.QtCore import QT_VERSION_STR
        from osgeo import gdal, osr
        actual = Qgis.QGIS_VERSION
        report['actual'] = actual
        report['environment'].update(QGIS=actual, Qt=QT_VERSION_STR, Python=platform.python_version(),
                                     GDAL=gdal.VersionInfo('RELEASE_NAME'))
        report['environment']['PROJ'] = '.'.join(str(getattr(osr, 'GetPROJVersion' + part)()) for part in ('Major', 'Minor', 'Micro')) if hasattr(osr, 'GetPROJVersionMajor') else 'unavailable'
        for label, module_name in [('NumPy', 'numpy'), ('SciPy', 'scipy'), ('scikit-learn', 'sklearn'), ('matplotlib', 'matplotlib'), ('pandas', 'pandas')]:
            module = importlib.import_module(module_name)
            report['environment'][label] = module.__version__
        print(json.dumps(report['environment'], indent=2), flush=True)
        requested = args.requested.split('.')[:2]
        actual_parts = actual.split('-')[0].split('.')[:2]
        if args.requested != 'nightly' and actual_parts != requested:
            raise RuntimeError('QGIS API version mismatch: requested {}, actual {}'.format(args.requested, actual))
        if int(actual_parts[0]) >= 4 and not QT_VERSION_STR.startswith('6.'):
            raise RuntimeError('Qt6 is required for the QGIS 4 runtime')
        with tempfile.TemporaryDirectory(prefix='bfi-qgis-profile-') as profile:
            app = QgsApplication([], False, profile)
            app.initQgis()
            if os.name=='nt':
                from qgis.PyQt.QtGui import QFontDatabase,QFont
                for font in ('arial.ttf','arialbd.ttf','ariali.ttf'):
                    QFontDatabase.addApplicationFont(str(Path(r'C:\Windows\Fonts')/font))
                app.setFont(QFont('Arial',9))
            from runtime_cases import RuntimeCases
            import bestfitinterpolator
            if Path(bestfitinterpolator.__file__).resolve().parent!=plugin_root:
                raise RuntimeError('Plugin source mismatch; refusing to test a substituted copy')
            suite = RuntimeCases(app, output.parent, args.pdf)
            for name, case in suite.cases():
                try:
                    with warnings.catch_warnings(record=True) as recorded:
                        warnings.simplefilter('always')
                        case()
                    report['warnings'].extend(str(item.message) for item in recorded)
                    report['tests'][name] = {'result': 'PASS'}
                    print('PASS', name, flush=True)
                except Exception:
                    message = traceback.format_exc()
                    report['tests'][name] = {'result': 'FAIL', 'category': classify_error(message), 'error': message}
                    report['errors'].append(message)
                    print('FAIL', name, message, flush=True)
            report['numerical_results'] = suite.numerical_results
            suite.cleanup()
            if suite.slot_errors or suite.alerts:
                raise RuntimeError('Qt or plugin errors: ' + repr(suite.slot_errors + suite.alerts))
            report['status'] = 'EXECUTED' if not report['errors'] else 'FAILED'
    except Exception:
        message = traceback.format_exc()
        report['errors'].append(message)
        report['category'] = classify_error(message)
        print(message, flush=True)
    finally:
        report['warnings'] = sorted(set(report['warnings']))
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if app is not None:
            app.exitQgis()
    return 0 if report['status'] == 'EXECUTED' else 1


if __name__ == '__main__':
    sys.exit(main())
