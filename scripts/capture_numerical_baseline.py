"""Explicit baseline capture; CI never updates expected values automatically."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
parser = argparse.ArgumentParser()
parser.add_argument('--output', default=str(root / 'tests/data/numerical_baseline.json'))
args = parser.parse_args()
from qgis.core import Qgis
from qgis.PyQt.QtCore import QT_VERSION_STR
spec = importlib.util.spec_from_file_location('numerical_fixture', str(root / 'tests/compatibility/numerical.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
values = module.calculate()
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
payload = {'qgis': Qgis.QGIS_VERSION, 'qt': QT_VERSION_STR, 'python': sys.version.split()[0],
           'rtol': 1e-5, 'atol': 1e-7, 'results': values,
           'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / 'bestfitinterpolator').glob('*.py')}}
output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
print('BASELINE_CAPTURED', Qgis.QGIS_VERSION, output)
