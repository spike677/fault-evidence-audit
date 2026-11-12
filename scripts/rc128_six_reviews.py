"""Curated R2 quantity questions. Semantic roles are not invented source variables.

All statements are bounded to the frozen handoff or selected historical code.
This module makes no event, new-mode, hardware or human acceptance decision.
"""
from copy import deepcopy

SIX = ('RC-009','RC-010','RC-023','RC-029','RC-062','RC-105')
SHARED = ('RC-051','RC-060','RC-111')
EXPECTED = {
 'RC-009':'缓存复用前应核对缓存适用描述与当前调用布局是否满足同一适用契约；具体字段、比较方式和失效规则待核。',
 'RC-010':'所选执行模板在首次消费前应建立该设备／上下文所需的ctrl状态；编码、位、设置与复位范围待核。',
 'RC-023':'索引变换应保留合同规定的有效性语义；消费者只使用合同允许且具有可用结果的专家槽位。默认填充及掩码规则待核。',
 'RC-029':'FlashUpdate相关调用的各scale参数应符合被消费载荷的对象、类型及数值语义契约；选段仅证实参数替换，完整契约待核。',
 'RC-062':'在目标调用、位置及配置可比且合法域明确的前提下，sin／cos内容应符合该调用的辅助张量契约；差异产生环节待核。',
 'RC-105':'通信buffer配置更新后，确定性请求应按实际配置契约传至有效设置与分派消费者；更新规则及字段编码待核。',
 'RC-051':'专家token计数应符合实际输入和所用计数API的契约；histc换bincount后的变化不能单独定位初始化或寄存器原因。',
 'RC-060':'FP8 FIA所消费scale应符合该调用及参考的数值、对象与布局契约；置1规避不能定位具体错绑对象。',
 'RC-111':'跨API比较应显式核对各自scale默认值及其数学语义；不同默认约定不直接等于载荷错绑。',
 'TC-SFAG-EVENT-ID':'事件分配结果向runInfo传播后应能被对应等待者正确读取；需核对event归属、ID编码和生命周期。',
 'TC-FP8-VSCALE':'被消费载荷与各scale实参应满足调用契约；选段参数替换之外的对象、数值和阶段语义待核。',
}

REVIEWS = {
 'RC-009': dict(title='缓存适用描述／复用资格关系待核',carrier='aclnn框架host-tiling-cache；具体实现责任待核',
  known='来源声明连续输入匹配到非连续缓存；未取得缓存匹配及修复代码。',
  unknown='缓存字段、stride单位、生成／失效主体及复用谓词未知；不预断key遗漏。',
  alternatives=['缓存描述遗漏','比较或规范化规则错误','失效／作用域错误','来源描述尚不完整'],
  modes=['M011','M027'],common='涉及条件判断／布局适用边界。',boundary='M011可讨论扩展，但需先定位复用资格如何被破坏；M027是特定私有格式的view限制。四问不决定归卡优先级。',
  hint='PR2094历史记录只改测试Golden，不能证明host-tiling-cache修复。'),
 'RC-010': dict(title='所需ctrl状态建立责任待核',carrier='极致头开销执行模板／TPipe；设备和上下文范围未知',
  known='周报及相关摘要声明取消TPipe后缺失构造函数设置ctrl的操作；版本替换后现象消失。',
  unknown='寄存器位、期望编码、实际值、责任主体和复位范围未知；初始化遗漏不等于同步或内存初始化。',
  alternatives=['模板未建立必要ctrl状态','其它模板副作用或配置差异'],modes=['M013','M007'],
  common='均涉及执行前提或适配行为。',boundary='M013是block_dim标量支持／常量折叠；M007是多核搬运同步。不能只因初始化一词挂到内存类或A05。',
  hint='摘要明确给出cann/opbase#279，保留为定向补读；本轮未读取该PR。'),
 'RC-023': dict(title='索引有效性与槽位消费资格待核',carrier='模型适配索引变换／token_unpermute输入契约',
  known='来源声明对sorted_indices取abs后所有专家被视为激活，并称未激活专家不执行MLP、输出含NaN。',
  unknown='负值是合法标记还是非法实参、默认填充值、掩码及结果可用性未知；未执行MLP不自动证明未初始化。',
  alternatives=['标记语义丢失','默认填充或掩码消费不符合契约','负值不在接口合法域'],modes=['M022','M020'],
  common='索引对象对应／边界结果传播具有相似性。',boundary='M022是Block Table与KV batch偏移；M020是空tensor前向到反向NaN。必须先证明槽位消费资格，不能直接归类。',
  hint='PR4833是反向grad_probs dtype子问题，不是本条前向负值语义修复。'),
 'RC-029': dict(title='scale实参与载荷契约关系待核',carrier='FP8 Attention内核调用参数；完整实现阶段未知',
  known='来源声明V scale读取异常。历史选段记录FlashUpdate相关参数由deScalePreVValue替换为deScaleVValue。',
  unknown='两个变量的对象、类型、数值含义、定义及参数契约未知；变量名不足以确定块、时间或轴语义。',
  alternatives=['对象绑定差异','数值含义或类型契约差异','选段外的实现改动'],modes=['M010','M024'],
  common='缩放计算链或表示转换可能相关。',boundary='M010是图中Dequantize位置，M024是内存排布。仅参数替换不能确认独立错绑机理，也不能直接归类。',
  hint='cann/ops-transformer#8005，commit f4f1bafc2ffefc94306e0ea6403ff362e5259331，历史文件选段589–612；完整Diff和变量定义待补。'),
 'RC-062': dict(title='辅助张量内容／生命周期关系待核',carrier='verl／vllm调用准备与辅助张量传递；具体层未知',
  known='来源声明verl切pe／nope的sin、cos全零，单推是正常数值。当前尚未证实两侧目标调用可比。',
  unknown='位置、配置、合法域和目标调用身份未知；差异可来自构造、初始化、传递、取错对象或恢复。',
  alternatives=['构造不同','初始化不同','传递差异','取错对象','恢复差异','目标调用本身不可比'],modes=['M020','M027'],
  common='边界内容或view适用性可作为对照方向。',boundary='M020的空tensor不等于非空全零sin／cos；M027的私有格式限制未被说明。不能命名为恢复遗漏或确认CANN缺陷。',
  hint='现有npu_mrope DTS摘要未给根因，不支持本条辅助张量差异的产生环节。'),
 'RC-105': dict(title='确定性请求到有效分派的传播关系待核',carrier='PTA通信buffer配置更新与ReduceScatter分派',
  known='来源声明新增buffer配置时覆盖确定性配置，未进入确定性分支，RC1修复。',
  unknown='配置编码、写入主体、更新语义和具体RC1版本／提交未知；不指定结构覆盖、字段重置或位域操作。',
  alternatives=['配置更新传播错误','设置作用域或初始化错误','来源省略了分派条件'],modes=['M028','M013'],
  common='确定性能力／适配控制路径具有相似性。',boundary='M028是HCCL与LCCL能力差异，本条声明请求未传到分派；M013为标量参数适配。载体位置不能决定合并或新增。',
  hint='需配置更新与确定性分派修复的具体提交；只写RC1不能定位版本。'),
}

