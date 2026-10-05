"""Resolve/build/run one official environment for both local use and GitHub Actions."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from static_check import analyze


def fallback(target, folder, reason):
    static = analyze()
    result = dict(target, actual=None, status='STATICALLY_CHECKED' if not static['syntax_errors'] else 'UNAVAILABLE',
                  static_analysis=static, tests={}, errors=[reason], category='DEPENDENCY',
                  environment_available=False)
    (folder / (target['requested'] + '.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(reason)
    return 1 if target.get('required') else 0


def run(command, log):
    print(' '.join(command), flush=True)
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    print(process.stdout, flush=True)
    with log.open('a', encoding='utf-8') as stream: stream.write(process.stdout)
    return process.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    parser.add_argument('--discovery', default=str(ROOT / 'compatibility-results/discovery.json'))
    parser.add_argument('--output', default=str(ROOT / 'compatibility-results'))
    args = parser.parse_args()
    folder = Path(args.output).resolve(); folder.mkdir(parents=True, exist_ok=True)
    rows = json.loads(Path(args.discovery).read_text())['targets']
    target = next(row for row in rows if args.version == row['requested'] or args.version in row['aliases'])
    if not shutil.which('docker'): return fallback(target, folder, 'Docker is unavailable on this host. No QGIS runtime was substituted.')
    if not target['resolution']: return fallback(target, folder, 'Official image unavailable: ' + str(target.get('discovery_error') or 'no matching tag'))
    image = target['resolution']['image']
    log = folder / (target['requested'] + '.log')
    log.write_text('', encoding='utf-8')
    digest = hashlib.sha256((image + (ROOT / 'docker/compatibility.Dockerfile').read_text()).encode()).hexdigest()[:16]
    tag = 'bfi-compatibility:' + digest
    command = ['docker', 'buildx', 'build', '--load', '--build-arg', 'QGIS_IMAGE=' + image,
               '-f', str(ROOT / 'docker/compatibility.Dockerfile'), '-t', tag]
    cache = os.environ.get('BFI_DOCKER_CACHE')
    if cache:
        command += ['--cache-from', 'type=local,src=' + cache,
                    '--cache-to', 'type=local,dest=' + cache + '-new,mode=max']
    command += [str(ROOT)]
    if run(command, log): return fallback(target, folder, 'Official image pull or scientific environment build failed; see Docker log.')
    output_name = target['requested'] + '.json'
    command = ['docker', 'run', '--rm', '--network', 'none', '--entrypoint', '/usr/bin/env',
               '-e', 'QT_QPA_PLATFORM=offscreen',
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(ROOT) + ':/workspace:ro',
               '-v', str(folder) + ':/results', '-w', '/workspace', tag,
               '-u', 'PYTHONOPTIMIZE', 'python3', '/workspace/scripts/run_qgis_tests.py', '--requested', target['requested'],
               '--image', image, '--output', '/results/' + output_name]
    if target['pdf']: command.append('--pdf')
    code = run(command, log)
    path = folder / output_name
    if not path.exists(): return fallback(target, folder, 'Container terminated before test evidence was written; see Docker log.')
    result = json.loads(path.read_text())
    if code and result['status']=='EXECUTED':
        result['status']='FAILED'
        result['category']='UI LIFECYCLE'
        result.setdefault('errors',[]).append('Container exited with code {} after writing evidence.'.format(code))
    result.update(aliases=target['aliases'], required=target['required'], resolution=target['resolution'])
    # Docker may create the evidence as root; replace its directory entry from the host.
    finalized = path.with_suffix('.host.json')
    finalized.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    finalized.replace(path)
    return (0 if not code and result['status']=='EXECUTED' else 1) if target['required'] else 0


if __name__ == '__main__': raise SystemExit(main())
