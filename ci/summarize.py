"""Aggregate exact execution evidence and enforce required-target coverage."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(discovery, folder):
    rows = []
    for target in discovery['targets']:
        files = list(folder.rglob(target['requested'] + '.json'))
        result = json.loads(files[0].read_text(encoding='utf-8')) if files else dict(status='UNAVAILABLE', tests={}, actual=None, errors=['No runtime evidence artifact found.'])
        rows.append(dict(target, **{key: value for key, value in result.items() if key not in target}))
    baseline = json.loads((ROOT / 'tests/data/numerical_baseline.json').read_text())
    lines = ['# Best Fit Interpolator Compatibility', '',
             '| Requested QGIS | Actual QGIS | Verification | Tests | Required |',
             '|---|---|---|---|---|']
    for row in rows:
        passed = sum(test['result'] == 'PASS' for test in row.get('tests', {}).values())
        tests = '{}/{}'.format(passed, len(row.get('tests', {}))) if row.get('tests') else 'Not executed'
        label = row['requested'] + (' (latest stable 4.x)' if 'latest4' in row['aliases'] else '')
        lines.append('| {} | {} | {} | {} | {} |'.format(label, row.get('actual') or 'None', row['status'], tests, row['required']))
    lines += ['', '## Numerical comparison against QGIS ' + baseline['qgis'], '',
              'Relative tolerance: {}; absolute tolerance: {}. Exact LISA class comparison. Expected values are never regenerated in CI.'.format(baseline['rtol'], baseline['atol']), '',
              '| QGIS | Calculation | Maximum absolute difference |', '|---|---|---|']
    for row in rows:
        for key, values in row.get('numerical_results', {}).items():
            expected = baseline['results'][key]
            delta = 'same classes' if key == 'lisa' and values == expected else ('classes differ' if key == 'lisa' else '{:.8g}'.format(max(abs(a-b) for a,b in zip(values, expected))))
            lines.append('| {} | {} | {} |'.format(row['requested'], key, delta))
    for row in rows:
        lines += ['', '## QGIS ' + row['requested'], '', 'Image: ' + str(row.get('resolution')), '',
                  'Environment: ' + str(row.get('environment', {})), '']
        for name, result in row.get('tests', {}).items(): lines.append('- {}: {} {}'.format(name, result['result'], result.get('category', '')))
        for error in row.get('errors', []): lines += ['', '```text', str(error), '```']
        for warning in row.get('warnings', []): lines.append('- Warning: ' + warning)
    verified = [row.get('actual') for row in rows if row['status'] == 'EXECUTED']
    lines += ['', '## Verified support', '', 'Actually executed: ' + (', '.join(verified) if verified else 'None'),
              'Metadata is not changed by this workflow. Static checks and unavailable runtimes do not justify expanding support.']
    return rows, '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', default=str(ROOT / 'compatibility-results'))
    parser.add_argument('--discovery', default=str(ROOT / 'compatibility-results/discovery.json'))
    parser.add_argument('--informational', action='store_true')
    args = parser.parse_args()
    folder = Path(args.folder); folder.mkdir(parents=True, exist_ok=True)
    rows, markdown = summarize(json.loads(Path(args.discovery).read_text()), folder)
    (folder / 'qgis_compatibility_report.md').write_text(markdown, encoding='utf-8')
    (folder / 'qgis_compatibility_report.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream: stream.write(markdown)
    print(markdown)
    return 1 if not args.informational and any(row['required'] and row['status'] != 'EXECUTED' for row in rows) else 0


if __name__ == '__main__': raise SystemExit(main())