# Each tuple is one driver, not one keyword: label, name kind, Q1, Q2,
# creator, initializer, writable owner, resetter, Q4. Unknowns are explicit.
DRIVERS = {
 'RC-009': [
 ('当前输入布局／stride','SEMANTIC_ROLE','当前调用输入张量的布局描述，不是缓存条目本身。','stride按元素还是字节解释未知；shape、连续性判定及类型未知。','输入张量／view创建方未知','布局元数据建立方式未知','是否允许框架重写布局未知','下一调用／view复用时元数据更新责任未知','host-tiling缓存匹配逻辑；具体函数未知'),
 ('缓存适用描述','SEMANTIC_ROLE','某条缓存tiling结果对应的可用输入集合。','字段、布局编码及范围未知；不能预断key字段遗漏。','缓存条目生成主体未知','插入时如何写入描述未知','缓存描述是否可变及写入方未知','淘汰、失效或跨上下文清理规则未知','缓存匹配／命中判断函数未知'),
 ('复用资格','SEMANTIC_ROLE','当前调用是否有资格消费该缓存结果的判定。','非计数量；判定布尔／枚举编码与合法域未知。','匹配判定的计算主体未知','默认命中／未命中值未知','谁可更新复用判定未知','每次调用是否重算及异常复位未知','取用tiling结果的调用路径未知'),
 ],
 'RC-010': [
 ('期望ctrl状态','SEMANTIC_ROLE','目标设备／上下文所需ctrl状态；作用域未知。','非计数量；寄存器位、掩码、期望编码和合法域未知。','状态需求由何种指令／平台契约定义未知','摘要称TPipe构造曾设置ctrl，具体动作未见代码','其它可写主体未知','调用、stream或context切换后复位规则未知','依赖ctrl的指令／kernel未定位'),
 ('实际ctrl状态','SEMANTIC_ROLE','本次消费时设备／上下文中的实际状态，不是期望值。','非计数量；未采集实际位值，不能对比编码。','实际状态来自哪个context未知','来源称取消TPipe后设置操作缺失；尚未代码核验','谁能修改及并发范围未知','何时清理或恢复未知','首次读ctrl的位置未知'),
 ('执行模板选择','SEMANTIC_ROLE','采用极致头开销模板的实现路径选择。','非计数量；模板选择编码、输入谓词和版本未知。','模板分派方未知','默认模板与配置建立方式未知','版本或工具是否改变模板未知','后续调用重选规则未知','执行模板入口及其初始化契约未知'),
 ],
 'RC-023': [
 ('sorted_indices原值','SOURCE_NAME','abs之前的索引及可能的负值标记。','整数索引域；dtype、负值语义、允许范围未知。','模型路由／排序产生方待核','默认哨兵／填充值未知','abs前其它写入方未知','每轮路由重建及清理未知','abs转换及原接口契约需核对'),
 ('abs后索引','SEMANTIC_ROLE','模型对sorted_indices取abs后的实际传入值。','绝对值转换可改变符号；是否改变有效性语义需合同，不能仅凭转换判缺陷。','来源声明模型执行abs','转换后默认和空位置如何保留未知','转换后是否再次修改未知','调用间索引复用与重建未知','token_unpermute前向；不得套用反向grad_probs dtype修复'),
 ('有效专家／位置集合','SEMANTIC_ROLE','被合同允许参与输出组合的专家槽位集合。','集合／掩码非计数量；负标记到有效集合的规则未知。','有效性计算主体未知','默认激活／屏蔽状态未知','模型或算子是否可更新掩码未知','每次调用的集合重算责任未知','专家结果筛选与组合消费者未定位'),
 ('专家槽位结果可用性','SEMANTIC_ROLE','每个被消费槽位是否具有合同认可的结果。','结果数值dtype和默认填充值未知；未执行MLP不等于未初始化。','槽位分配方未知','需检查默认填充，未采到初始化代码','MLP及其它填充写入方未知','跨调用复用／清理及掩码责任未知','输出聚合是否只消费有效且可用槽位待核'),
 ],
 'RC-029': [
 ('deScalePreVValue','SOURCE_NAME','历史选段中出现的scale变量；完整绑定对象未知。','dtype、数值含义、shape和轴对应未知；名字不证明时间或块语义。','变量定义位置未在选段核验','首次赋值与有效默认值未知','后续可写位置未知','更新／复用／复位规则未知','选段记录其曾处于FlashUpdate实参位置；完整参数契约未知'),
 ('deScaleVValue','SOURCE_NAME','历史选段中替换传入的scale变量；对象绑定未知。','数值类型、量化／反量化语义和shape未知。','定义及读取来源未核验','首次赋值与默认状态未知','谁可更新该量未知','作用域与复位规则未知','FlashUpdateNew／FlashUpdateLastNew选段实参；参数位置需完整声明'),
 ('相关V载荷','SEMANTIC_ROLE','被上述调用消费的Value载荷；与两scale如何对应未知。','FP8为来源上下文；具体载荷dtype、scale类型与换算契约未核。','载荷生成／读取方未知','缓冲区填充与初始化未知','允许写入主体未知','调用间及循环复用规则未知','Attention更新过程，具体函数合同未知'),
 ('FlashUpdate参数绑定','SEMANTIC_ROLE','某实参位置绑定哪个scale变量这一关系。','非计数量；签名、参数序号和各参数定义域待完整源码。','调用点形成绑定','来源选段记录替换事实，不能证明默认规则','谁改写调用参数未知','执行分支切换后的绑定规则未知','FlashUpdate相关函数声明／函数体未完整核验'),
 ],
 'RC-062': [
 ('sin辅助张量','SEMANTIC_ROLE','verl目标调用中sin与单推对照；目前可比性未证。','来源称全零；shape、dtype、数值合法域及位置对应未知。','构造主体未知','来源说初始化全0；未见写入位置，不能确认遗漏','传递中可写主体与别名关系未知','是否恢复或复用未知，恢复只是解释之一','pe／nope相关目标调用具体接口未知'),
 ('cos辅助张量','SEMANTIC_ROLE','verl目标调用中cos；不能与sin或其它位置张量混为一物。','全零为来源声明；dtype、shape及合法域待核。','构造主体未知','首次赋值与默认规则未知','传递和修改主体未知','清理、重建、恢复或复用规则未知','具体pe／nope调用及其对cos的合同未知'),
 ('位置对照','SEMANTIC_ROLE','两侧目标调用的token位置／position对应。','位置坐标系、索引单位和合法域未知。','位置生成主体未知','初始位置和偏移未知','位置更新方未知','请求间复位／cache复用规则未知','辅助张量选择及目标调用待核'),
 ('RoPE配置对照','SEMANTIC_ROLE','verl与单推各自的RoPE等配置，是否相同未知。','非计数量与数值参数混合；配置字段、编码和定义域待核。','配置来源未知','默认值建立未知','适配层能否改写未知','模型加载／切换／恢复责任未知','构造和消费sin／cos的调用双方需共同核对'),
 ],
 'RC-105': [
 ('确定性请求','SEMANTIC_ROLE','调用者要求的确定性行为；API还是环境设置未知。','非计数量；布尔／枚举编码和合法域待核。','请求产生主体未知','默认值和设置时点未知','谁可修改请求未知','请求／context结束后的复位未知','配置传播入口未知'),
 ('buffer配置更新','SEMANTIC_ROLE','来源所称新增通信buffer配置代码的更新动作及配置对象。','非计数量；更新结构、字段编码及作用域未知。','配置对象创建方未知','默认及初始内容未知','更新主体待核，不指定整结构、字段或位域实现','配置切换与复位规则未知','配置合成／提交消费者未知'),
 ('有效确定性设置','SEMANTIC_ROLE','分派前实际可见的确定性设置，不等同调用者请求。','非计数量；有效编码、作用域与传播转换未知。','从请求合成有效值的主体未知','有效值首次建立时点未知','buffer更新是否影响该值需代码核验','调用／设备／context复位未知','ReduceScatter分派读取位置未知'),
 ('分派决定','SEMANTIC_ROLE','最终进入哪个ReduceScatter实现分支。','非计数量；分派谓词及编码未知，不能用后端名代替决定。','分派计算主体未知','默认分支规则未知','条件更新及缓存责任未知','每调用是否重新分派未知','被选择的实现及确定性能力契约待核'),
 ],
}


