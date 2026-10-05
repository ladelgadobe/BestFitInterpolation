"""Require a clean checker log or narrowly reviewed, documented findings."""
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def review(folder):
    result=json.loads((folder/'checker.json').read_text())
    if result['status']!='STATICALLY_CHECKED' or result.get('source_modified'):
        raise RuntimeError('The official read-only checker did not complete.')
    log=(folder/'pyqgis4-checker.log').read_text(encoding='utf-8')
    configuration=json.loads((ROOT/'ci/checker_reviews.json').read_text())
    findings=[line for line in log.splitlines() if '.py:' in line or 'WARNING:' in line or 'ERROR:' in line]
    unreviewed=[]
    for line in findings:
        accepted=False
        for entry in configuration['reviews']:
            if entry['file'] in line and re.search(entry['diagnostic_pattern'],line):
                source=(ROOT/entry['file']).read_text(encoding='utf-8')
                if entry['guarded_source'] in source and entry['reason']: accepted=True
        if not accepted: unreviewed.append(line)
    result.update(findings=findings,unreviewed=unreviewed,review_required=bool(unreviewed))
    (folder/'checker.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Official checker findings: {}; unreviewed: {}'.format(len(findings),len(unreviewed)))
    if unreviewed: print('\n'.join(unreviewed))
    return 1 if unreviewed else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    raise SystemExit(review(Path(args.folder)))
