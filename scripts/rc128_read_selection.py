"""Print bounded evidence selections and retain the exact read ranges."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/archive/rc128-actual-rework-20261113'
LOG = ROOT / 'reports/evidence/read_selections_legacy_format.jsonl'


def run():
    p = argparse.ArgumentParser()
    p.add_argument('collection')
    p.add_argument('start', type=int)
    p.add_argument('count', type=int)
    p.add_argument('--kind', default='BODY')
    p.add_argument('--chars', type=int, default=2400)
    p.add_argument('--offset', type=int, default=0)
    p.add_argument('--needle')
    p.add_argument('--regex')
    p.add_argument('--occurrence', type=int, default=0)
    a = p.parse_args()
    jobs = json.loads((OUT / a.collection).read_bytes())
    jobs = [j for j in jobs if j.get('kind') == a.kind]
    for j in jobs[a.start:a.start+a.count]:
        if 'text_file' in j:
            body = (OUT / j['text_file']).read_text(encoding='utf-8')
            key = j['resource_id']
        else:
            structured = j.get('response', {}).get('structuredContent', {})
            obj = structured.get('issue', structured.get('pull_request', {}))
            body = obj.get('title', '') + '\n' + obj.get('body', '')
            key = 'GH-' + hashlib.sha256(j['url'].encode()).hexdigest()[:20]
        start = min(len(body), a.offset)
        if a.needle:
            matches = list(re.finditer(re.escape(a.needle), body))
            if not matches:
                print(json.dumps({'resource_id': key, 'needle_not_found': a.needle}))
                continue
            at = matches[a.occurrence].start()
            start = max(0, at - 350)
        if a.regex:
            matches = list(re.finditer(a.regex, body))
            if not matches:
                print(json.dumps({'resource_id': key, 'regex_not_found': a.regex}))
                continue
            start = max(0, matches[a.occurrence].start()-250)
        end = min(len(body), start+a.chars)
        selection = {'resource_id': key, 'url': j['url'], 'task_ids': j['task_ids'],
                     'kind': a.kind, 'start': start, 'end': end, 'total_chars': len(body),
                     'first_line': body[:start].count('\n')+1,
                     'last_line': body[:end].count('\n')+1,
                     'read_at': datetime.now(timezone.utc).isoformat(),
                     'selection_sha256': hashlib.sha256(body[start:end].encode()).hexdigest()}
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(json.dumps(selection, ensure_ascii=False) + '\n')
        print(json.dumps({**selection, 'text': body[start:end]}, ensure_ascii=False))


if __name__ == '__main__':
    run()