def answer(text, refs, *, source=False):
    return dict(answer=text, status='SOURCE_DESCRIBED_WITH_GAPS' if source else 'UNKNOWN_OR_DESIGN_QUESTION',
                basis='SOURCE_DECLARATION' if source else 'BOUNDED_ANALYSIS', evidence_ids=list(refs),
                unknown_reason='未取得相关完整源码／契约／执行取值；以上未知不能补成实现事实。', confirmed=False)


def quantities(task_id, refs):
    result=[]
    for i,(label,kind,obj,unit,creator,initializer,writers,reset,consumer) in enumerate(DRIVERS[task_id],1):
        result.append(dict(quantity_id=f'{task_id}:QTY-{i:02}',task_id=task_id,label=label,name_kind=kind,
            name_scope='SOURCE_NAME仅确认原文／选段存在该名称；SEMANTIC_ROLE不是源码变量名。',
            Q1=answer(obj,refs,source=True),Q2=answer(unit,refs),
            Q3=dict(creator=answer(creator,refs),initializer=answer(initializer,refs),
                    writable_owners=answer(writers,refs),reset_responsibility=answer(reset,refs)),
            Q4=answer(consumer,refs), questions_recorded=True,relation_confirmed=False,
            unit_error_confirmed=False,manual_accept_created=False))
        if task_id=='RC-029'and kind=='SOURCE_NAME':
            result[-1]['Q1']['basis']='PRIOR_SELECTED_CODE_OBSERVATION'
            result[-1]['Q1']['status']='CODE_NAME_OBSERVED_SEMANTICS_INCOMPLETE'
    return result


