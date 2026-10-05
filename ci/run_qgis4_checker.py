"""Run the official checker in a digest-pinned, read-only Docker environment."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'bestfitinterpolator').rglob('*.py') if '__pycache__' not in p.parts}


def main():
    output = ROOT / 'compatibility-results/checker'
    output.mkdir(parents=True, exist_ok=True)
    configuration = json.loads((ROOT / 'ci/qgis_targets.json').read_text())
    tag = configuration['checker_image']
    before = hashes()
    result = {'status': 'UNAVAILABLE', 'image_tag': tag, 'mode': 'dry_run', 'source_modified': False}
    try:
        subprocess.run(['docker', 'pull', tag], check=True)
        image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{index .RepoDigests 0}}', tag], universal_newlines=True).strip()
        result['image_digest'] = image
        process = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--user', '0:0',
                                  '-e', 'PYTHONOPTIMIZE=0', '-v', str(ROOT) + ':/workspace:ro',
                                  '-v', str(output) + ':/results', '--entrypoint', 'pyqt5_to_pyqt6.py', image,
                                  '--dry_run', '--logfile', '/results/pyqgis4-checker.log', '/workspace/bestfitinterpolator'],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        (output / 'console.log').write_text(process.stdout, encoding='utf-8')
        result['returncode'] = process.returncode
        result['source_modified'] = before != hashes()
        result['status'] = 'STATICALLY_CHECKED' if process.returncode == 0 and not result['source_modified'] else 'FAILED'
        result['review_required'] = True
        # A successful dry run does not mean zero findings. The gate reviews the log separately.
        print(process.stdout)
    except Exception as exc:
        result['error'] = str(exc)
    (output / 'checker.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return 0 if result['status'] == 'STATICALLY_CHECKED' else 1


if __name__ == '__main__': raise SystemExit(main())
