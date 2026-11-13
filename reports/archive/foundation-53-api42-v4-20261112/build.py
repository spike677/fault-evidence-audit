"""Reproduce the knowledge-inventory report; no source-library edits or execution.

python build.py --prepare   # assemble captured, explicitly versioned inputs
python build.py             # render from this self-contained bundle
python build.py --verify    # read-only content/definition/quote/hash checks
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORKSPACE = REPO.parent
WORK = WORKSPACE / 'work/foundation_inventory_20261112'
OLD = WORKSPACE / 'work/ascend_pattern_comparison_20261111/ascend-op-fault-patterns'
NEW = WORK / 'upstream-current'
R4 = REPO / 'reports/rc128-mechanism-design-20261112-r4'
ORIGINAL_COMMIT = '1652e0fc3f8aeb617eeb889e518e2bc9cc8494e8'
REMOTE_COMMIT = '6c47a3a9af9159129d1678b05b9382f749537f0c'
VERSION = 'FOUNDATION-INVENTORY-20261112-V1'

TARGET = {
 'decision':'USER_CONFIRMED',
 'primary_goal':'维护可泛化的CANN算子精度失效机理库；模型、推理引擎、AI框架和硬件层先做归因分流。',
 'precision_meaning':'数值偏差、错误值、异常NaN/Inf、错误布局/绑定/状态/同步引出的数值错误等；必须结合目标接口合同与数值影响证据，不把一切不一致当缺陷。',
 'primary_entry':['有依据定位到CANN算子接口、host/tiling、kernel或直接相关的图分派/属性传递链中的失效关系。',
   '可参数化为对象角色、必要前提、核心约定、破坏方式及影响链，能列出相似模式的排除边界。',
   '精度影响和因果支持分别分级，摘要可以支持候选，未读代码和未执行设备仍保持未知。'],
 'routing':[
  {'layer':'用户模型/模型配置','meaning':'模型公式、权重、配置、采样或训练过程本身的错误。','53_scope':'可能作为症状背景、输入或数值参考出现；该库不是完整用户模型故障目录。','our_action':'保留故障和证据，单独归因；不能因模型最终乱码就认定算子缺陷。'},
  {'layer':'应用/推理引擎','meaning':'调度、请求批处理、KV管理、sleep/wakeup等实现链。','53_scope':'部分状态、内存、依赖关系可迁移作审查线索，非全套引擎故障覆盖。','our_action':'查具体破坏位置；引擎状态错误与算子正确消费错误输入分开，泛化关系可作旁证。'},
  {'layer':'AI框架/适配','meaning':'框架算子适配、参数语义、注册、dtype及元数据传递。','53_scope':'存在有限直接涉及，如F04的torch_npu清单/注册，A09多框架语义比较；不能说完全没有框架层，也不能说系统覆盖框架。','our_action':'明确责任边界和参考语义，不把提到TF/PTA或GPU就当框架自身故障。'},
  {'layer':'CANN算子及直接相关链','meaning':'接口合同、推导/tiling、计算/搬运、回写、图分派及依赖关系。','53_scope':'主体覆盖；A组22条归精度，其他组也可导致静默数值错误。','our_action':'精度机理主库来源；按实际核心关系筛选，不能只截取A组或将全部53直接导入。'},
  {'layer':'硬件/平台','meaning':'区分硬件规格/能力/代际约束与器件物理故障、设计/实现错误。','53_scope':'A01/A11/A17等涉及指令精度、能力与代际前提，不构成完整物理故障库。','our_action':'硬件限制下的软件选路/精度适配错误可以落到算子；硬件故障需独立规格、诊断或勘误证据。'},
  {'layer':'归因未定或跨层','meaning':'只有模型表现，或多个候选破坏点尚未消解。','53_scope':'可用于候选分诊和查证，不能由模式命中自动完成责任归因。','our_action':'按子问题保留未知/冲突，不强推主库；承载层与通用机理分别标注。'}],
 'library_fit':[
  {'capability':'算子精度及相关失效关系参考','assessment':'适合','reason':'具有机理卡、适用头、相邻边界、案例和审查清单；B/G等非A分组也可能支持精度机理。'},
  {'capability':'输入、路径与判据设计','assessment':'已有基础，可与42/V4互补','reason':'53自身已有L2设计、L3反误判和第二oracle；V4补统一构造索引，42补API角色及适用性，不是从零补测试。'},
  {'capability':'直接作为我们的主分类','assessment':'不宜整套直接采用','reason':'七组混合数值机理、接口契约、测试覆盖和工程风险；需投影、归一和证据分级，原30定义仍保留。'},
  {'capability':'自动根因与逐案例归类','assessment':'不能单靠现有库完成','reason':'源码指纹是候选工具；正则/文件配平/局部状态机不能替代跨语句和跨函数的对象—消费者追踪及因果验证。'},
  {'capability':'模型至硬件的全栈故障分类','assessment':'不属于完整覆盖范围','reason':'若干跨层案例不等于模型、引擎、框架、CANN及物理硬件体系均系统覆盖。'},
  {'capability':'精度缺陷已证实/设备覆盖','assessment':'必须逐接口、子问题与路径另验收','reason':'53有定义及来源声明，不是53个本轮独立确认或上板结果。'}],
 'next_logic':'故障记录→归因层及性质分流→具体五段链→抽象核心关系与破坏方式→对照原30/53候选→独立42/V4触发与验证。主库优先机理，辅助保留契约/测试/工程条目；不自动入库。'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')


FOUNDATION = {
 'purpose': '在真实资料和代码范围内，用对象、表示、生命周期及消费者解释失效关系，并连接条件构造、机理模式和验证判据。',
 'terminology_notes': [
  '四问中的消费者是使用某个量的代码/阶段/指令；53索引顶层consumers是消费知识库的工具，两者不是同一对象。',
  '53适用头的trigger常是源码正则/定位哨兵；42/V4的触发条件是输入或控制构造，不能把正则命中当作实际输入触发。',
  '53的L1/L2/L3分别是机理、检测判据、判据自身失效；不是芯片架构层级，也不等同V4三级构造目录。'],
 'distinctions': [
  {'name':'对象', 'meaning':'这个量属于谁、担当什么语义角色；不是只记录变量名或函数名。',
   'examples':'输入/输出/中间tensor；scale/indices/shape元数据；A/B/UB/workspace；控制字段；事件和结果状态。',
   'question':'本处实际取值是否来自消费者要求的那个对象？'},
  {'name':'时点', 'meaning':'观察、修改或消费发生在生命周期的哪一边界；不只是墙上时钟时间。',
   'examples':'创建→初始化→写入→发布→读取→复用→复位→释放；当前/前次调用；生产者/消费者。',
   'question':'当前消费者读取前，所需值是否已经建立且仍有效？谁有权写入和负责复位？'},
  {'name':'消费者', 'meaning':'最后使用该量的函数、分支、阶段或指令及其合同；不是笼统的下游模型。',
   'examples':'接口校验、InferShape、容量估算、地址算式、kernel分派、DataCopy/MM指令、后续算子。',
   'question':'这里要求逻辑形状还是物理对齐、元素还是字节、原激活dtype还是量化载荷dtype？'},
  {'name':'单位与表示域', 'meaning':'对象—时点—消费者只是定位简写，不能丢掉INVARIANTS的Q2。',
   'examples':'元素/字节/block/repeat；逻辑/物理形状和坐标；存储/计算/累加dtype；整数位宽；标志编码。',
   'question':'是否需要转换，转换在什么位置完成？非计数量说明编码/定义域；合法转换不算缺陷。'}],
 'five_stage_chain': [
  {'stage':1,'name':'输入及执行前提','required':'调用实参及合同预期；合法计算/明确应拒绝/未定义分别记录；实现情境另列。','not_proof':'选择了某42/V4类别不证明该输入已构造或触发故障。'},
  {'stage':2,'name':'派生量或状态','required':'驱动量的对象、计算/转换、单位表示、创建初始化写入复位责任及作用范围。','not_proof':'没有源码名时写语义角色；缺公式时不编造阈值。'},
  {'stage':3,'name':'实际路径及消费者','required':'分派谓词、调用边、读写位置或执行顺序；默认路径也可记录。','not_proof':'源码有此分支不等于实际运行进入；参数名相似不证明同对象。'},
  {'stage':4,'name':'失效关系与影响链','required':'应有关系、实际破坏方式、位置、必要触发前提、替代解释及传播。','not_proof':'乱码/NaN/越界是结果，不能单独作为根因；四问答全不能替代复现。'},
  {'stage':5,'name':'参考与区分判据','required':'控制变量、独立参考、路径探针、机制断言、数值/功能结果和观测能力缺口。','not_proof':'一次PASS只覆盖已记录接口/路径/条件；oracle本身要检查假阳与假阴。'}],
 'capability_layers': [
  {'status':'已具备结构/编排','content':'资料来源与快照、独立摘要、事件/机理分离、稀疏Scenario/LabelLink、测试DesignCard、整请求预算、策略失效、历史与HTML。','limit':'结构校验与引用存在性不等于语义正确或根因成立。'},
  {'status':'Agent分析工作','content':'分子问题、逐驱动量四问、条件Requires/Skip、核心关系、同机理边界与原30比较；需要明确证据或未知。','limit':'不能由关键词、共享URL、同算子或摘要自动完成这些判断。'},
  {'status':'当前数据缺口','content':'R4许多条件保持UNKNOWN；简化事实仍常为UNKNOWN角色，公开卡变量被统一写作CONTEXT。','limit':'不能把现有卡片数量说成逐参数/逐消费者的数据流追踪已经完成；五段链是本轮规范，尚非完整自动根因引擎。'},
  {'status':'执行另验收','content':'输入构造保留、目标路径实测、状态/流/多rank执行、注入后消费者读取及恢复。','limit':'知识库的构造说明或能力声明不证明已有执行器。'}],
 'maintenance': [
  '模式保存参数化因果规则；案例保存具体对象、版本、代码位置和证据。原30、外部53、原42、V4均保留各自身份。',
  '补充案例：原定义已解释核心关系及破坏方式；扩展详情：规则不变而具体路径/边界更明确；新增候选：存在原定义不能覆盖的有据独立破坏方式；证据不足保留待审。',
  '通用性验收：去掉实例名称仍可判别；第二实现可替换角色和参数而不用重写核心关系；能排除相似结果的不同机理；存在可落实的判据。',
  '同一场景多条件可联合触发；不把组合的证据复制为每个单条件充分致因。机理归组不合并历史事件。'],
 'injection_and_effect': [
  '语义位置用“对象角色×生命周期时点×消费者”描述；注入动作、范围、执行平面和实际selector另列。模式与注入能力不是一一对应。',
  '注入命中、数据/状态改变、消费者使用、目标关系失效、局部结果与模型任务影响分别观察；局部x→x′扰动不是y_ref→y_fault误差。',
  '当前TargetPlan主入口的可执行推荐是绑定资格，不是最敏感位置。辅助参数、持久状态和执行依赖需要相应可观测且可控的执行器。',
  '一次有证据B/F可展示对应影响；完整重复、热卸载恢复和跨故障泛化分别验收，不补造缺失历史证据。']}


COMPARISON = {
 'roles': [
  {'system':'分析基座','unit':'驱动量、具体关系及证据','question':'谁的量，在什么时点，以什么表示，被谁消费，哪项约定被破坏？','strength':'将具体代码、资料与测试观测连接起来。','limit':'不是完整自动数据流分析器，也不自带所有模式或设备执行器。'},
  {'system':'原53模式','unit':'机理/契约/性能资源/判据/工程风险条目','question':'检查哪些已知错误形态，怎么审查和验证？','strength':'L1机理、L2判据、L3判据失效、案例与治理形成闭环。','limit':'层级与范围混合，不能把全部53等同精度根因或53项已实测覆盖。'},
  {'system':'原42','unit':'API输入触发条件','question':'接口暴露什么参数角色，可构造哪些边界、值、布局和控制组合？','strength':'结构×语义角色×约束，输入族与schema门禁明确。','limit':'不直接提供代码消费者、根因或运行时状态/并发协议。'},
  {'system':'V4','unit':'31条件类、55构造情形及指导/执行规程','question':'怎样构造差异并观察路径与结果？','strength':'较细构造、输入驱动控制、执行方法和可区分数据设计。','limit':'不是55类机理，指导案例不等于已验证故障，执行协议不等于实现。'}],
 'themes': [
  {'topic':'数值表示与计算精度','patterns':'FP-A01/A02/A03/A12/A14/A15/A18等','api42':'数值族1.7及接口实际暴露的dtype/计算模式','v4':'N类、C1/C2及各自适用构造','bridge':'从合法数值/类型到实际中间精度、运算顺序及数值参考；相同误差不等于同机理。'},
  {'topic':'接口合法性与拒绝路径','patterns':'FP-B01/B04/B05/B11等','api42':'可选/形状/索引/窗口/控制条件，按各自定义','v4':'D/I/S/C相关类；合法计算与校验测试分开','bridge':'先确认接口级合同；拒绝合法输入、接受应拒绝输入和未定义行为分别判断。'},
  {'topic':'空输入与非空输出义务','patterns':'FP-B06，及相关写回/初始化条目','api42':'1.1.1等退化项','v4':'D3及E3','bridge':'主输入空不自动意味着所有输出空或可以跳过写回。'},
  {'topic':'寻址、容量、表示域','patterns':'FP-B07及A07/D类等，先分取错对象与算式错误','api42':'1.3依原硬索引门禁；1.2/1.4分别判断','v4':'I3/S2/S5/T类，需实际公式、单位、位宽','bridge':'原42不因普通shape大就自动满足1.3；V4I3可分析普通shape/stride进入内部算址。'},
  {'topic':'跨调用状态与可重入','patterns':'FP-A21，相关A05/A06需按具体破坏方式区分','api42':'当前调用可控输入可能有关；调用序列不在其输入构造范围','v4':'按输入类独立判断；E1/E2/E4提供实验方法','bridge':'固定目标调用，改变合法前序或干扰参与者；状态创建、写入及复位责任需查代码。'},
  {'topic':'确定性与同步依赖','patterns':'FP-A06/A20及FP-G类等','api42':'1.C.5仅当API实际暴露对应控制','v4':'合法显式控制与E1-E5；跨流补充单列','bridge':'内部不确定不自动等于deterministic参数问题；同步错误也可能稳定错算。'},
  {'topic':'输入驱动分派与信息传播','patterns':'FP-A07/A19/A22/FP-B08等','api42':'显式控制、形状边界等分别满足条目条件','v4':'C4允许可追踪的输入驱动分派；C2原文口径张力保留','bridge':'输入→派生谓词→所选实现→消费者；内部派生量不变成API实参。'},
  {'topic':'布局、视图与输出写回','patterns':'原53的布局/写回相关条目；远端新增FP-B16另列','api42':'1.4原schema/stride边界；out参数存在不代表执行器可构造输出stride','v4':'T1等语义方向与E3；需目标接口/输出合同','bridge':'算值正确与落位正确分开；合法逻辑视图、物理storage及实际写回分别核对。'},
  {'topic':'性能、资源和执行可靠性','patterns':'FP-C/D/G类','api42':'输入规模/分布可以选压力场景','v4':'S/C构造及执行方法可辅助定位','bridge':'性能回退、内存不足和挂死各自需要时间/容量/活性判据，不能全部用精度阈值。'},
  {'topic':'测试有效性与工程交付','patterns':'FP-E/F类及A19等覆盖风险','api42':'记录适用性和构造覆盖，不替代oracle审查','v4':'提供构造指导和能力/路径缺口，不代替交付流程','bridge':'测到正确路径且判据有效，才能解释PASS/FAIL；资料支持面是接口级问题。'},
  {'topic':'注入与效果评价','patterns':'提供需模拟的关系，但不是每条模式都有注入后端','api42':'选择暴露影响的调用实参','v4':'选择构造和执行规程','bridge':'位置→实际介入→消费者→关系→局部/模型效果；扰动代理与机理复现分别标注。'}],
 'non_conversion_rules': [
  '53个模式、42个条件、31个条件类、55个构造代码、64个挂载和195指导案例，分母不同，不能直接计算彼此覆盖百分比。',
  '本报告对比定义与任务分工，不生成53×42或53×55的全量匹配矩阵，也不自动转换标签。',
  '关联需要具体接口/子问题/情景以及适用谓词、原文或代码证据；列表中的主题对应只是检查方向。',
  '原53的子型、L2/L3与第二oracle是自身结构，不能与V4构造或42输入ID混成一套编号。',
  '无类别匹配不证明没有缺陷；有类别匹配不证明存在缺陷、属于同事件、正式入库或设备覆盖。']}


def prepare():
    for root, expected in [(OLD, ORIGINAL_COMMIT), (NEW, REMOTE_COMMIT)]:
        actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip()
        if actual != expected:
            raise ValueError('Source HEAD does not match the named frozen commit: '+str(root))
        subprocess.run(['git','-C',str(root),'diff','--exit-code','HEAD','--'],check=True,capture_output=True)
    for name in ['patterns53_review.json', 'api42_review.json', 'v4_review.json','layer_scope_review.json']:
        shutil.copyfile(WORK / name, HERE / name)
    # Preserve tracked public knowledge sources, never the source clone's .git.
    for root, name in [(OLD, 'patterns53'), (NEW, 'upstream_current')]:
        files = subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split('\0')
        for f in filter(None, files):
            target = HERE / 'sources' / name / f
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / f, target)
    for name in ['api42_trigger_library_original.md','precision_trigger_knowledge_v4.md']:
        dest = HERE / 'sources' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(R4 / 'sources/original' / name, dest)
    shutil.copyfile(R4/'condition_definitions.json',HERE/'sources/reference_condition_definitions.json')
    write(HERE/'source_manifest.json',dict(frozen53_commit=ORIGINAL_COMMIT,remote_observed_commit=REMOTE_COMMIT,
        files={p.relative_to(HERE).as_posix():sha(p) for p in (HERE/'sources').rglob('*') if p.is_file()}))
    old, new = read(OLD/'fault_patterns_index.json'), read(NEW/'fault_patterns_index.json')
    oi, ni = {x['id']:x for x in old['patterns']}, {x['id']:x for x in new['patterns']}
    write(HERE/'upstream_delta.json', dict(frozen_commit=ORIGINAL_COMMIT, observed_remote_head=REMOTE_COMMIT,
        frozen_version=old['version'], remote_index_version=new['version'], frozen_pattern_count=len(oi), remote_pattern_count=len(ni),
        original53_records_identical=all(oi[k]==ni[k] for k in oi),
        original53_cards_byte_identical=all((OLD/oi[k]['file']).read_bytes()==(NEW/ni[k]['file']).read_bytes() for k in oi),
        added=[ni[k] for k in sorted(ni.keys()-oi.keys())],
        version_cautions=['远端index仍标6.63，README顶部仍声明53，实际index和AGENTS尾部已54；FP-B16卡又写v6.64建条。原文矛盾并列保留，不能靠版本字符串判断规模。',
            'FP-B16来源宣称的19 issue/25接口及根因尚未由本报告独立读取工单/实测复现，保持上游声明身份。',
            'memcheck无告警本身不能普遍证明无越界或无缺陷；新卡给出的强边界不能在别的接口上机械套用。'],
        review_boundary='主体仍完整审读原53；新增54仅作当前版本附录，不覆盖旧定义或自动入库。'))
    (HERE/'.gitattributes').write_text('* -text\n',encoding='ascii')


CSS = '''body{font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;color:#213044;background:#f3f6fa;margin:0}main{max-width:1260px;margin:auto;padding:25px}h1{font-size:29px}h2{font-size:24px}h3{font-size:19px}a{color:#135fab}nav,.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:15px 0}button,input,select{font:inherit;padding:8px;border:1px solid #bac8d7;border-radius:6px;background:white}button{cursor:pointer}button.active{background:#174d7c;color:white}.card,.panel{background:white;padding:20px;margin:16px 0;border-radius:10px;border:1px solid #d6e0eb}.notice{padding:12px;background:#fff3d7;border-left:4px solid #a96b00}.metric{display:inline-block;padding:12px 20px;margin:5px;background:#e6eef8;border-radius:8px}.metric strong{font-size:24px;display:block}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{padding:10px;border:1px solid #d6e0eb;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3f9;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6fa;padding:12px}summary{cursor:pointer;font-weight:600}.tag{display:inline-block;border:1px solid #c6d7e8;border-radius:4px;padding:1px 6px;margin:2px;font-size:13px}.muted{color:#52677f}li{margin:5px 0}.chain{display:flex;gap:8px;flex-wrap:wrap}.chain span{background:#edf3f9;padding:8px;border-radius:5px}.small{font-size:13px}@media(max-width:720px){main{padding:12px}table{table-layout:auto;font-size:13px}td,th{padding:6px}}'''


JS = r'''
const D=JSON.parse(document.getElementById('payload').textContent),$=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>typeof x==='string'?x:JSON.stringify(x,null,2);
const pretty=x=>{const raw='<pre>'+esc(fmt(x))+'</pre>';if(x===D.patterns53.overview)return table(x.groups,[['prefix','分组'],['name','范围'],['count','条数']])+list(x.coverage_summary)+'<h3>测试与证据纪律</h3>'+list(x.testing_and_evidence_discipline)+'<details><summary>完整规模、边界及审读元数据</summary>'+raw+'</details>';if(x===D.api42.overview)return '<p>'+esc(x.purpose)+'</p><p><b>适用规则：</b>'+esc(x.applicability_rule)+'</p><h3>9族计数</h3>'+pretty(x.family_counts)+'<h3>优势与范围限制</h3>'+list(x.strengths)+list(x.limits)+'<details><summary>完整范围与审读元数据</summary>'+raw+'</details>';if(x===D.v4.overview)return '<p>'+esc(x.role)+'</p><p>'+esc(x.hierarchy)+'</p><h3>原定义边界</h3>'+list(x.known_definition_boundaries)+'<details><summary>完整计数、状态与共享挂载</summary>'+raw+'</details>';return raw;};
const list=x=>'<ul>'+((Array.isArray(x)?x:[x])||[]).map(v=>'<li>'+esc(fmt(v))+'</li>').join('')+'</ul>';
const tags=x=>(x||[]).map(v=>'<span class="tag">'+esc(v)+'</span>').join('');
function safeHref(s){return typeof s==='string'&&!s.includes('..')&&!s.includes('\\')&&(/^(sources\/|https:\/\/)/.test(s))?s:null}
function link(s,t){const h=safeHref(s);return h?'<a href="'+esc(h)+'" target="_blank" rel="noopener noreferrer">'+esc(t||s)+'</a>':esc(t||s)}
function table(rows,cols){return '<table><thead><tr>'+cols.map(([k,n])=>'<th>'+esc(n)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(([k,n])=>'<td>'+esc(fmt(r[k]??''))+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function section(title,text){return '<section class="panel"><h2>'+esc(title)+'</h2>'+text+'</section>'}
function find(rows,q){return rows.filter(r=>!q||JSON.stringify(r).toLowerCase().includes(q.toLowerCase()))}
function source(r,defaultPath){const path=r.source_file?.startsWith('sources/')?r.source_file:defaultPath;return (r.layer_assessment?'<details><summary>故障承载、触发情境、症状与参考分层</summary><p><b>承载解释：</b>'+esc(r.layer_assessment.carrier_interpretation)+'</p><p><b>情境／参考：</b>'+esc(r.layer_assessment.context_reference_interpretation)+'</p><p><b>主目标关系：</b>'+esc(r.layer_assessment.precision_goal_role)+'</p>'+pretty(r.layer_assessment)+'</details>':'')+(r.source_profile?'<details><summary>L1适用、L2判据、子型及上游证据声明</summary><p>来源索引中的声明和方法，不代表本报告独立核验历史案例或运行设备。</p>'+pretty(r.source_profile)+'</details>':'')+'<details><summary>原始引文、位置及完整字段</summary><p>'+link(path,'打开随包原文')+'</p>'+pretty(r.source_quote||r.source_occurrences||'未单列引文')+pretty(r)+'</details>'}
function foundation(){return section('00 · 先确定分类目标','<p><b>'+esc(D.target.primary_goal)+'</b></p><p>'+esc(D.target.precision_meaning)+'</p>'+list(D.target.primary_entry)+'<h3>归因层、触发背景和故障表现分别看</h3>'+table(D.target.routing,[['layer','归因层'],['meaning','判断什么'],['53_scope','53条实际范围'],['our_action','我们的分流']])+'<p>'+esc(D.target.next_logic)+'</p>')+section('01 · 分析基座：定位、关系、证据', '<p>'+esc(D.foundation.purpose)+'</p>'+table(D.foundation.distinctions,[['name','分析维度'],['meaning','负责回答'],['examples','对象／阶段示例'],['question','判别问题']])+'<p class="notice">“对象—时点—消费者”用于定位。完整分析仍保留对象、单位与表示域、生命周期、消费者四问；它们是判定底座，不是第54种模式或新的输入类别。</p>')+
section('同名术语先分清',list(D.foundation.terminology_notes))+
section('五段解释链：具体案例的因果说明','<div class="chain">'+D.foundation.five_stage_chain.map(s=>'<span>'+s.stage+' '+esc(s.name)+'</span>').join(' → ')+'</div>'+table(D.foundation.five_stage_chain,[['name','环节'],['required','需回答'],['not_proof','不能据此推出']]))+
section('当前已经具备什么，尚需什么',table(D.foundation.capability_layers,[['status','状态'],['content','已有结构／工作'],['limit','边界']]))+
section('维护通用模式库',list(D.foundation.maintenance))+section('注入与效果评价的位置',list(D.foundation.injection_and_effect))}
function patterns(q){const rows=find(D.patterns53.patterns,q);return section('02 · 原53条模式：完整目录与逐条审读','<p>固定1652e0fc，v6.63。这里的“覆盖”指条目定义涉及的内容，不代表本轮接口/设备覆盖。模式名、分组及边界按原文保留。</p>'+pretty(D.patterns53.overview)+'<p>匹配 '+rows.length+' / 53</p>')+rows.map(r=>'<article class="card pattern"><h3>'+esc(r.id+' · '+r.name)+'</h3>'+tags([r.category,r.analysis_kind])+'<p><b>定义涉及：</b>'+esc(fmt(r.coverage))+'</p><p><b>关系重点：</b>'+esc(fmt(r.relation_focus))+'</p>'+table([r],[['object_focus','对象'],['time_focus','时点／生命周期'],['consumer_focus','消费者']])+'<p><b>排除边界：</b>'+esc(fmt(r.boundary))+'</p>'+source(r,'sources/patterns53/'+r.source_file)+'</article>').join('')}
function api42(q){const rows=find(D.api42.items42,q);return section('03 · 原42条：API输入触发条件','<p>原定义69f6cae4…；采用原42，不采用V5修订42。类别是输入构造方向，消费者列是审读方向，尚不是代码定位或因果证据。</p>'+pretty(D.api42.overview)+'<details><summary>完整9族前提与边界</summary>'+pretty(D.api42.families)+'</details><p>匹配 '+rows.length+' / 42</p>')+rows.map(r=>'<article class="card api42"><h3>'+esc(r.id+' · '+r.name)+'</h3>'+tags([r.family_id,...r.input_roles])+'<p><b>原定义：</b>'+esc(r.definition)+'</p><b>完整Requires（项＋族）</b>'+list(r.requires)+'<b>完整Skip if（项＋族）</b>'+list(r.skip_if)+(r.family_scope_constraint?'<p><b>族范围前提：</b>'+esc(fmt(r.family_scope_constraint))+'</p>':'')+'<p><b>构造重点：</b>'+esc(r.construction_focus)+'</p><p><b>潜在消费者方向：</b>'+esc(r.consumer_direction)+'</p><p><b>边界：</b>'+esc(r.boundary)+'</p><p>'+esc(r.legality_expectation)+'</p>'+source(r,'sources/api42_trigger_library_original.md')+'</article>').join('')}
function v4(q){const cs=find(D.v4.classes,q),ss=find(D.v4.constructions,q);return section('04 · V4：先区分条件类、构造、案例和执行方法','<p>6主题、31条件类、55唯一构造、64挂载、195指导案例、原文E1–E5；应用层跨流补充单列，不算原文第6方法。</p>'+pretty(D.v4.overview)+table(D.v4.themes,[['id','主题'],['name','名称'],['class_ids','条件类'],['guidance_count','指导案例数']]))+
section('31条件类：完整原定义及适用边界','<p>匹配 '+cs.length+' / 31</p>')+cs.map(r=>'<article class="card v4class"><h3>'+esc(r.id+' · '+r.name)+'</h3>'+tags(r.construction_ids)+'<p><b>原定义：</b>'+esc(r.definition)+'</p><p><b>检验目的：</b>'+esc(r.purpose)+'</p><b>原Requires</b>'+list(r.requires)+'<b>原Skip if</b>'+list(r.skip_if)+table([r],[['object_focus','对象'],['time_focus','时点'],['consumer_focus','消费者方向']])+'<p><b>边界：</b>'+esc(r.boundary)+'</p>'+source(r,'sources/precision_trigger_knowledge_v4.md')+'</article>').join('')+
section('55唯一构造：完整清点（共享挂载不重复计类）','<p>匹配 '+ss.length+' / 55</p>')+ss.map(r=>'<article class="card construction"><h3>'+esc(r.id+' · '+r.name)+'</h3>'+tags(r.class_ids)+'<p>'+esc(r.definition)+'</p><p><b>检查方向：</b>'+esc(r.inspection_focus)+'</p>'+source(r,'sources/precision_trigger_knowledge_v4.md')+'</article>').join('')+
section('E1–E5：执行方法',D.v4.execution_methods.map(r=>'<article class="card method"><h3>'+esc(r.name)+'</h3><p>'+esc(r.definition)+'</p><p><b>边界：</b>'+esc(r.boundary)+'</p>'+source(r,'sources/precision_trigger_knowledge_v4.md')+'</article>').join(''))+
section('补充跨流规程：来自应用要求',pretty(D.v4.supplementary_methods))+
section('195指导案例与10种组合：保留完整索引','<p>指导案例不计为独立历史故障、已证根因或设备执行。</p><details><summary>展开195指导案例索引</summary>'+pretty(D.v4.guidance_index)+'</details><details><summary>展开10种组合指导</summary>'+pretty(D.v4.combination_guides)+'</details>')}
function compare(){return section('05 · 完成独立梳理后再比较',table(D.comparison.roles,[['system','体系'],['unit','基本单位'],['question','回答的问题'],['strength','优势'],['limit','边界']]))+section('ascend-op-fault-patterns能否满足已确认目标？',table(D.target.library_fit,[['capability','目标能力'],['assessment','判断'],['reason','依据与限制']]))+section('具体主题的分工与连接（检查方向，不是自动匹配）',table(D.comparison.themes,[['topic','主题'],['patterns','53模式侧'],['api42','原42侧'],['v4','V4侧'],['bridge','需要补的证据连接']]))+section('比较口径',list(D.comparison.non_conversion_rules))}
function upstream(){return section('06 · 远端版本核对：现在实际54条','<p class="notice">本次只读访问远端发现新增FP-B16。主体53条基准未被覆盖；原53的索引记录和卡片字节与新HEAD均相同。</p>'+pretty(D.upstream)+'<p>'+link('sources/upstream_current/patterns/FP-B/FP-B16.md','查看新增FP-B16原卡')+'</p><p>新卡涉及出参stride回写，特别适合说明“值计算正确”和“写到正确位置”不是同一关系。与V4 T1/E3只能作为进一步核对方向；原42仍须满足实际schema/输出描述能力。上游实测宣称不是本报告独立复现。</p>')+section('来源、版本与交付边界',pretty(D.provenance))}
const VIEWS=[['foundation','01 分析基座'],['patterns','02 原53模式'],['api42','03 原42条件'],['v4','04 V4完整盘点'],['comparison','05 横向比较'],['upstream','06 远端增量与来源']];let view='foundation';
function render(v,q=''){return v==='foundation'?foundation():v==='patterns'?patterns(q):v==='api42'?api42(q):v==='v4'?v4(q):v==='comparison'?compare():upstream()}
function draw(){const q=$('query').value.trim();$('nav').innerHTML=VIEWS.map(([v,n])=>'<button data-view="'+v+'" class="'+(v===view?'active':'')+'">'+n+'</button>').join('');$('content').innerHTML=render(view,q);$('count').textContent=['patterns','api42','v4'].includes(view)?'关键词过滤当前目录；构造与类别分别计数。':'独立审读与比较；不表示实际故障/设备覆盖。'}
$('nav').addEventListener('click',e=>{const b=e.target.closest('button[data-view]');if(b){view=b.dataset.view;draw()}});$('query').addEventListener('input',draw);$('reset').addEventListener('click',()=>{$('query').value='';draw()});
$('metrics').innerHTML=[[53,'冻结模式'],[42,'API条件'],[31,'V4条件类'],[55,'唯一构造'],[195,'指导案例'],[54,'远端当前条目']].map(([n,t])=>'<span class="metric"><strong>'+n+'</strong>'+t+'</span>').join('');draw();
'''


def render():
    data = dict(version=VERSION, target=TARGET, foundation=FOUNDATION, comparison=COMPARISON,
        patterns53=read(HERE/'patterns53_review.json'), api42=read(HERE/'api42_review.json'),
        v4=read(HERE/'v4_review.json'), upstream=read(HERE/'upstream_delta.json'),
        layer_scope=read(HERE/'layer_scope_review.json'),
        provenance=dict(review_date='2026-11-12 Asia/Shanghai', frozen53_commit=ORIGINAL_COMMIT,
            observed_remote_head=REMOTE_COMMIT, original42_sha256=sha(HERE/'sources/api42_trigger_library_original.md'),
            v4_sha256=sha(HERE/'sources/precision_trigger_knowledge_v4.md'),
            original30_not_replaced=True, new_pattern_adoption=False, device_runs=0,
            review='知识定义与能力边界审读；来源里的案例、签名、实测和覆盖宣称没有在此重新验证。',
            source_license='53/54来源保留自带LICENSE，本报告不重新许可上游资料。'))
    canonical = {p['id']:p for p in read(HERE/'sources/patterns53/fault_patterns_index.json')['patterns']}
    layers = {p['id']:p for p in data['layer_scope']['patterns']}
    for p in data['patterns53']['patterns']:
        p['original_source_file'] = p['source_file']
        p['source_file'] = 'sources/patterns53/' + canonical[p['id']]['file']
        p['layer_assessment'] = layers[p['id']]['layer_assessment']
        c = canonical[p['id']]
        p['source_profile'] = dict(applicability=c.get('applicability'),detect=c.get('detect'),
            subtype_count=len(c.get('subtypes',[])),subtypes=c.get('subtypes',[]),
            signature_count=len(c.get('signatures',[])),evidence=c.get('evidence',[]),
            evidence_scope='UPSTREAM_DECLARATION_NOT_REAUDITED',related=c.get('related',[]))
    write(HERE/'review.json',data)
    wire=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>分析基座与53／42／V4完整梳理</title><style>__CSS__</style><main><h1>分析基座与53／42／V4：完整梳理后再比较</h1><p>先区分对象、时点、消费者和表示域，再分别读模式、输入条件与构造。所有“覆盖”均注明是定义范围、证据还是执行结果。</p><div id="metrics"></div><p class="notice">冻结53条为v6.63（1652e0fc）。2026-11-12远端实际新增到54条，但部分版本/总数文字尚未同步；新增FP-B16单列附录，主体不混版。</p><nav id="nav" aria-label="梳理章节"></nav><div class="toolbar"><input id="query" aria-label="过滤目录" placeholder="模式/条件ID、对象、关键词"><button id="reset">清除过滤</button></div><p id="count" class="muted"></p><div id="content"></div><footer>离线HTML · <a href="review.json">完整结构化梳理</a> · <a href="validation.json">核验记录</a> · <a href="manifest.json">字节清单</a> · 未运行设备或自动入库</footer></main><script type="application/json" id="payload">__DATA__</script><script>__JS__</script></html>'''
    (HERE/'index.html').write_text(html.replace('__CSS__',CSS).replace('__DATA__',wire).replace('__JS__',JS),encoding='utf8',newline='\n')
    payload={p.relative_to(HERE).as_posix():sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in {'manifest.json','validation.json','ui_validation.json','browser_validation.json'}}
    write(HERE/'manifest.json',dict(version=VERSION,payload_sha256=payload))


def verify():
    d=read(HERE/'review.json');checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    pp=d['patterns53']['patterns'];aa=d['api42']['items42'];cc=d['v4']['classes'];ss=d['v4']['constructions']
    canonical=read(HERE/'sources/patterns53/fault_patterns_index.json')['patterns'];ci={r['id']:r for r in canonical}
    check('53_unique_ids_original_names_categories',len(pp)==53 and len({r['id'] for r in pp})==53 and all(r['id'] in ci and r['name']==ci[r['id']]['name'] and r['category']==ci[r['id']]['category'] for r in pp))
    check('seven_original_groups_22_15_6_2_2_4_2',Counter(p['category'] for p in canonical)==Counter(dict(accuracy=22,compatibility=15,performance=6,resource=2,test_effectiveness=2,engineering=4,reliability=2)))
    check('42_unique_ids_nine_families',len(aa)==42 and len({r['id'] for r in aa})==42 and len(d['api42']['families'])==9)
    check('six_themes_31_classes_55_constructions',len(d['v4']['themes'])==6 and len(cc)==31 and len(ss)==55 and len({x['id'] for x in ss})==55)
    check('64_mounts_195_guides',sum(len(x['class_ids']) for x in ss)==64 and len(d['v4']['guidance_index'])==195)
    check('original_E1_E5_supplement_separate',set(x['method_id'] for x in d['v4']['execution_methods'])=={'E1','E2','E3','E4','E5'} and len(d['v4']['supplementary_methods'])==1)
    check('all_v4_mounts_bidirectional',all({c['id'] for c in cc if s['id'] in c['construction_ids']}==set(s['class_ids']) for s in ss))
    api=(HERE/'sources/api42_trigger_library_original.md').read_bytes().decode('utf8')
    v4=(HERE/'sources/precision_trigger_knowledge_v4.md').read_bytes().decode('utf8')
    check('original42_bytes',sha(HERE/'sources/api42_trigger_library_original.md')=='69f6cae46a021b5f242cd6bdf6600618bf63e2de7c87122c2187c90d08837a82')
    check('originalV4_bytes',sha(HERE/'sources/precision_trigger_knowledge_v4.md')=='e4aafbd2aaa6054e2f721b3d23f8808670ea97ca65bdf6082188a280c67f3193')
    check('every42_quote_exact',all(x['source_quote'] in api for x in aa))
    ref=read(HERE/'sources/reference_condition_definitions.json')['definitions']
    api_ref={x['condition_id']:x for x in ref if x['system']=='API42'}
    check('every42_full_original_definition_predicates',all(p['name']==api_ref[p['id']]['name'] and p['definition']==api_ref[p['id']]['definition'] and set(p['requires'])==set(api_ref[p['id']]['requires']) and set(p['skip_if'])==set(api_ref[p['id']]['skip_if']) for p in aa))
    class_ref={c['id']:c for x in ref if x['system']=='V4' for c in x['original_class_predicates']}
    const_ref={x['condition_id']:x for x in ref if x['system']=='V4'}
    check('every_v4_class_original_definition_predicates',all(p['name']==class_ref[p['id']]['name'] and p['definition']==class_ref[p['id']]['definition'] and p['requires']==class_ref[p['id']]['original_requires'] and p['skip_if']==class_ref[p['id']]['original_skip_if'] for p in cc))
    check('every55_original_definition_mounts',all(p['name']==const_ref[p['id']]['name'] and p['definition']==const_ref[p['id']]['definition'] and set(p['class_ids'])==set(const_ref[p['id']]['class_ids']) for p in ss))
    check('every_v4_class_construct_method_quote_exact',all(x['source_quote'] in v4 for x in cc+ss+d['v4']['execution_methods']))
    guides=d['v4']['guidance_index']
    source_ids=re.findall(r'^\d+\.\s+\*\*([A-Z]\d+-\d{2})\*\*',v4,re.M)
    check('all195_guides_exact_unique_and_correct_class',len(source_ids)==195 and set(source_ids)=={g['guide_id'] for g in guides} and len({g['guide_id'] for g in guides})==195 and all(g['source_quote'] in v4 and g['text'] in g['source_quote'] and g['title'] in g['source_quote'] and g['category_id']==g['guide_id'].split('-')[0] for g in guides))
    combos=d['v4']['combination_guides']
    check('ten_combination_quotes_exact',len(combos)==10 and len({c['source_quote'] for c in combos})==10 and all(c['source_quote'] in v4 for c in combos))
    def card(p):
        f=p['source_file'].replace('\\','/')
        if '/patterns/' in f:f='patterns/'+f.split('/patterns/',1)[1]
        if f.startswith('sources/patterns53/'):return HERE/f
        return HERE/'sources/patterns53'/f
    check('every53_quote_exact',all(p['source_quote'] in card(p).read_bytes().decode('utf8') for p in pp))
    layers=d['layer_scope']['patterns']
    check('all53_layer_annotations_and_quotes_scoped',len(layers)==53 and {p['id'] for p in layers}==set(ci) and all(p['name']==ci[p['id']]['name'] and all(e['quote'] in (HERE/'sources/patterns53'/ci[p['id']]['file']).read_bytes().decode('utf8') for e in p['layer_assessment']['source_evidence']) for p in layers))
    check('user_confirmed_goal_and_no_case_attribution_inherited',d['target']['decision']=='USER_CONFIRMED' and all(p['layer_assessment']['actual_incident_attribution']=='UNKNOWN_WITHOUT_CASE_SPECIFIC_CODE_AND_EXECUTION_EVIDENCE' for p in layers))
    check('all53_have_role_time_consumer_boundary',all(all(p.get(k) for k in ['coverage','relation_focus','object_focus','time_focus','consumer_focus','boundary','analysis_kind']) for p in pp))
    up=d['upstream'];check('current54_not_silently_53',up['remote_pattern_count']==54 and up['frozen_pattern_count']==53 and [r['id'] for r in up['added']]==['FP-B16'] and up['original53_records_identical'] and up['original53_cards_byte_identical'])
    check('archived_source_bytes_match_capture_manifest',all(sha(HERE/p)==h for p,h in read(HERE/'source_manifest.json')['files'].items()))
    wire=re.search(r'<script type="application/json" id="payload">(.*?)</script>',(HERE/'index.html').read_text(encoding='utf8'),re.S)[1]
    check('html_json_same_complete_content',json.loads(wire)==d)
    manifest=read(HERE/'manifest.json')
    files={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in {'manifest.json','validation.json','ui_validation.json','browser_validation.json'}}
    check('manifest_covers_complete_payload',set(manifest['payload_sha256'])==files)
    check('all_payload_bytes_match',all(sha(HERE/p)==h for p,h in manifest['payload_sha256'].items()))
    return dict(status='PASS' if all(c['passed'] for c in checks) else 'FAIL',checks=checks,check_count=len(checks),
        scope='DEFINITION_INVENTORY_AND_SOURCE_INTEGRITY_NOT_DEVICE_OR_HISTORICAL_FAULT_VALIDATION')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');ap.add_argument('--verify',action='store_true');ap.add_argument('--package',action='store_true');a=ap.parse_args()
    if a.prepare:prepare()
    if not a.verify:render()
    result=verify()
    if not a.verify:write(HERE/'validation.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='PASS':raise SystemExit(2)
    if a.package:
        zpath=HERE.with_suffix('.zip')
        with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for p in sorted(HERE.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(HERE).as_posix())
        print(json.dumps(dict(zip=str(zpath),sha256=sha(zpath)),ensure_ascii=False))


if __name__=='__main__':main()
