"""Discover official version tags; never replace a missing target with another QGIS."""
import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def get_json(url):
    headers = {'User-Agent': 'BestFitInterpolator-compatibility', 'Accept': 'application/json'}
    origin = urlsplit(url)
    if origin.scheme == 'https' and origin.netloc == 'api.github.com':
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
    request = Request(url, headers=headers)
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def version_from_tag(tag):
    match = re.fullmatch(r'(?:final-|release-)?(\d+)[_.](\d+)(?:[_.](\d+))?(?:[-_]([a-z0-9]+))?', tag)
    return tuple(int(v or 0) for v in match.groups()[:3]) if match else None


def discover():
    tags = []
    url = 'https://hub.docker.com/v2/repositories/qgis/qgis/tags?page_size=100'
    for page in range(35):
        payload = get_json(url)
        tags.extend(payload.get('results', []))
        url = payload.get('next')
        if not url: break
        if not url.startswith('https://hub.docker.com/'): raise ValueError('Unexpected Docker registry pagination origin')
    else: raise RuntimeError('Docker tag discovery exceeded pagination bound; cannot infer availability')
    releases = []
    for page in range(1, 4):
        payload = get_json('https://api.github.com/repos/qgis/QGIS/tags?per_page=100&page={}'.format(page))
        releases.extend(version_from_tag(item['name']) for item in payload if item['name'].startswith('final-'))
    stable4 = [v for v in releases if v and v[0] == 4 and v[1] % 2 == 0]
    if not stable4: raise RuntimeError('No official stable QGIS 4 release found; latest4 cannot be guessed')
    latest = max(stable4)
    return tags, '{}.{}'.format(*latest[:2])


def resolve(tags, target):
    desired = tuple(int(v) for v in target.split('.'))
    candidates = []
    for entry in tags:
        version = version_from_tag(entry['name'])
        if version and version[:2] == desired and any(i.get('architecture') == 'amd64' and i.get('os') == 'linux' for i in entry.get('images', [])):
            candidates.append((version, entry))
    preferred=('noble','bookworm','focal') if desired[0]==3 else ('questing','trixie','forky')
    candidates.sort(key=lambda item: (item[0], sum((len(preferred)-i) for i,suffix in enumerate(preferred) if suffix in item[1]['name'])), reverse=True)
    if not candidates: return None
    entry = candidates[0][1]
    digest = entry.get('digest')
    if not digest:
        digest = next(i['digest'] for i in entry['images'] if i.get('architecture') == 'amd64' and i.get('os') == 'linux')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest): raise ValueError('Invalid official image digest')
    return {'tag': 'qgis/qgis:' + entry['name'], 'image': 'qgis/qgis@' + digest,
            'digest': digest, 'origin': 'Official QGIS Docker Hub' if not entry['name'].startswith('final-') else 'Archived official QGIS image'}


def target_labels(configuration, mode, latest):
    labels = list(configuration[mode])
    if mode == 'full' and latest:
        major, minor = (int(part) for part in latest.split('.'))
        if major != 4 or minor % 2:
            raise ValueError('Latest stable QGIS 4 must have an even minor version')
        for number in range(0, minor + 1, 2):
            label = '4.{}'.format(number)
            if label not in labels:
                labels.append(label)
    return labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('fast', 'full'), default='fast')
    parser.add_argument('--output', default=str(ROOT / 'compatibility-results/discovery.json'))
    parser.add_argument('--github-output')
    parser.add_argument('--nightly', action='store_true')
    args = parser.parse_args()
    configuration = json.loads((ROOT / 'ci/qgis_targets.json').read_text())
    error = None
    try: tags, latest = discover()
    except Exception as exc: tags, latest, error = [], None, str(exc)
    entries = {}
    for label in target_labels(configuration, args.mode, latest):
        requested = latest if label == 'latest4' else label
        key = requested or label
        if key not in entries:
            entries[key] = {'requested': key, 'aliases': [], 'required': False, 'pdf': False, 'resolution': None}
        row = entries[key]
        row['aliases'].append(label)
        row['required'] |= args.mode == 'full' or label in configuration['required']
        row['pdf'] |= label in configuration['pdf']
        row['resolution'] = resolve(tags, requested) if requested else None
        row['discovery_error'] = error
    result = {'mode': args.mode, 'latest_stable_4': latest, 'targets': list(entries.values()), 'error': error}
    if args.nightly:
        entry=next((entry for entry in tags if entry['name']=='nightly'),None)
        digest=entry.get('digest') if entry else None
        result['targets'].append(dict(requested='nightly',aliases=['nightly'],required=False,pdf=False,
                                      resolution=dict(tag='qgis/qgis:nightly',image='qgis/qgis@'+digest,digest=digest,origin='Official QGIS nightly') if digest else None,
                                      discovery_error=error))
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if args.github_output:
        with open(args.github_output, 'a', encoding='utf-8') as stream:
            stream.write('matrix=' + json.dumps({'include': result['targets']}, separators=(',', ':')) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
