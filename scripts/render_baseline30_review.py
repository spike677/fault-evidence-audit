"""Replay the frozen baseline-30 publication; no model, website or device calls."""
from pathlib import Path
import argparse, hashlib, html, json, re, sys, zipfile

TEMPLATE = Path(__file__).with_name('baseline30_template.html')
REPORT = 'CANN_30_MODES_API42_V4_REVIEW.html'
LEVELS = ('L1','L2','L3','L4')

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj): Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def cell(x): return str(x).replace('|','\\|').replace('\n',' ')

def markdown(data):
    lines=['# 原30条CANN模式：API42与V4逐条说明','',
      '2026-11-11讨论更新版。按原表顺序保留M编号。分类依据为原模式声明、既有Wiki/DTS摘要及已记录技术推导；历史网页原始快照尚未在本机重新核验。','',
      '[完整离线HTML](CANN_30_MODES_API42_V4_REVIEW.html) · [完整结构化数据](review_data.json) · [OpenChamber续接说明](CHAMBER_HANDOFF.md) · [本机Init查找结果](local_init_search.json)','',
      '## 状态与口径','',
      '- 数据Init：30/30完成；该COMPLETE只表示数据初始化，不是A1–A5工作流完成或Baseline冻结。',
      '- API42：L1技术相关18/42，L2历史摘要代表3/42，L3测试设计3/42，L4设备验证0/42。',
      '- V4：L1技术相关21/55，L2历史摘要代表6/55，L3测试设计4/55，L4设备验证0/55。',
      '- 62条稀疏关系：API42 25条、V4 37条。关系数、模式数和唯一条件数分别统计，各层不相加。',
      '- V4保持6主题、31条件类、55种构造、64挂载、195指导案例及独立E1–E5；真实机理另列，不把55称为失效机理。',
      '- M006的minus_one为本次讨论暂记；M026保留待补证；M004增加参数传播机理说明。三项更新未静默升级历史代表或设备覆盖。','',
      '## 原始资料和state','',
      '本次按用户明确指示附原始数据Init、现有本机来源转录和历史预检state。ZIP内保留原字节及逐文件SHA；没有伪造或恢复缺失的现场数据库。','',
      '- [原始Init及来源资料](original_init_and_sources.zip)：数据Init、原模式字段、证据/来源台账、两份Markdown转录、原API42及V4。',
      '- [原30条历史预检state](legacy_original30_preflight.zip)：0.1.17数据库、两个run的任务目录、原输入JSON。每run 30条记录、30个请求、0个完成结果。',
      '- [逐文件SHA-256](archive_manifest.json) · [可用性及缺失清单](availability.json)。',
      '- 现场run `run-20261109T065009Z-37f05b15`、原始`cann_modes.xlsx`和28份原始网页采集快照未在可读本机范围找到。',
      '- 已找到的旧`init_frozen_baseline.json`对应15类`INF-*`，不作为本轮30条基线。','',
      '## 按原表顺序逐条说明','',
      '|原序／M编号|原模式名称|API42关联|V4构造关联|最新讨论|','|---|---|---|---|---|']
    for m in data['modes']:
        d=m.get('discussion_classification',{})
        note=d.get('note')or d.get('mechanism_refinement')or'无本次讨论改动'
        v4=', '.join(m['v4_scenario_ids'])or'暂无已建立关系'
        if d.get('v4_scenario_ids'):v4+='；讨论暂记：'+', '.join(d['v4_scenario_ids'])
        lines.append('|'+ '|'.join(map(cell,[f"{m['original_order']}／{m['mode_id']}",m['mode_name'],', '.join(m['api42_ids'])or'暂无已建立关系',v4,note]))+'|')
    for m in data['modes']:
        lines += ['',f"### 原第{m['original_order']}条／{m['mode_id']}：{m['mode_name']}",'',
          '**原始定义：** '+m['original_definition'],'',
          '**机理整理：** '+m['failure_mechanism']['text'],'',
          '**输入／实现情境：** '+m['input_trigger_conditions']['text']+'；'+m['execution_trigger_conditions']['text'],'',
          '**分类说明：** '+m['analysis_note'],'']
        if m.get('discussion_classification'):
            d=m['discussion_classification']
            lines += ['**2026-11-11讨论更新：** '+(d.get('note')or d.get('mechanism_refinement')),'',
              '```json',json.dumps(d,ensure_ascii=False,indent=2),'```','']
        edges=[r for r in data['relations']if r['mode_id']==m['mode_id']]
        if not edges:lines += ['当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。','']
        for r in edges:
            lines += [f"- **{r['condition_system']} `{r['condition_id']}`** · {' / '.join(r['coverage_levels'])} · {r['basis']}",
              '  - 理由：'+r['reason'],'  - 限制：'+r['limitation'],
              '  - 证据：'+', '.join(r['evidence_ids'])]
        lines += ['', '**待确认项：** '+'；'.join(m['unresolved_gaps']),'',
          f"证据状态：{m['mode_definition_status']}；原文独立核验={m['source_verified']}；设备验证={m['hardware_validated']}。"]
    lines += ['','## 复现本报告','', '```sh',
      'python scripts/render_baseline30_review.py render reports/archive/baseline-30-api42-v4-20261111',
      'python scripts/render_baseline30_review.py verify reports/archive/baseline-30-api42-v4-20261111',
      'node scripts/verify_baseline30_ui.cjs reports/archive/baseline-30-api42-v4-20261111','```','',
      '命令仅重放已冻结的数据和检查离线报告，不重新运行Init、采集、模型或设备。历史验证回执保留其原日期和范围，新发布检查单独记录。','']
    return '\n'.join(lines)

