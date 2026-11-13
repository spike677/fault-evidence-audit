"""Verify portable input integrity and neutral-projection boundaries offline."""
from __future__ import annotations
from pathlib import Path
import hashlib,json,sys

ROOT=Path(__file__).resolve().parent
CASE_KEYS={'audit_id','case_id','repo','issue_url','source_pr_url','source_refs','input_status','evidence_gaps'}
RECEIPT_KEYS={'audit_id','url','commit','upstream_file','source_ref_id','origin_source_ids','captures','payloads','availability'}

def read_jsonl(path):
 return [json.loads(line)for line in path.read_text('utf8').splitlines()if line.strip()]

def main():
 errors=[];manifest=json.loads((ROOT/'manifest.json').read_text('utf8'))
 for item in manifest['files']:
  p=(ROOT/item['path']).resolve()
  if not p.is_relative_to(ROOT):errors.append('Unsafe path: '+item['path']);continue
  if not p.is_file():errors.append('Missing: '+item['path']);continue
  b=p.read_bytes()
  if len(b)!=item['bytes']or hashlib.sha256(b).hexdigest()!=item['sha256']:
   errors.append('Hash/size mismatch: '+item['path'])
 cases=read_jsonl(ROOT/'cases555/cases.jsonl')
 receipts=read_jsonl(ROOT/'cases555/source_receipts.jsonl')
 rc128=read_jsonl(ROOT/'rc128_original.jsonl')
 if len(cases)!=555 or len({r['audit_id']for r in cases})!=555 or len({str(r['case_id'])for r in cases})!=555:
  errors.append('555 case identity/count mismatch')
 if len(rc128)!=128 or len({r['task_id']for r in rc128})!=128:
  errors.append('128 task identity/count mismatch')
 ids={r['source_ref_id']for r in receipts}
 if len(ids)!=len(receipts):errors.append('Duplicate source reference ID')
 by_id={r['source_ref_id']:r for r in receipts}
 coverage=manifest['cases555']['coverage']
 bundled_cases=0
 for r in cases:
  if set(r)!=CASE_KEYS:errors.append('Non-neutral case fields: '+r['audit_id'])
  if any(k not in ids for k in r['source_refs']):errors.append('Unresolved reference: '+r['audit_id'])
  if any(by_id[s]['audit_id']!=r['audit_id']for s in r['source_refs']if s in by_id):
   errors.append('Source reference belongs to another case: '+r['audit_id'])
  has=any(by_id[s]['payloads']for s in r['source_refs']if s in by_id)
  if has:bundled_cases+=1
  if has!=(r['input_status']=='PARTIAL_PRIMARY_MATERIAL_BUNDLED'):
   errors.append('Incorrect availability state: '+r['audit_id'])
 for r in receipts:
  if set(r)!=RECEIPT_KEYS:errors.append('Unexpected receipt annotations: '+r['source_ref_id'])
  for payload in r['payloads']:
   p=(ROOT/payload['path']).resolve()
   if not p.is_relative_to(ROOT)or not p.is_file():errors.append('Missing/unsafe payload: '+r['source_ref_id']);continue
   b=p.read_bytes()
   if hashlib.sha256(b).hexdigest()!=payload['sha256']or len(b)!=payload['bytes']:
    errors.append('Payload mismatch: '+r['source_ref_id'])
 if bundled_cases!=coverage['cases_with_any_bundled_primary_material']:
  errors.append('Coverage mismatch')
 if coverage['historical_mechanism_assignments_included']or coverage['historical_test_verdicts_included']:
  errors.append('Historical verdicts marked as included')
 print(json.dumps({'passed':not errors,'cases555':len(cases),'handoff128':len(rc128),
  'cases_with_partial_primary_material':bundled_cases,'cases_needing_primary_material':555-bundled_cases,
  'source_references':len(receipts),'checked_files':len(manifest['files']),'errors':errors,
  'validation_scope':'OFFLINE_INPUT_INTEGRITY_ONLY; NOT_SEMANTIC_OR_DEVICE_VALIDATION'},ensure_ascii=False))
 return 0 if not errors else 1

if __name__=='__main__':raise SystemExit(main())