def review(task_id, refs, mode_index):
    d=deepcopy(REVIEWS[task_id])
    source_claim='来源声明FP8 Attention的静态量化V scale读取异常；完整原文尚未补齐。' if task_id=='RC-029' else d['known']
    claims=[dict(claim=source_claim,basis='SOURCE_DECLARATION',evidence_ids=[r for r in refs if not r.startswith('OBS:')],
                 limitation='转交声明／摘要，不是本轮独立根因、事件或设备确认。')]
    if task_id=='RC-029':
        claims.append(dict(claim='归档选段中的FlashUpdate实参替换事实。',basis='PRIOR_SELECTED_CODE_OBSERVATION',
            evidence_ids=['OBS:TC-FP8-VSCALE:1:before','OBS:TC-FP8-VSCALE:1:after'],
            limitation='全文完整性未证，未核变量定义／函数合同，未执行设备验证。'))
    return dict(task_id=task_id,candidate_mechanism=dict(name=d['title'],status='PENDING_RELATION_REVIEW',
                  expected_relation=EXPECTED[task_id],known=d['known'],unknown=d['unknown'],alternatives=d['alternatives']),
        implementation_carrier=dict(description=d['carrier'],determines_mode_relationship=False),
        evidence_level=dict(claims=claims,unknown=d['unknown']),
        original30_relation=dict(status='PENDING',similar_modes=[dict(mode_id=m,original_definition=mode_index[m]['original_definition'])for m in d['modes']],
             common=d['common'],boundary_discussion=d['boundary'],priority_inferred_from_four_questions=False),
        targeted_evidence_gap=d['hint'],quantity_ids=[f'{task_id}:QTY-{i:02}'for i in range(1,len(DRIVERS[task_id])+1)],
        review_scope='DRIVING_QUANTITY_REVIEW_WITH_GAPS',relation_confirmed=False,
        new_or_extension_confirmed=False,hardware_validated=False,formal_adoption=False)