def render(folder):
    folder=Path(folder);data=load(folder/'review_data.json')
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    text=TEMPLATE.read_text(encoding='utf-8').replace('__COVERAGE_DATA__',payload).replace('__UI_VERIFICATION__','浏览器预览未完成：computer-use无法可靠识别Windows当前浏览器URL，已停止UI操作。离线逻辑检查已通过；设备执行为0。')
    (folder/REPORT).write_text(text,encoding='utf-8',newline='\n')
    (folder/'README.md').write_text(markdown(data),encoding='utf-8',newline='\n')

def manifest(folder):
    folder=Path(folder)
    files={p.relative_to(folder).as_posix():sha(p)for p in sorted(folder.rglob('*'))
           if p.is_file()and p.name!='manifest.json'and p.parent.name!='validation'}
    dump(folder/'manifest.json',{'report_version':'BASELINE30-DISCUSSION-EXPORT-1','payload_sha256':files,
        'archives_preserve_original_bytes':True,'runtime_state_never_modified':True})

def verify(folder):
    folder=Path(folder);b=load(folder/'review_data.json');checks=[]
    def check(name,ok):
        checks.append({'name':name,'status':'PASS'if ok else'FAIL'})
    modes=b['modes'];edges=b['relations'];byid={m['mode_id']:m for m in modes}
    check('30_unique_modes_original_order',len(byid)==30 and [m['original_order']for m in modes]==list(range(1,31))and [m['mode_id']for m in modes[:4]]==['M020','M006','M026','M004'])
    check('42_55_independent_complete_definitions',len(b['api42']['conditions'])==42 and len(b['v4']['conditions'])==55 and b['v4']['class_count']==31 and b['v4']['mount_count']==64 and b['v4']['guidance_count']==195)
    check('62_sparse_unique_relations',len(edges)==len({e['relation_id']for e in edges})==62)
    check('all_relations_have_explanation_and_source',all(r['reason']and r['limitation']and r['original_facts']and r['source_reference']for r in edges))
    for key,expected in [('api42',[18,3,3,0]),('v4',[21,6,4,0])]:
        ledger=b[key]
        actual=[len({r['condition_id']for r in edges if r['condition_system']==ledger['system']and level in r['coverage_levels']})for level in LEVELS]
        check(key+'_unique_condition_counts',actual==expected and actual==[ledger['coverage_counts'][k]for k in LEVELS])
        check(key+'_all_predicates_preserved',all(c.get('definition')and (c.get('family_source')if key=='api42'else c.get('original_class_predicates'))for c in ledger['conditions']))
    check('3_discussion_notes_separate',len(b['discussions'])==3 and {r['mode_id']for r in b['discussions']}=={'M006','M026','M004'})
    check('M006_minus_one_provisional_only',byid['M006']['discussion_classification']['v4_scenario_ids']==['minus_one']and not any(r['mode_id']=='M006'and r['condition_id']=='minus_one'for r in edges))
    check('M026_retained_no_evidence_upgrade',byid['M026']['discussion_classification']['status']=='RETAIN_PENDING_EVIDENCE'and not byid['M026']['discussion_classification']['evidence_confirmed'])
    check('M004_config_mechanism_not_low_probability',byid['M004']['discussion_classification']['reproduction_status']=='CONDITIONS_REQUIRED_RATE_UNKNOWN'and byid['M004']['discussion_classification']['v4_class_candidates']==['C4']and not byid['M004']['discussion_classification']['v4_scenario_ids'])
    check('no_auto_accept_no_freeze_no_device',b['publication']['new_human_accepts']==b['publication']['new_baseline_freezes']==b['publication']['device_runs']==0 and not any(m['hardware_validated']for m in modes))
    check('init_state_scopes_honest',b['availability']['data_init']['scope']=='DATA_INITIALIZATION_ONLY'and b['availability']['legacy_preflight']['accepted_workflow_results']==0 and not b['availability']['onsite_run']['database_included']and not b['availability']['old_frozen_files']['usable_as_this_30_mode_baseline'])
    entries=load(folder/'archive_manifest.json')['entries'];valid=True
    for name in {e['archive']for e in entries}:
        with zipfile.ZipFile(folder/name)as z:
            valid &= z.testzip()is None
            for e in entries:
                if e['archive']==name:valid &= hashlib.sha256(z.read(e['path'])).hexdigest()==e['sha256']
    check('original_archive_87_entries_byte_hashes',valid and len(entries)==87)
    check('original_rule_bytes_match_frozen_ledgers',
        next(e['sha256']for e in entries if e['path']=='knowledge/trigger_library.md')==b['api42']['source_sha256']and
        next(e['sha256']for e in entries if e['path']=='knowledge/precision_trigger_knowledge_v4.md')==b['v4']['source_sha256'])
    raw=(folder/REPORT).read_text(encoding='utf-8')
    payload=re.search(r'<script id="coverage-data" type="application/json">([\s\S]*?)</script>',raw)[1]
    check('full_html_embeds_all_review_data',json.loads(payload)==b)
    check('offline_no_network_script',not re.search(r'<script[^>]+src=|<link[^>]+href=|\bfetch\s*\(|XMLHttpRequest|WebSocket',raw))
    check('manifest_hashes',all(sha(folder/n)==h for n,h in load(folder/'manifest.json')['payload_sha256'].items()))
    check('init_registry_preserved',len(b['legacy_id_cross_reference'])==30 and b['availability']['data_init']['source_sha256']==next(e['sha256']for e in entries if e['path']=='init/cann_30_init.json'))
    return {'status':'PASS'if all(c['status']=='PASS'for c in checks)else'FAIL',
      'python':sys.version,'dependencies':'Python standard library only','check_count':len(checks),
      'passed':sum(c['status']=='PASS'for c in checks),'checks':checks,
      'scope':'PUBLICATION_REPLAY_AND_ARCHIVE_INTEGRITY_NOT_MODEL_OR_DEVICE_OR_FULL_APP_REGRESSION',
      'onsite_run_restored':False,'model_calls':0,'device_runs':0}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['render','manifest','verify']);p.add_argument('folder',type=Path)
    a=p.parse_args()
    if a.action!='verify' and (folder_archive := (Path(__file__).resolve().parents[1]/'reports/archive').resolve()) in a.folder.resolve().parents:
        raise ValueError('Archived Baseline is read-only; do not regenerate historical reports.')
    if a.action=='render':render(a.folder)
    elif a.action=='manifest':manifest(a.folder)
    else:
        r=verify(a.folder);print(json.dumps(r,ensure_ascii=False,indent=2));sys.exit(0 if r['status']=='PASS'else 1)
