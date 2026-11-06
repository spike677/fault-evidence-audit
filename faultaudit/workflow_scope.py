"""A frozen workflow view over the existing run; historical rows stay intact."""
from __future__ import annotations

from .store import AuditError, digest


class ScopedStore:
    def __init__(self, store, run_id, case_ids):
        self.unscoped = getattr(store, 'unscoped', store)
        self.run_id = run_id
        self.case_ids = frozenset(case_ids)
        self.scope_hash = digest(sorted(self.case_ids))

    def __getattr__(self, name):
        return getattr(self.unscoped, name)

    def _snapshot_ids(self):
        from .resource_identity import resource_key
        urls = {resource_key(r['url']) for r in self.unscoped.records(self.run_id, 'references')
                if r['case_id'] in self.case_ids and r.get('url') and r.get('status') == 'PARSED'}
        ids = {a['snapshot_id'] for a in self.unscoped.records(self.run_id, 'evidence_associations')
               if a['case_id'] in self.case_ids and a.get('snapshot_id')}
        return ids | {s['snapshot_id'] for s in self.unscoped.records(self.run_id, 'snapshots')
                      if resource_key(s['url']) in urls}

    def records(self, run_id, kind):
        values = self.unscoped.records(run_id, kind)
        if run_id != self.run_id:
            return values
        if kind == 'cases':
            return [v for v in values if v['case_id'] in self.case_ids]
        if kind in {'references', 'evidence_associations', 'judgments', 'mappings', 'wiki_checks'}:
            return [v for v in values if v.get('case_id') in self.case_ids]
        if kind == 'search_policies':
            return [v for v in values if not v.get('case_id') or v['case_id'] in self.case_ids]
        if kind == 'event_groups':
            # A partial group cannot propagate a representative's conclusion
            # from outside this explicitly selected scope.
            return [v for v in values if set(v['case_ids']) <= self.case_ids]
        if kind in {'snapshots', 'summaries'}:
            ids = self._snapshot_ids()
            return [v for v in values if v['snapshot_id'] in ids]
        if kind == 'heads':
            ids = self._snapshot_ids()
            return [v for v in values if v['snapshot_id'] in ids]
        if kind == 'model_tasks':
            ids = self._snapshot_ids()
            return [v for v in values if (v['payload'].get('case') or {}).get('case_id') in self.case_ids
                    or v.get('kind') == 'summarize' and v['payload']['snapshot']['snapshot_id'] in ids]
        if kind == 'model_results':
            ids = {v['task_id'] for v in self.records(run_id, 'model_tasks')}
            return [v for v in values if v['task_id'] in ids]
        if kind in {'documents', 'exclusions'}:
            shas = {c['source_sha256'] for c in self.records(run_id, 'cases')}
            shas.update(c['source_sha256'] for c in self.unscoped.records(run_id, 'catalog'))
            return [v for v in values if v.get('source_sha256') in shas]
        return values

    def get(self, run_id, kind, key):
        value = self.unscoped.get(run_id, kind, key)
        if value and run_id == self.run_id:
            if kind == 'cases' and value['case_id'] not in self.case_ids:
                return None
            if kind in {'references', 'judgments', 'mappings', 'evidence_associations'} and value.get('case_id') not in self.case_ids:
                return None
        return value

    def active_snapshots(self, run_id):
        from .resource_identity import snapshot_index
        ids = {h['snapshot_id'] for h in self.records(run_id, 'heads')}
        return list(snapshot_index([s for s in self.records(run_id, 'snapshots') if s['snapshot_id'] in ids]).values())

    def ingest_evidence(self, run_id, package, base_dir=None):
        if set(package.get('case_ids', [])) - self.case_ids:
            raise AuditError('Evidence package is outside the frozen workflow scope')
        return self.unscoped.ingest_evidence(run_id, package, base_dir)


def scoped_store(store, run_id):
    if isinstance(store, ScopedStore):
        return store
    cfg = store.get(run_id, 'xlsx_workflow', 'config') or {}
    ids = cfg.get('selected_case_ids')
    return ScopedStore(store, run_id, ids) if ids else store
