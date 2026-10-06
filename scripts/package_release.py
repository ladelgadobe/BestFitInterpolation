"""Build a reproducible QGIS ZIP and manual assets from a committed revision."""
import argparse
import ast
import configparser
import hashlib
import io
import json
import subprocess
import time
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = 'bestfitinterpolator'
MANUAL = 'BestFitInterpolator_User_Manual.pdf'
MANUAL_URL = 'https://github.com/ladelgadobe/BestFitInterpolation/blob/main/' + MANUAL
EXCLUDED_DIRS = {'test', 'docs', '__pycache__', '_deps', '.pytest_cache'}
EXCLUDED_FILES = {'.gitignore', 'Makefile', 'pb_tool.cfg', 'pylintrc', 'plugin_upload.py',
                  'scripts/compile-strings.sh', 'scripts/run-env-linux.sh',
                  'scripts/update-strings.sh'}


def git(*args):
    return subprocess.check_output(['git'] + list(args), cwd=str(ROOT))


def blob(commit, name):
    return git('show', commit + ':' + name)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    commit = git('rev-parse', args.revision + '^{commit}').decode().strip()
    names = git('ls-tree', '-r', '--name-only', '-z', commit, '--', PLUGIN).decode().split('\0')
    files = {}
    for name in sorted(filter(None, names)):
        relative = PurePosixPath(name).relative_to(PLUGIN)
        if (set(relative.parts) & EXCLUDED_DIRS or str(relative) in EXCLUDED_FILES
                or relative.suffix in ('.pyc', '.pyo')):
            continue
        files[name] = blob(commit, name)
    required = {'__init__.py', 'metadata.txt', 'LICENSE', 'README.md', 'icon.png',
                'resources.py', 'BestFitInterpolator_dialog_base.ui'}
    if not {PLUGIN + '/' + name for name in required}.issubset(files):
        raise RuntimeError('The committed plugin is missing required runtime files')
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read_string(files[PLUGIN + '/metadata.txt'].decode('utf-8-sig'))
    general = metadata['general']
    version = general['version']
    if (general['manual'] != MANUAL_URL
            or not general['changelog'].startswith('Version ' + version + ':')):
        raise RuntimeError('Release metadata and stable manual link are inconsistent')
    modules = 0
    for name, data in files.items():
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8-sig'), filename=name, feature_version=(3, 7))
            modules += 1
    ET.parse(io.BytesIO(files[PLUGIN + '/BestFitInterpolator_dialog_base.ui']))
    manual = blob(commit, MANUAL)
    verification = json.loads(blob(commit, 'docs/manual/verification.json'))
    if not manual.startswith(b'%PDF-') or sha(manual) != verification['pdf_sha256']:
        raise RuntimeError('The committed PDF differs from the reviewed manual')
    timestamp = int(git('show', '-s', '--format=%ct', commit).decode().strip())
    zip_time = time.gmtime(max(timestamp, 315532800))[:6]
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / 'bestfitinterpolator.zip'
    with zipfile.ZipFile(str(archive_path), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, zip_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(str(archive_path)) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise RuntimeError('ZIP integrity or file inventory check failed')
        for name, data in files.items():
            if archive.read(name) != data:
                raise RuntimeError('ZIP differs from commit: ' + name)
    (output / MANUAL).write_bytes(manual)
    artifacts = {archive_path.name: sha(archive_path.read_bytes()), MANUAL: sha(manual)}
    manifest = {
        'version': version, 'tag': 'v' + version, 'source_commit': commit,
        'archive_root': PLUGIN + '/', 'files': len(files), 'python37_syntax_modules': modules,
        'manual_url': MANUAL_URL, 'manual_pages': verification['pages'],
        'qgis_minimum': general['qgisMinimumVersion'],
        'qgis_maximum': general['qgisMaximumVersion'],
        'artifacts_sha256': artifacts,
        'packaged_files_sha256': {name: sha(data) for name, data in sorted(files.items())},
    }
    manifest_path = output / 'release_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    artifacts[manifest_path.name] = sha(manifest_path.read_bytes())
    (output / 'SHA256SUMS').write_text(
        ''.join(value + '  ' + name + '\n' for name, value in sorted(artifacts.items())),
        encoding='ascii')
    print(json.dumps({key: value for key, value in manifest.items()
                      if key != 'packaged_files_sha256'}, indent=2))


if __name__ == '__main__':
    main()
