"""Mechanical scaffolding for explicitly synthetic structural test responses.

Never used by real Agent executions or the manual 30-record validation.
"""
import copy
from faultaudit.trigger_assessment import CLASSIFICATION_FRAMEWORK
from faultaudit.trigger_taxonomy import BRANCH_ROLES, condition_role_requirements


def canonical_checks(item, families):
    family = families.get(item.get('family_id'), {})
    return [('INCLUSION', x) for x in sorted({item['definition'].strip()} | {
        v.strip() for source in (item, family) for v in source.get('requires', [])}) if x] + [
        ('EXCLUSION', x) for x in sorted({v.strip() for source in (item, family) for v in source.get('skip_if', [])}) if x]


def condition_attempt(payload, response):
    if payload.get('classification_framework') != CLASSIFICATION_FRAMEWORK:
        return response
    response.setdefault('condition_facts', [])
    families = {f['family_id']: f for f in payload['taxonomy'].get('families', [])}
    items = {i['id']: i for i in payload['taxonomy']['items']}
    for row in response['rows']:
        old = {(c.get('clause_role', 'INCLUSION'), c['clause']): c for c in row.get('predicate_checks', [])}
        row['predicate_checks'] = [copy.deepcopy(old.get((role, clause), {
            'clause_role': role, 'clause': clause, 'result': 'UNKNOWN'})) for role, clause in canonical_checks(items[row['trigger_id']], families)]
        if row['applicability'] != 'UNKNOWN':
            fact_id = 'synthetic-' + row['trigger_id']
            web = bool(row.get('evidence'))
            fact = {'fact_id': fact_id, 'statement': 'Explicit synthetic test condition',
                'role': next(iter(condition_role_requirements(row['trigger_id'])), 'INPUT_SHAPE'),
                'subject': 'CURRENT_ISSUE' if web else 'SOURCE_RECORD',
                'evidence_basis': 'SOURCE_REPORTED' if web else 'SOURCE_DEFINITION',
                'evidence': copy.deepcopy(row.get('evidence', [])),
                'source_cells': copy.deepcopy(row.get('source_cells', []))}
            response['condition_facts'].append(fact)
            row['condition_fact_ids'] = [fact_id]
            for check in row['predicate_checks']:
                if check['result'] != 'UNKNOWN': check['condition_fact_ids'] = [fact_id]
    for branch in response['external_branches']:
        definition = next((b for b in payload['taxonomy'].get('branches', []) if b['branch_id'] == branch['branch_id']), {})
        branch['category_checks'] = [{'category_id': c['id'], 'applicability': 'UNKNOWN',
            'reason': 'Synthetic source does not state this condition', 'unknowns': ['Missing specific condition']} for c in definition.get('categories', [])]
    return response
