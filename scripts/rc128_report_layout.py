"""Move report archives without changing their bytes or touching runtime state."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = (
    'baseline-30-api42-v4-20261111', 'expansion-v1-20261110',
    'foundation-53-api42-v4-20261112', 'rc128-actual-rework-20261113',
    'rc128-evidence-review-20261111', 'rc128-evidence-review-20261112-r2',
    'rc128-evidence-review-20261112-r3', 'rc128-mechanism-design-20261112-r4',
    'rc128-official-repo-pilot-20261112',
)
LOCAL = (
    'operator-mechanism-pilot-20261112', 'operator-mechanism-rc128-20261112',
    'operator-mechanism-rc128-20261113', 'rc128-rework-audit-20261113',
)


def confined(path):
    path = path.resolve()
    path.relative_to(ROOT.resolve())
    return path


def prepare():
    receipt = ROOT/'reports/evidence/layout_migration.json'
    if receipt.exists():
        raise ValueError('Migration already recorded; use verify instead')
    tracked = set(subprocess.check_output(
        ['git', '-c', 'safe.directory='+ROOT.as_posix(), 'ls-files', '-z'], cwd=ROOT
    ).decode().split('\0'))
    moves = []
    files = []
    for name in PUBLISHED + LOCAL:
        source = confined(ROOT/'reports'/name)
        dest = confined(ROOT/'reports/archive'/('local-experiments' if name in LOCAL else '')/name)
        if not source.is_dir() or dest.exists():
            raise ValueError('Missing source or existing destination: '+name)
        moves.append((source, dest))
        for path in sorted(source.rglob('*')):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            is_tracked = rel in tracked
            target = dest/path.relative_to(source)
            if name in PUBLISHED and not is_tracked:
                target = ROOT/'reports/archive/local-experiments/process-outputs'/name/path.relative_to(source)
            target = confined(target)
            if target.exists():
                raise ValueError('Refusing overwrite: '+str(target))
            data = path.read_bytes()
            files.append({'old_path':rel, 'new_path':target.relative_to(ROOT).as_posix(),
                          'tracked':is_tracked, 'sha256':sha256(data).hexdigest(), 'bytes':len(data)})
    receipt.parent.mkdir(parents=True, exist_ok=True)
    data={'source_commit':subprocess.check_output(
        ['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'published_directories':list(PUBLISHED),'local_directories':list(LOCAL),
        'files':files,'status':'PREPARED'}
    receipt.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for source,dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
    for entry in files:
        if not entry['tracked'] and entry['old_path'].split('/')[1] in PUBLISHED:
            old=ROOT/'reports/archive'/Path(entry['old_path']).relative_to('reports')
            target=ROOT/entry['new_path']
            target.parent.mkdir(parents=True,exist_ok=True)
            old.rename(target)
    data['status']='MOVED'
    receipt.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return verify()


def move_legacy_files():
    """Finish the same migration for the legacy ZIPs and one pilot workbook."""
    receipt=ROOT/'reports/evidence/layout_migration.json'
    data=json.loads(receipt.read_bytes())
    tracked=set(subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','-z'],cwd=ROOT).decode().split('\0'))
    pending=[]
    for source in sorted((ROOT/'reports').iterdir()):
        if not source.is_file() or source.name.startswith('.'):
            continue
        dest=confined(ROOT/'reports/archive'/source.name)
        source=confined(source)
        if dest.exists():raise ValueError('Refusing overwrite: '+str(dest))
        raw=source.read_bytes();rel=source.relative_to(ROOT).as_posix()
        pending.append((source,dest,{'old_path':rel,'new_path':dest.relative_to(ROOT).as_posix(),
            'tracked':rel in tracked,'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}))
    for source,dest,entry in pending:
        source.rename(dest);data['files'].append(entry)
    receipt.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return verify(include_local=True)


def verify(include_local=False):
    data=json.loads((ROOT/'reports/evidence/layout_migration.json').read_bytes())
    failures=[]
    checked=0;local_skipped=0
    for item in data['files']:
        if not item['tracked'] and not include_local:
            local_skipped+=1;continue
        checked+=1
        path=confined(ROOT/item['new_path'])
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            failures.append(item['new_path'])
    result={'passed':not failures,'files':checked,'local_files_not_in_publication':local_skipped,
            'tracked_files':sum(x['tracked'] for x in data['files']),
            'failures':failures,'historical_manifests_rewritten':False,
            'runtime_state_touched':False}
    if failures:
        raise ValueError(result)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['move','move-legacy-files','verify'])
    p.add_argument('--include-local',action='store_true')
    a=p.parse_args()
    print(json.dumps(prepare() if a.action=='move' else move_legacy_files() if a.action=='move-legacy-files' else verify(a.include_local)))
