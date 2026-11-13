"""R2 overlay on an immutable R1 bundle. No fetch, model, state or device client."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import rc128_review as core
from rc128_six_reviews import SIX, SHARED, EXPECTED, REVIEWS, quantities, review

VERSION='RC128-DRIVING-QUANTITY-REVIEW-2'
SOURCE_COMMIT='f4a8497063c63403e8a68a1d5870e97c5d7cd59c'
INVARIANTS=core.REPO.parent/'docs/reviews/cann53_42_55_20261111/snapshot/work/ascend_pattern_comparison_20261111/ascend-op-fault-patterns/INVARIANTS.md'
CODE=['scripts/rc128_review.py','scripts/rc128_decisions.py','scripts/rc128_six_reviews.py',
      'scripts/rc128_revision.py','scripts/rc128_search_queries.txt']
EXCLUDED={'manifest.json','validation.json','ui_validation.json','test_results.txt','git_publication.json'}


def file_hashes(folder):
    return {p.relative_to(folder).as_posix():core.sha(p)for p in sorted(folder.rglob('*'))if p.is_file()}


def axis(status,reason,refs,unknown):
    return dict(status=status,reason=reason,evidence_ids=list(refs),unknown_reason=unknown,
                defect_confirmation_required=False)


def classify(c, definitions):
    """Classify a scenario; each mount remains independent, never inherited."""
    c=deepcopy(c);cid=c.get('task_id');refs=c['source_evidence_ids'];key=(cid,c['system'],c['condition_id'])
    if cid=='RC-029':
        c['missing']='两个scale变量的完整定义、类型、数值含义、函数签名、载荷对应及合法输入待核。'
        c['predicate_checks']=deepcopy(c['predicate_checks'])
        for k in ['requires','skip_if']:
            for p in c['predicate_checks'].get(k,[]):
                if isinstance(p,dict)and'reason'in p:p['reason']=c['missing']
    reason='本轮仅分离原记录的分类与构造状态；未重新做完整Requires／Skip语义审读。'
    state='HISTORICAL_PARTIAL_OR_UNKNOWN';feasibility='NOT_ASSESSED'
    unknown=c.get('missing')or'完整合法域、接口契约及构造能力未重新核对。'
    if cid in SIX:
        state='CONDITIONAL_SOURCE_CLASSIFICATION'
        reason='来源给出相关条件线索；须核对目标调用合法域及该类别完整Requires／Skip，未确认缺陷。'
    if key==('RC-009','V4','view_stride'):
        state='CONDITIONALLY_APPLICABLE'
        reason='来源明确对照连续／非连续输入。若接口允许相应stride，则T1语义可适用；不以缺陷确认作为分类前提。'
        unknown='目标接口是否允许该view、stride单位与构造后是否保留原stride待核。'
        feasibility='EXECUTOR_CAPABILITY_UNKNOWN'
    elif key==('RC-009','API42','1.4.1'):
        state='SCHEMA_CONDITIONAL'
        reason='原42条定义含not testable／schema暴露stride限制，须保持原定义；此限制不转换为V4表达能力缺失。'
    elif key==('RC-029','V4','scale_structure'):
        state='UNKNOWN';reason='S7需要scale形状／轴与载荷的对应依据；仅涉及scale不能成立。'
        unknown='未取得两scale的shape、广播／轴对应和合法域。'
    elif key==('RC-062','V4','zeros'):
        state='CONDITIONAL_SOURCE_CLASSIFICATION'
        reason='来源声明sin／cos全零，可条件化登记N3／zeros；合法域与两侧目标调用可比时语义适用，不要求先证明kernel缺陷。'
        unknown='目标调用、位置、配置、shape／dtype及全零是否属于合法域待核。'
    elif cid=='RC-062':
        state='UNKNOWN';reason='pe／nope及RoPE上下文未证明接口暴露相应模式控制，不由关键词直接建立控制条件。'
    if c.get('technical_case_id')=='TC-FP8-VSCALE':
        c['reason']='历史选段只证实参数替换；完整变量类型、数值语义和参数合同待核。'
        c['issue_scope']='scale参数替换选段，不推导对象阶段。'
    c['semantic_applicability']=axis(state,reason,refs,unknown)
    c['construction_feasibility']=axis(feasibility,'本轮无执行器／设备验证；语义适用不代表已构造或命中路径。',refs,
                                      '实际输入构造、stride保留、目标路径和参考结果均未执行。')
    c['applicability']='SEE_SEPARATE_SEMANTIC_AND_CONSTRUCTION_AXES'
    c['reason']=reason if cid in SIX else c['reason']
    c['review_scope']='SIX_CASE_CONDITIONAL_CLASSIFICATION' if cid in SIX else 'AXIS_SPLIT_ONLY_HISTORICAL_ANALYSIS_REUSED'
    c['defect_confirmed']=False
    c['class_assessments']=[]
    for mount in c['class_ids']:
        ms=state;mr=reason
        if key==('RC-023','V4','index_mask') and mount=='C4':
            ms='UNKNOWN';mr='有效集合线索不自动证明行为模式或输入到分派的完整谓词；C4单独待核。'
        if key==('RC-029','V4','enum_quant') and mount=='C2':
            ms='UNKNOWN';mr='FP8静态量化上下文不自动证明显式API模式／合法输入到内部策略的可追踪谓词。'
        definition=definitions[(c['system'],c['condition_id'])]
        def in_mount(x):
            return not isinstance(x,dict) or x.get('class_id',mount)==mount
        c['class_assessments'].append(dict(class_id=mount,status=ms,reason=mr,
            requires=[x for x in definition['requires'] if in_mount(x)],skip_if=[x for x in definition['skip_if'] if in_mount(x)],
            evidence_ids=list(refs),unknown_reason=unknown))
    return c


def reconcile(source_data, mode_index, definitions):
    data=deepcopy(source_data);rs=data['results'];fs=data['failures'];cs=data['conditions'];ms=data['comparisons'];ts=data['technical_cases']
    corrections=[];driving=[];reviews=[]
    def change(obj,key,value,scope,why):
        old=deepcopy(obj.get(key))
        if old==value:return
        corrections.append(dict(entity_id=obj.get('task_id')or obj.get('technical_case_id')or obj.get('relation_id'),
            record_id=obj.get('relation_id')or obj.get('comparison_id'),field=key,previous_value=old,new_value=deepcopy(value),
            scope=scope,reason=why,source_revision=SOURCE_COMMIT))
        obj[key]=value
    rmap={r['task_id']:r for r in rs}
    for r in rs:
        cid=r['task_id']
        r['review_scope']='DRIVING_QUANTITY_REVIEW_WITH_GAPS' if cid in SIX else 'SHARED_TEMPLATE_CORRECTION_ONLY' if cid in SHARED else 'HISTORICAL_ANALYSIS_REUSED'
        r['review_policy']=VERSION
        if cid in SIX:
            refs=[e for e in r['evidence_ids']if ':fault:'in e or ':related_internal_facts:'in e]
            if cid=='RC-029':refs+=['OBS:TC-FP8-VSCALE:1:before','OBS:TC-FP8-VSCALE:1:after']
            q=quantities(cid,refs);rv=review(cid,refs,mode_index);driving+=q;reviews.append(rv)
            change(r,'root_cause',dict(conclusion=rv['candidate_mechanism']['known']+' '+rv['candidate_mechanism']['unknown'],
                   basis='SOURCE_DECLARED_WITH_BOUNDED_ANALYSIS',independently_confirmed=False),r['review_scope'],'区分声明、选段事实与待核解释。')
            r['quantity_ids']=rv['quantity_ids'];r['review_status']='PENDING_RELATION_REVIEW'
            change(r,'unresolved_gaps',[rv['candidate_mechanism']['unknown'],rv['targeted_evidence_gap']],r['review_scope'],
                   '旧缺口可能预设错误原因；历史值保留在纠正记录，当前使用中性补证问题。')
    for f in fs:
        cid=f.get('task_id')or f.get('technical_case_id')
        if cid in EXPECTED:
            scope='DRIVING_QUANTITY_REVIEW_WITH_GAPS' if cid in SIX else 'SHARED_TEMPLATE_CORRECTION_ONLY'
            change(f,'expected_relation',EXPECTED[cid],scope,'按具体子问题纠正共享模板携带的对象／构造／阶段断言。')
            f['review_scope']=scope
            if cid in SIX:
                rv=next(x for x in reviews if x['task_id']==cid)
                for k,v in dict(mechanism_title=REVIEWS[cid]['title'],actual_relation=rv['candidate_mechanism']['known'],
                    cause_chain=rv['candidate_mechanism']['known']+' 因果关系尚未独立确认。',
                    measurement_and_representation='按下列驱动量的Q2逐项核对；编码／定义域不强行写成单位错误。',
                    lifecycle='逐驱动量分别记录创建、初始化、可写主体和复位；未核责任保留未知。',
                    consumers='按驱动量Q4记录消费者及未知；Q4未确定时不确认Q2错误。',
                    trigger_predicate='需核目标调用、合法域和实际消费契约；来源描述不等于已确认触发谓词。',
                    alternative_explanations=rv['candidate_mechanism']['alternatives'],
                    unresolved=[rv['candidate_mechanism']['unknown'],rv['targeted_evidence_gap']]).items():
                    change(f,k,v,scope,'收紧为来源支持范围内的关系待核分析。')
                f['driving_quantity_ids']=rv['quantity_ids'];f['relation_confirmed']=False
            else:
                change(f,'lifecycle','只核对本子问题对象的创建、赋值、消费及复位；本轮未完成逐驱动量生命周期审读。',scope,'删除模板阶段／构造副作用推断，未扩大审查范围。')
                if cid=='RC-051':
                    change(f,'measurement_and_representation','计数API的输入域、bin边界、输出类型与约定待核；未确认ctrl状态。',scope,'histc/bincount未直接定位ctrl初始化。')
                    change(f,'consumers','专家token计数的后续使用路径待核，不默认是依赖ctrl的kernel。',scope,'取消寄存器消费者继承。')
                if cid in ['RC-060','RC-111']:
                    change(f,'consumers','仅核对本条所述scale实际消费者；不同API默认值与scale=1规避均不能证明对象错绑。',scope,'取消具体阶段推断。')
    for m in ms:
        cid=m.get('task_id')or m.get('technical_case_id')
        if cid=='RC-060':
            change(m,'reason','与RC-029均存在scale路径线索；本条没有定位到同一参数关系，不确认同机理或同事件。',
                   'SHARED_TEMPLATE_CORRECTION_ONLY','删除未经支持的阶段关联。')
        if cid in SIX or cid=='TC-FP8-VSCALE':
            why=REVIEWS[cid]['boundary'] if cid in SIX else '仅确认历史选段参数替换；变量对象、数值与调用契约待核，不能确定新增或扩展。'
            for k,v in dict(action='PENDING',decision_scope='RELATION_ANALYSIS_AND_TENTATIVE_CARD_DISCUSSION_ONLY',
                reason=why,mechanism_candidate=REVIEWS[cid]['title'] if cid in SIX else 'scale实参与载荷契约关系待核',
                proposed_pattern_name=None).items():
                change(m,k,v,'PENDING_ADJUDICATION','四问齐备不产生新增／扩展决定。')
            m['adjudication_status']='PENDING'
            if cid in SIX:
                change(m,'closest_mode_differences',[dict(mode_id=k,common=REVIEWS[cid]['common'],boundary=why)for k in REVIEWS[cid]['modes']],
                       'PENDING_ADJUDICATION','边界讨论与优先归卡建议分开。')
    for t in ts:
        if t['technical_case_id']=='TC-FP8-VSCALE':
            replacements=dict(title='V scale参数替换：完整契约待核',failure_mechanism='历史选段记录deScalePreVValue替换为deScaleVValue；对象、类型和数值语义待核。',
                trigger_predicate='完整变量定义、函数签名及输入对照待核；选段不是完整触发条件。',
                comparison_reason='参数替换不足以确认独立对象错绑机理，暂保留待核关系讨论。',
                relation_reason='M010／M024的边界待完整调用契约后比较，不自动新增。',action='PENDING',
                mechanism_relation='UNDETERMINED',candidate_id=None)
            for k,v in replacements.items():change(t,k,v,'SHARED_TEMPLATE_CORRECTION_ONLY','移除变量名推导的块／时间语义。')
        if t['technical_case_id']in ['TC-FP8-VSCALE','TC-SFAG-EVENT-ID']:
            t['review_scope']='SHARED_TEMPLATE_CORRECTION_ONLY_NOT_QUANTITY_REVIEW'
    for f in fs:
        if f.get('technical_case_id')=='TC-FP8-VSCALE':
            for k,v in dict(issue_scope='scale参数替换选段',mechanism_title='scale实参与载荷契约关系待核',actual_relation='历史选段记录deScalePreVValue替换为deScaleVValue。',
                cause_chain='参数替换事实可定位；完整因果链待定义、签名、调用与数值对照。',
                object_roles='deScalePreVValue、deScaleVValue及被消费载荷；完整对象和类型未知。',
                measurement_and_representation='两个scale变量的类型、数值含义和对应载荷未完整核验，不由变量名指定阶段或轴。',
                trigger_predicate='需取得变量定义和函数契约，不能由变量名确认触发条件。',
                semantic_detail=dict(parameter_change='deScalePreVValue → deScaleVValue',object_semantics='UNKNOWN',
                  stage_semantics='UNKNOWN',full_source_reviewed=False,hardware_validated=False)).items():
                change(f,k,v,'SHARED_TEMPLATE_CORRECTION_ONLY','仅保留选段参数替换事实。')
    # Add a conditional description-level tag without inventing a kernel defect.
    d=definitions[('V4','zeros')];refs=[x for x in rmap['RC-062']['evidence_ids']if ':fault:'in x]
    cs.append(dict(relation_id='RC-062:V4:zeros',task_id='RC-062',entity_type='WEEKLY_RECORD',system='V4',condition_id='zeros',
        class_ids=d['class_ids'],theme_ids=d['theme_ids'],status='CONDITIONAL_SOURCE_CLASSIFICATION',applicability='PARTIAL_OR_UNKNOWN',
        reason='来源声明sin／cos全零；合法域与目标调用可比时可作N3来源层分类。',missing='合法域、目标调用、位置及配置可比性待核。',
        issue_scope='RC-062辅助张量内容差异',issue_scope_map=['RC-062:REL-01'],source_evidence_ids=refs,
        definition_ref=dict(file='condition_definitions.json',system='V4',condition_id='zeros'),
        predicate_checks=dict(observed_condition='来源声明全零，未独立确认',requires=d['requires'],skip_if=d['skip_if']),
        source_verified=False,hardware_validated=False,historical_event_confirmed=False,counts_as_verified_coverage=False))
    classified=[]
    for c in cs:
        new=classify(c,definitions)
        for key in ['reason','missing','predicate_checks','issue_scope']:
            if c.get(key)!=new.get(key):
                corrections.append(dict(entity_id=c.get('task_id')or c.get('technical_case_id'),record_id=c['relation_id'],
                    field=key,previous_value=c.get(key),new_value=new.get(key),scope='CONDITIONAL_CLASSIFICATION_CORRECTION',
                    reason='去除未证阶段或控制条件断言，独立核对语义与构造。',source_revision=SOURCE_COMMIT))
        classified.append(new)
    data['conditions']=classified
    for r in rs:
        r['proposed_api42_ids']=[c['condition_id']for c in data['conditions']if c.get('task_id')==r['task_id']and c['system']=='API42']
        r['proposed_v4_scenario_ids']=[c['condition_id']for c in data['conditions']if c.get('task_id')==r['task_id']and c['system']=='V4']
    data['driving_quantities']=driving;data['case_reviews']=reviews;data['corrections']=corrections
    # Old family grouping is historical evidence, not a revised grouping decision.
    data['cross_review']['historical_candidate_families']=data['cross_review'].pop('candidate_families')
    data['cross_review']['candidate_families']=[]
    data['cross_review']['revision_note']='原7组仅保存在历史字段；六条未核关系不据四问确定新增、扩展或优先归卡。'
    return data


def summary(data,folder):
    base=core.summarize(data['results'],data['failures'],data['conditions'],data['comparisons'],data['technical_cases'],
        core.read(folder/'sources/baseline_30.json'),core.read(folder/'search_index.json')['searches'],
        core.read(folder/'sources/prior_condition_relations.json')['relations'])
    base['schema_version']='RC128-RELATION-REVIEW-2'
    base['candidate_review_families']=len(data['cross_review']['candidate_families'])
    base['candidate_count_scope']='本版六条均为待核关系／归卡讨论；历史8条建议／7组方向仅在history/r1和历史分组字段保留，不构成本轮新增决策。'
    base['search_count_scope']='128条／141轮均为R1历史检索；R2新增搜索0轮。'
    base['technical_case_count_scope']='22条均复用R1；prior19与new3是R1相对更早版本的计数，本版新增技术案例0条。'
    base['revision']=dict(policy_version=VERSION,unique_records=128,quantity_reviewed_cases=list(SIX),
        quantity_reviewed_case_count=6,driving_quantity_count=len(data['driving_quantities']),
        questions_recorded_count=len(data['driving_quantities']),relation_confirmed_count=0,
        shared_template_only_cases=list(SHARED),shared_template_only_case_count=3,
        historical_only_case_count=119,remaining122_not_quantity_reviewed=True,
        technical_shared_corrections=['TC-FP8-VSCALE','TC-SFAG-EVENT-ID'],
        new_or_extension_decisions=0,formal_adoption=0,manual_accepts=0,device_runs=0,
        draft_action_counts_are_not_adjudications=True,
        semantic_statuses=dict(Counter(c['semantic_applicability']['status']for c in data['conditions'])),
        construction_statuses=dict(Counter(c['construction_feasibility']['status']for c in data['conditions'])))
    return base


JS_OVERLAY=r'''
const reviewById=new Map(D.case_reviews.map(x=>[x.task_id,x]));
const scopeLabel={DRIVING_QUANTITY_REVIEW_WITH_GAPS:'六条逐驱动量审查，仍有未知',SHARED_TEMPLATE_CORRECTION_ONLY:'仅共享模板纠正，未逐驱动量复审',HISTORICAL_ANALYSIS_REUSED:'沿用历史分析与模式建议，非本轮新决定'};
function answerCard(a){return '<p>'+esc(a.answer)+'</p>'+tags([a.status,a.basis])+'<p class="muted">未知原因：'+esc(a.unknown_reason)+'</p>'+a.evidence_ids.map(quote).join('')}
function fourColumns(r){return '<div class="scroll"><table><thead><tr><th>候选机理</th><th>实现载体</th><th>证据等级</th><th>与原30关系</th></tr></thead><tbody><tr><td>'+esc(r.candidate_mechanism.name)+'<p>'+esc(r.candidate_mechanism.known)+'</p><p class="danger">'+esc(r.candidate_mechanism.unknown)+'</p></td><td>'+esc(r.implementation_carrier.description)+'<p>载体不决定合并或新增。</p></td><td>'+r.evidence_level.claims.map(c=>'<p>'+esc(c.claim)+'</p>'+tags([c.basis])+'<p>'+esc(c.limitation)+'</p>'+c.evidence_ids.map(quote).join('')).join('')+'</td><td>'+r.original30_relation.similar_modes.map(m=>'<p><b>'+esc(m.mode_id)+'</b>：'+esc(m.original_definition)+'</p>').join('')+'<p>'+esc(r.original30_relation.common)+'</p><p>'+esc(r.original30_relation.boundary_discussion)+'</p><b>待审，不确认新增或扩展。</b></td></tr></tbody></table></div>'}
function quantitiesCard(id){return D.driving_quantities.filter(q=>q.task_id===id).map(q=>'<section class="line" id="'+esc(q.quantity_id)+'"><h4>'+esc(q.label)+'</h4>'+tags([q.quantity_id,q.name_kind])+'<p>'+esc(q.name_scope)+'</p><div class="grid"><div><b>Q1 对象</b>'+answerCard(q.Q1)+'<b>Q2 单位／编码／定义域</b>'+answerCard(q.Q2)+'</div><div><b>Q3 生命周期</b>'+[['creator','创建'],['initializer','初始化'],['writable_owners','可写主体'],['reset_responsibility','复位责任']].map(([k,n])=>'<details><summary>'+n+'</summary>'+answerCard(q.Q3[k])+'</details>').join('')+'<b>Q4 消费者</b>'+answerCard(q.Q4)+'</div></div><p>四问记录齐备，关系未证实；未执行复现。</p></section>').join('')}
const oldCaseCard=caseCard;caseCard=function(r){const rv=reviewById.get(r.task_id);let h=oldCaseCard(r),cut=h.indexOf('</h3>')+5;const panel='<div class="panel"><b>本轮审查范围：</b>'+esc(scopeLabel[r.review_scope])+' '+tags([r.review_scope])+(rv?fourColumns(rv)+'<details><summary>逐驱动量四问（含未知与责任）</summary>'+quantitiesCard(r.task_id)+'</details><p>定向补证：'+esc(rv.targeted_evidence_gap)+'</p>':'<p>沿用历史分析；共享模板纠正不代表逐驱动量复审。</p>')+'</div>';return h.slice(0,cut)+panel+h.slice(cut)};
const oldTechnicalCard=technicalCard;technicalCard=function(t,embeddedScope=''){const h=oldTechnicalCard(t,embeddedScope);if(!t.review_scope)return h;const cut=h.indexOf('</h3>')+5;return h.slice(0,cut)+'<p class="panel">共享模板纠正，未完成逐驱动量复审。'+tags([t.review_scope])+'</p>'+h.slice(cut)};
const oldConditionCard=conditionCard;conditionCard=function(c){return oldConditionCard(c)+'<details><summary>语义适用与构造能力独立记录</summary><b>semantic_applicability</b><pre>'+esc(fmt(c.semantic_applicability))+'</pre><b>construction_feasibility</b><pre>'+esc(fmt(c.construction_feasibility))+'</pre><b>各挂载类别独立核对</b><pre>'+esc(fmt(c.class_assessments))+'</pre></details>'};
const oldSelectRows=selectRows;selectRows=function(q='',a='',g='',m=''){const key=q.toLowerCase().trim();return oldSelectRows('',a,g,m).filter(r=>!key||JSON.stringify([r,D.failures.filter(f=>f.task_id===r.task_id),D.conditions.filter(c=>c.task_id===r.task_id),D.driving_quantities.filter(x=>x.task_id===r.task_id),reviewById.get(r.task_id)]).toLowerCase().includes(key))};
const oldRenderView=renderView;renderView=function(v,q=''){if(v==='driving'||v==='candidates')return '<div class="panel"><h2>六条待核关系分析＋暂定归卡讨论</h2><p>22个驱动量四问已记录；未知不等于失效，四问不替代复现，不产生新增／扩展或人工ACCEPT。</p></div>'+D.case_reviews.filter(r=>!q||JSON.stringify(r).toLowerCase().includes(q.toLowerCase())).map(r=>'<article class="card"><h3>'+esc(r.task_id)+'</h3>'+fourColumns(r)+(v==='driving'?quantitiesCard(r.task_id):'')+'</article>').join('');if(v==='corrections')return '<article class="card"><h2>逐项纠正记录</h2><p>历史值只作差异追溯，不作为新版结论。</p><pre>'+esc(fmt(D.corrections.filter(c=>!q||JSON.stringify(c).toLowerCase().includes(q.toLowerCase()))))+'</pre></article>';return oldRenderView(v,q)};
VIEWS.splice(2,0,['driving','六条逐驱动量四问'],['corrections','纠正记录']);VIEWS.find(x=>x[0]==='candidates')[1]='六条暂定归卡讨论';
'''


def render(folder,data):
    template=core.HTML
    template=template.replace('<title>128条核验 · 条件与失效关系</title>','<title>128条修订版 · 六条逐驱动量四问 · 2026-11-12</title>')
    template=template.replace('128条均执行定向检索；原21个GitCode PR本轮网页读取受阻。',
        '本版复用前轮128条检索和证据，未重新搜索。六条完成逐驱动量审查（含未知）；3条仅纠正共享模板，119条沿用历史。原21个GitCode PR全文仍未取得。')
    template=template.replace('本轮最强公开原文','复用的最强公开选段').replace('实际检索 ','历史检索 ')
    start=template.index("$('metrics').innerHTML=");end=template.index("for(const id of ['query'",start)
    template=template[:start]+JS_OVERLAY+"\n$('metrics').innerHTML=[['128','完整保留记录'],['6 / 22','深审记录 / 驱动量'],['3 / 119','模板纠正 / 历史沿用'],['0','关系证实 / 入库 / 设备执行']].map(([v,n])=>'<div class=\"metric\"><strong>'+v+'</strong>'+esc(n)+'</div>').join('');\n"+template[end:]
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    core.writable_output(folder)
    (folder/'report.html').write_text(template.replace('__PAYLOAD__',encoded),encoding='utf-8',newline='\n')


def make_manifest(folder):
    policy=core.read(folder/'review_policy.json')
    code={p:core.sha(core.REPO/p)for p in CODE}
    fp=hashlib.sha256(json.dumps(dict(code=code,policy=policy),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    core.write(folder/'manifest.json',dict(schema_version='RC128-BUNDLE-2',policy_fingerprint=fp,analysis_code_sha256=code,
        source_revision=SOURCE_COMMIT,payload_sha256={p:h for p,h in file_hashes(folder).items()if p not in EXCLUDED},
        original_state_modified=False,baseline_workflow_frozen=False,formal_adoption=False))
    return fp


def build_revision(folder, source):
    folder=core.writable_output(folder);source=source.resolve()
    if folder==source or source in folder.parents or folder in source.parents:
        raise ValueError('Source archive and output must be independent directories.')
    if core.read(source/'manifest.json')['schema_version']!='RC128-BUNDLE-1':
        raise ValueError('R2 requires the historical R1 source, not another overlay.')
    source_hashes=file_hashes(source)
    history_check=core._verify_v1(source)
    text=(source/'report.html').read_text(encoding='utf-8')
    data=json.loads(re.search(r'<script type="application/json" id="payload">(.*?)</script>',text,re.S).group(1))
    for rel in source_hashes:
        if rel in EXCLUDED or rel=='README.md':continue
        target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,target)
    for rel in ['manifest.json','validation.json','ui_validation.json','test_results.txt','summary.json','review_policy.json','cross_review.json']:
        target=folder/'history/r1'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,target)
    invariant_target=folder/'sources/reference/INVARIANTS.md'
    invariant_target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(INVARIANTS,invariant_target)
    source_info=dict(source_path=str(source),source_commit=SOURCE_COMMIT,policy_status=history_check['policy_status'],
        policy_fingerprint=history_check['policy_fingerprint'],all_file_sha256=source_hashes,
        zip_sha256=core.sha(source.with_suffix('.zip')),read_only_verification=history_check,
        invariants_sha256=core.sha(invariant_target),invariants_role='分析纪律参考，不修改定义，不替代原30条基准。')
    core.write(folder/'source_revision.json',source_info)
    definitions={(d['system'],d['condition_id']):d for d in data['definitions']}
    modes={m['mode_id']:m for m in data['baseline']}
    data=reconcile(data,modes,definitions);data['summary']=summary(data,folder)
    for name,key in [('results','results'),('failure_relations','failures'),('condition_relations','conditions'),('mode_comparison','comparisons'),('driving_quantities','driving_quantities')]:
        core.jsonl(folder/(name+'.jsonl'),data[key])
    core.write(folder/'case_reviews.json',dict(reviews=data['case_reviews'],status='PENDING_RELATION_REVIEW'))
    core.write(folder/'corrections.json',dict(corrections=data['corrections'],source_revision=SOURCE_COMMIT))
    core.write(folder/'technical_cases.json',dict(cases=data['technical_cases'],prior_case_count=19,new_independent_case_count=3,weekly_event_confirmed_count=0))
    core.write(folder/'cross_review.json',data['cross_review']);core.write(folder/'summary.json',data['summary'])
    gaps=core.read(source/'unresolved_gaps.json')
    gaps['gaps']=[g for g in gaps['gaps']if not(g.get('task_id')in SIX and g.get('kind')=='CLAIM_SPECIFIC_EVIDENCE_GAP')]
    gaps['gaps'] += [dict(task_id=r['task_id'],kind='R2_RELATION_REVIEW_GAP',detail=g)
                    for r in data['results']if r['task_id']in SIX for g in r['unresolved_gaps']]
    core.write(folder/'unresolved_gaps.json',gaps)
    policy=dict(version=VERSION,input_budget_chars=160000,no_auto_accept=True,original_state_modified=False,
        device_runs=0,no_new_or_extension_decision_from_questions=True,semantic_and_construction_independent=True,
        original42_and_v4_independent=True,full_request_no_truncation=True,source_archive_read_only=True)
    core.write(folder/'review_policy.json',policy)
    context={r['task_id']:dict(review=r,quantities=[q for q in data['driving_quantities']if q['task_id']==r['task_id']])for r in data['case_reviews']}
    budgets=core.input_budget_receipts(core.rows(folder/'sources/original/handoff.jsonl'),data['baseline'],data['definitions'],folder,context)
    core.write(folder/'input_budget_receipts.json',budgets)
    render(folder,data)
    (folder/'README.md').write_text(README,encoding='utf-8',newline='\n')
    core.write(folder/'evidence_sha256_manifest.json',dict(reused_from=SOURCE_COMMIT,
        files={p:core.sha(folder/p)for p in source_hashes if p.startswith(('sources/','evidence/'))},
        new_searches=0,full_prs_newly_reviewed=0,summary_is_not_full_text=True))
    make_manifest(folder)
    result=verify_revision(folder)
    if source_hashes!=file_hashes(source):raise ValueError('Historical archive changed during build.')
    core.write(folder/'validation.json',result)
    return result


README='''# 128条修订版 · 2026-11-12

主要入口为 report.html；全部来源及最强可用选段随目录保留，可离线查看。

六条 RC-009、010、023、029、062、105 是待核关系分析＋暂定归卡讨论。
22个驱动量逐项记录Q1对象、Q2单位／编码／定义域、Q3创建／初始化／可写主体／复位、Q4消费者。
填写完整不代表关系证实，也不替代复现。六条新增与扩展决定全部待审。
RC-051、060、111以及TC-FP8-VSCALE、TC-SFAG-EVENT-ID仅纠正模板携带的断言；其余119条沿用历史。
原128输入字节、原30／42／V4定义、历史证据保持不变；未修改state或人工历史。

RC-029只有历史代码选段能定位参数替换；未核完整变量定义和调用合同。
其它五条根因目前主要来自转交声明／摘要，不能写作已独立证实。明确PR提示保留作定向补证，不重搜128条。
RC-062 N3／zeros为条件化来源层分类；不证明缺陷、恢复遗漏或新增模式。
semantic_applicability与construction_feasibility独立；Requires／Skip和每个挂载类别逐项保留。
旧模式建议的计数只表示历史草案，不能当成本版新增／扩展决策。

## 构建与核验

```powershell
python scripts/rc128_review.py build reports/archive/rc128-evidence-review-20261112-r2 --source-bundle reports/archive/rc128-evidence-review-20261111
python scripts/rc128_review.py verify reports/archive/rc128-evidence-review-20261112-r2
python scripts/rc128_review.py verify reports/archive/rc128-evidence-review-20261111
node scripts/verify_rc128_revision_ui.cjs reports/archive/rc128-evidence-review-20261112-r2
```

build只允许独立输出目录，禁止写入旧归档。verify只读；旧包按原manifest核验并明确历史策略身份，不改旧validation。
history/r1保留原统计、策略及验证日志；source_revision.json记录源目录全部文件SHA和旧ZIP SHA。
整请求包含指令、原记录、原30定义、完整42／V4原文、分类定义以及本轮四问数据，预算160000字符。
超限标记BLOCKED／INPUT_TOO_LARGE，不截断；预算检查不证明执行会话未截断。本轮未调用生产模型桥接。

## 验证范围

test_results.txt、validation.json、ui_validation.json记录实际解释器／依赖和检查结果。
UI测试为离线Node VM逻辑检查，不冒充真实浏览器或设备执行。
本包无人工ACCEPT、Baseline冻结、正式入库或NPU／GPU测试。
'''


def validate_quantities(qs):
    expected={k:len(quantities(k,[]))for k in SIX}
    if Counter(q['task_id']for q in qs)!=Counter(expected):return False
    if len({q['quantity_id']for q in qs})!=22:return False
    for q in qs:
        answers=[q['Q1'],q['Q2'],q['Q4']]+[q['Q3'][k]for k in ['creator','initializer','writable_owners','reset_responsibility']]
        if not all(a.get('answer')and a.get('status')and a.get('basis')and a.get('unknown_reason')and not a['confirmed']for a in answers):return False
        if q['relation_confirmed']or q['unit_error_confirmed']or q['manual_accept_created']:return False
    return True


def verify_revision(folder,git_index=False,historical_policy=False):
    folder=Path(folder);checks=[]
    def check(name,test):
        try:
            if test() is False:raise ValueError(name)
            checks.append(dict(name=name,status='PASS'))
        except Exception as exc:checks.append(dict(name=name,status='FAIL',error=str(exc)))
    manifest=core.read(folder/'manifest.json');info=core.read(folder/'source_revision.json')
    rs=core.rows(folder/'results.jsonl');fs=core.rows(folder/'failure_relations.jsonl');cs=core.rows(folder/'condition_relations.jsonl');ms=core.rows(folder/'mode_comparison.jsonl')
    qs=core.rows(folder/'driving_quantities.jsonl');reviews=core.read(folder/'case_reviews.json')['reviews']
    data=json.loads(re.search(r'<script type="application/json" id="payload">(.*?)</script>',(folder/'report.html').read_text(encoding='utf-8'),re.S).group(1))
    refs={q['evidence_id']for q in data['quotes']}|{q['excerpt_id']for q in data['current_excerpts']}
    check('128_unique_contiguous_original_ids',lambda:[r['task_id']for r in rs]==[f'RC-{n:03}'for n in range(1,129)])
    check('original_input_values_and_bytes_preserved',lambda:[r['original_input']for r in rs]==core.rows(folder/'sources/original/handoff.jsonl')and
          core.sha(folder/'sources/original/handoff.jsonl')==info['all_file_sha256']['sources/original/handoff.jsonl'])
    check('all_frozen_input_bytes_unchanged',lambda:all(core.sha(folder/x['file'])==x['sha256']for x in core.read(folder/'input_manifest.json')['files']))
    check('historical_snapshot_still_exact_if_present',lambda:not Path(info['source_path']).exists()or file_hashes(Path(info['source_path']))==info['all_file_sha256'])
    check('historical_zip_unchanged_if_present',lambda:not Path(info['source_path']).with_suffix('.zip').exists()or core.sha(Path(info['source_path']).with_suffix('.zip'))==info['zip_sha256'])
    check('legacy_policy_label_preserved',lambda:info['policy_status']=='HISTORICAL_POLICY_NOT_CURRENT_REVIEW'and info['read_only_verification']['read_only'])
    check('22_driver_four_questions_and_q3_responsibilities',lambda:validate_quantities(qs))
    check('six_reviews_not_128_new_reviews',lambda:{r['task_id']for r in reviews}==set(SIX)and Counter(r['review_scope']for r in rs)==dict(DRIVING_QUANTITY_REVIEW_WITH_GAPS=6,SHARED_TEMPLATE_CORRECTION_ONLY=3,HISTORICAL_ANALYSIS_REUSED=119))
    check('six_mode_decisions_pending',lambda:all(m['action']=='PENDING'and m['adjudication_status']=='PENDING'for m in ms if m.get('task_id')in SIX))
    check('no_confirmation_accept_adoption_or_device',lambda:all(not any(r[k]for k in ['weekly_event_confirmed','manual_accept_created','hardware_validated','formal_adoption'])for r in rs)and all(not q['relation_confirmed']for q in qs)and all(not r['new_or_extension_confirmed']for r in reviews))
    check('rc062_expected_no_register_or_constructor',lambda:all(not any(w in f['expected_relation']for w in ['寄存器','构造步骤','取消构造'])for f in fs if f.get('task_id')=='RC-062'))
    derived=[f for f in fs if (f.get('task_id')or f.get('technical_case_id'))in ['RC-029','TC-FP8-VSCALE']]
    check('rc029_no_unsupported_stage_conclusions',lambda:all(not any(w in json.dumps(f,ensure_ascii=False)for w in ['前块','当前块','前一块','前位置','前/当前','前一阶段'])for f in derived))
    check('unexecuted_mlp_not_inferred_uninitialized',lambda:'未执行MLP不自动证明未初始化'in next(r for r in reviews if r['task_id']=='RC-023')['candidate_mechanism']['unknown'])
    check('no_init_keyword_auto_a05',lambda:not any('A05'in json.dumps(r,ensure_ascii=False)and r['original30_relation']['status']!='PENDING'for r in reviews))
    check('semantic_and_construction_axes_all_present',lambda:all(c['semantic_applicability']['unknown_reason']and c['construction_feasibility']['unknown_reason']for c in cs))
    check('zeros_source_classification_not_defect_confirmation',lambda:any(c.get('task_id')=='RC-062'and c['condition_id']=='zeros'and c['semantic_applicability']['status']=='CONDITIONAL_SOURCE_CLASSIFICATION'and not c['defect_confirmed']and not c['counts_as_verified_coverage']for c in cs))
    check('scale_structure_requires_shape_axis_evidence',lambda:all(c['semantic_applicability']['status']=='UNKNOWN'for c in cs if c.get('task_id')=='RC-029'and c['condition_id']=='scale_structure'))
    check('api42_v4_independent_original_definition_bytes',lambda:all(core.sha(folder/p)==info['all_file_sha256'][p]for p in ['condition_definitions.json','baseline_30_index.json','sources/original/api42_trigger_library_original.md','sources/original/precision_trigger_knowledge_v4.md']))
    check('mounts_checked_without_label_transfer',lambda:all({x['class_id']for x in c['class_assessments']}==set(c['class_ids'])and all('requires'in x and 'skip_if'in x for x in c['class_assessments'])for c in cs))
    check('exact_original_quotes_resolve',lambda:anchors_valid(folder,data['quotes']))
    check('all_current_quote_ranges_exact',lambda:all((folder/q['file']).read_bytes().decode('utf-8')[q['char_start']:q['char_end']]==q['quote']and core.sha(folder/q['file'])==q['sha256']for q in data['current_excerpts']))
    check('all_driving_and_claim_references_resolve',lambda:all(set(a['evidence_ids'])<=refs for q in qs for a in [q['Q1'],q['Q2'],q['Q4'],*q['Q3'].values()])and all(set(c['evidence_ids'])<=refs for r in reviews for c in r['evidence_level']['claims']))
    check('failure_and_condition_evidence_resolve',lambda:all(set(f['evidence_ids'])<=refs for f in fs)and all(set(c['source_evidence_ids'])<=refs for c in cs))
    check('unique_relation_comparison_ids',lambda:all(len(x)==len({i[k]for i in x})for x,k in [(fs,'relation_id'),(ms,'comparison_id'),(cs,'relation_id')]))
    resources=core.read(folder/'evidence/resource_index.json')['resources']
    check('21_resources_dedup_without_reference_loss',lambda:len(resources)==21 and len({r['url']for r in resources})==21 and sum(len(r['task_ids'])for r in resources)==sum(len(r['original_input']['public_code_clues'])for r in rs))
    check('subproblem_scopes_preserved',lambda:len(rs[103]['failure_relation_ids'])==4 and all(len(c['issue_scope_map'])==1 for c in cs if c.get('task_id')=='RC-104'))
    check('unknown_not_different_event',lambda:all(a['event_relation']=='UNDETERMINED'for r in rs for a in r['source_associations']))
    check('no_verified_coverage_from_classification',lambda:all(not c['counts_as_verified_coverage']and not c['historical_event_confirmed']and not c['hardware_validated']for c in cs))
    check('html_json_all_arrays_equal',lambda:all(data[k]==v for k,v in [('results',rs),('failures',fs),('conditions',cs),('comparisons',ms),('driving_quantities',qs),('case_reviews',reviews)]))
    check('summary_recomputed_and_embedded_equal',lambda:data['summary']==core.read(folder/'summary.json')==summary(data,folder))
    budgets=core.read(folder/'input_budget_receipts.json')
    context={r['task_id']:dict(review=r,quantities=[q for q in qs if q['task_id']==r['task_id']])for r in reviews}
    check('entire_request_budget_reproduces',lambda:budgets==core.input_budget_receipts(core.rows(folder/'sources/original/handoff.jsonl'),data['baseline'],data['definitions'],folder,context))
    check('160000_budget_no_truncation_blocked_when_oversize',lambda:len(budgets['receipts'])==128 and not budgets['automatic_truncation']and all(b['budget_chars']==160000 and b['status']==('BLOCKED'if b['serialized_input_chars']>160000 else'WITHIN_BUDGET')and b['reason']==('INPUT_TOO_LARGE'if b['serialized_input_chars']>160000 else None)for b in budgets['receipts']))
    check('all_reused_evidence_bytes_identical',lambda:all(core.sha(folder/p)==h for p,h in core.read(folder/'evidence_sha256_manifest.json')['files'].items()))
    check('all_payload_sha256_match',lambda:all(core.sha(folder/p)==h for p,h in manifest['payload_sha256'].items()))
    check('manifest_covers_complete_payload',lambda:set(file_hashes(folder))-EXCLUDED==set(manifest['payload_sha256']))
    code={p:core.sha(core.REPO/p)for p in CODE}
    fingerprint=hashlib.sha256(json.dumps(dict(code=code,policy=core.read(folder/'review_policy.json')),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if historical_policy:
        old_fp=hashlib.sha256(json.dumps(dict(code=manifest['analysis_code_sha256'],policy=core.read(folder/'review_policy.json')),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        check('historical_policy_fingerprint_self_consistent_not_current',lambda:old_fp==manifest['policy_fingerprint']and old_fp!=info['policy_fingerprint'])
    else:
        check('current_policy_code_budget_fingerprint',lambda:code==manifest['analysis_code_sha256']and fingerprint==manifest['policy_fingerprint']and fingerprint!=info['policy_fingerprint'])
    if git_index:
        def staged():
            for p,h in manifest['payload_sha256'].items():
                result=subprocess.run(['git','show',':'+(folder/p).relative_to(core.REPO).as_posix()],cwd=core.REPO,capture_output=True)
                if result.returncode or hashlib.sha256(result.stdout).hexdigest()!=h:return False
            return True
        check('git_index_exact_payload_bytes',staged)
    import importlib.metadata
    dependencies={}
    for name in ['pydantic','openpyxl','PyYAML']:
        try:dependencies[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:dependencies[name]='NOT_INSTALLED'
    result=dict(status='FAIL'if any(c['status']=='FAIL'for c in checks)else'PASS',policy_version=VERSION,
        policy_fingerprint=manifest['policy_fingerprint'],checks=checks,check_count=len(checks),
        policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW'if historical_policy else'CURRENT_POLICY',
        records=128,driving_quantities=len(qs),read_only=True,python=sys.version,executable=sys.executable,
        dependencies=dependencies,device_runs=0,scope='OFFLINE_DATA_AND_REPORT_NOT_REPRODUCTION_OR_FULL_SOURCE_CONFIRMATION')
    if result['status']=='FAIL':raise ValueError(json.dumps(result,ensure_ascii=False))
    return result


def anchors_valid(folder,anchors):
    originals=core.rows(folder/'sources/original/handoff.jsonl');cache={}
    for q in anchors:
        if q['jsonl_line']:
            obj=originals[q['jsonl_line']-1]
            if obj['task_id']!=q['task_id']:return False
        else:
            if q['file']not in cache:cache[q['file']]=core.read(folder/q['file'])
            obj=cache[q['file']]
        value=core.pointer(obj,q['json_pointer'])
        actual=json.dumps(value,ensure_ascii=False,separators=(',',':'))if q['quote_is_serialized_json_value']else value
        if actual!=q['quote']:return False
    return True


def package(folder):
    """Archive complete validated directory without touching the historical ZIP."""
    folder=core.writable_output(folder);verify_revision(folder)
    target=folder.with_suffix('.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,folder.name+'/'+p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target)as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for p in folder.rglob('*'):
            if p.is_file()and hashlib.sha256(z.read(folder.name+'/'+p.relative_to(folder).as_posix())).hexdigest()!=core.sha(p):
                raise ValueError('ZIP member differs: '+str(p))
    return dict(file=str(target),bytes=target.stat().st_size,sha256=core.sha(target))
