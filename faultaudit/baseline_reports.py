"""The four requested Baseline artifacts; no source mutation or library adoption."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from .trigger_html import render


def _tsv(path, columns, rows):
    def literal(value):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict,list)) else str(value if value is not None else '')
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t');writer.writerow(columns)
        for row in rows:writer.writerow([literal(row.get(c,'')) for c in columns])


def export(data, output):
    data = {**data, 'report_json_name': 'baseline_30_modes.json'}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    api=[];v4=[]
    for subject in data['subjects']:
        for axis,rows,target in [('API42','rows',api),('V4','v4_rows',v4)]:
            values=[a for a in data['assessments'] if a['case_id']==subject['case_id'] and a.get('baseline_axis')==axis]
            if not values:
                target.append({'mode_id':subject['mode_id'],'applicability':'UNASSESSED','reason':'Task not completed'})
            for a in values:
                result=a['result'];summary=result['classification_summary']
                if not result[rows]:
                    target.append({'mode_id':subject['mode_id'],'assessment_id':a['assessment_id'],
                        'applicability':summary['status'],'reason':summary['reason'],'evidence':result['condition_facts']})
                for row in result[rows]:
                    base={'mode_id':subject['mode_id'],'assessment_id':a['assessment_id'],'applicability':row['applicability'],
                        'reason':row['reason'],'evidence':{'source_cells':row.get('source_cells',[]),'evidence':row.get('evidence',[])}}
                    if axis=='API42':
                        api.append({**base,'api_trigger_id':row['trigger_id'],'definition_version':data['taxonomy']['definition_version']})
                    else:
                        linked={k for link in result['label_links'] if link['scheme']=='V4' and link['trigger_id']==row['trigger_id'] for k in link['construction_ids']}
                        children=[c for c in row['construction_checks'] if c['construction_id'] in linked]
                        for child in children or [None]:
                            v4.append({**base,'v4_theme_id':row['trigger_id'][0],'v4_class_id':row['trigger_id'],
                                'v4_scenario_id':child['construction_id'] if child else '',
                                'construction_recipe':child.get('construction_recipe','') if child else '',
                                'definition_version':data['v4_taxonomy']['definition_version']})
    paths={k:str(output/name) for k,name in {'baseline_html':'baseline_30_modes.html','baseline_json':'baseline_30_modes.json',
        'api_mapping_tsv':'baseline_42_api_mapping.tsv','v4_mapping_tsv':'baseline_v4_mapping.tsv'}.items()}
    Path(paths['baseline_json']).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    Path(paths['baseline_html']).write_text(render(data),encoding='utf-8')
    _tsv(Path(paths['api_mapping_tsv']),['mode_id','api_trigger_id','applicability','reason','definition_version','assessment_id','evidence'],api)
    _tsv(Path(paths['v4_mapping_tsv']),['mode_id','v4_theme_id','v4_class_id','v4_scenario_id','applicability','reason','construction_recipe','definition_version','assessment_id','evidence'],v4)
    return {**paths,'report_html':paths['baseline_html'],'report_json':paths['baseline_json'],
        'primary_report':'HTML','mode_count':len(data['subjects']), 'automatic_adoption':False,
        'status':'COMPLETE_WITH_PENDING' if data['gaps'] else 'COMPLETE','gap_count':len(data['gaps'])}
