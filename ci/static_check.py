"""Evidence-based static inventory; static success never means runtime PASS."""
import argparse
import ast
import configparser
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'direct Qt binding': r'\b(?:from|import)\s+PyQt[56]\b',
    'legacy exec alias': r'\.exec_\(',
    'legacy QVariant assumption': r'QVariant\.(?:Int|Double|String|LongLong|Bool)',
    'Qt legacy enum': r'\bQt\.(?:Align\w+|UserRole|DisplayRole|KeepAspectRatio|Horizontal|Vertical)\b',
    'QGIS legacy type alias': r'QgsWkbTypes\.\w+Geometry|QgsUnitTypes\.Distance\w+',
    'legacy Matplotlib backend': r'backend_qt5agg|Qt5Agg',
    'modern NumPy dependency': r'default_rng|equal_nan\s*=',
    'modern standard library': r'missing_ok\s*=|\.removeprefix\(|\.removesuffix\(',
}


def analyze():
    files = list((ROOT / 'bestfitinterpolator').rglob('*.py'))
    imports, findings, syntax_errors = [], [], []
    for path in files:
        if any(part in ('__pycache__', '_deps') for part in path.parts): continue
        text = path.read_text(encoding='utf-8-sig')
        name = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(text, filename=name, feature_version=(3, 7))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom): module = node.module or ''
                elif isinstance(node, ast.Import): module = ','.join(alias.name for alias in node.names)
                else: continue
                if any(token in module for token in ('qgis', 'Qt', 'matplotlib', 'processing', 'scipy', 'numpy', 'sklearn', 'pandas', 'osgeo')):
                    imports.append({'file': name, 'line': node.lineno, 'module': module})
        except SyntaxError as error:
            syntax_errors.append({'file': name, 'error': str(error)})
        for line, value in enumerate(text.splitlines(), 1):
            if value.strip().startswith('#'): continue
            for category, pattern in PATTERNS.items():
                if re.search(pattern, value):
                    reviewed = path.name in ('compat.py', 'mpl_compat.py')
                    findings.append({'file': name, 'line': line, 'category': category,
                                     'code': value.strip(), 'reviewed_adapter': reviewed})
    metadata = configparser.ConfigParser()
    metadata.read(str(ROOT / 'bestfitinterpolator/metadata.txt'), encoding='utf-8-sig')
    return {'status': 'STATICALLY_CHECKED', 'syntax_floor': 'Python 3.7 grammar',
            'syntax_errors': syntax_errors, 'imports': imports, 'findings': findings,
            'metadata_minimum': metadata['general']['qgisMinimumVersion'],
            'metadata_maximum': metadata['general']['qgisMaximumVersion'],
            'limitations': ['Import inventory is not runtime import execution.',
                            'Feature-detected aliases require runtime testing; deprecated API inventory is not exhaustive.',
                            'Dependency versions and availability must be measured in each container.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'compatibility-results/static.json'))
    args = parser.parse_args()
    result = analyze()
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('STATICALLY_CHECKED: {} imports, {} findings, {} syntax errors'.format(len(result['imports']), len(result['findings']), len(result['syntax_errors'])))
    return 1 if result['syntax_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
