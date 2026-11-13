"""R4 pilot mechanism/design cases, bounded to the immutable R3 code evidence.

This is offline report data, not an execution client.  Public code observations
are independent technical cases, never confirmations of the weekly events.
``mechanism_cases()`` returns fresh dictionaries with exact frozen predicates.
No API42/V4 or original30 definition is edited, widened, or auto-converted.
"""
from copy import deepcopy
import json
from pathlib import Path


R3 = Path(__file__).resolve().parents[1] / "reports/archive/rc128-evidence-review-20261112-r3"
EVIDENCE_LEVEL = "CODE_OBSERVED_WITH_LIMITS"
REPRESENTATIVE_TASK_IDS = ("RC-002", "RC-024", "RC-029", "RC-030", "RC-031", "RC-099", "RC-122")


def locator(resource_id, file, marker, claim_scope):
    return dict(resource_id=resource_id, file=file, marker=marker, claim_scope=claim_scope)


def variable(name, role, meaning, proposed_values, unknown_reason=""):
    return dict(name=name, role=role, meaning=meaning, proposed_values=proposed_values,
                unknown_reason=unknown_reason)


def candidate(system, condition_id, status, reason, requires, skip_if, *, family_gate="", mounts=None):
    # Deliberately curated mounts: never inherit every class attached to a
    # frozen construction. Each entry below has separately authored checks.
    selected = {
        "enum_compute": ("C1", "C2"), "intermediate_overflow": ("N4",),
        "buffer_fit": ("S2",), "enum_quant": ("C1", "C2"),
        "scale_structure": ("S7",), "nondegenerate": ("S9",),
        "tile_shape": ("S5", "C4"), "unequal_axes": ("S3",),
        "enum_dtype": ("C1",), "enum_behavior": ("C2", "C4"),
        "index_edge": ("I2",),
    }
    return dict(system=system, condition_id=condition_id, semantic_applicability=status,
                reason=reason, _requires_notes=requires, _skip_notes=skip_if,
                family_gate_check=family_gate,
                reviewed_class_ids=list(mounts if mounts is not None else selected[condition_id])
                if system == "V4" else [])


def design(status, variables, target_path, baseline, oracle, capability, unknowns):
    return dict(design_status=status, variables=variables, target_path=target_path,
                baseline=baseline, oracle=oracle, capability=capability, unknowns=unknowns,
                execution_status="NOT_EXECUTED", hardware_validated=False)


def case(task_id, issue_key, title, mechanism, expected, change, resources, markers,
         modes, boundary, conditions, proposed_design, limits):
    return dict(task_id=task_id, issue_key=issue_key, title=title,
                entity_type="INDEPENDENT_PUBLIC_TECHNICAL_CASE",
                mechanism_claim=mechanism, expected_relation=expected, observed_change=change,
                evidence_level=EVIDENCE_LEVEL, resource_ids=resources, locator_markers=markers,
                original30=dict(similar_mode_ids=modes, boundary=boundary,
                                decision="DISCUSSION_ONLY", original_definitions_modified=False),
                candidate_conditions=conditions, proposed_design=proposed_design,
                source_read_limitations=limits, event_relation="UNDETERMINED",
                weekly_event_confirmed=False, hardware_validated=False, formal_adoption=False)


S = "SATISFIED"
U = "UNKNOWN"
N = "NOT_SATISFIED"
NT = "NOT_TRIGGERED"
T = "TRIGGERED"

_CASES = [
    case(
        "RC-002", "RC-002:gemm-precision-flag", "GEMM精度标志由调用者传给消费者",
        "两处AlphaBeta GEMM调用原来没有显式传入enableGemm16In32Out；补丁根据matA、matB、output的dtype和cubeMathType计算该量并传入。可观察的断点是精度选择信息的调用边传播，不是已证明的kernel中间值溢出。",
        "当前输入/输出类型及计算模式要求的精度选择，应传到所选ExecGemmV3WithAlphaBetaOp调用；完整NeedEnableFp32Output谓词和kernel执行语义需另读。",
        "aclnn_baddbmm.cpp和aclnn_addmm.cpp各新增NeedEnableFp32Output调用，再把返回布尔量作为ExecGemmV3WithAlphaBetaOp末参。可见外层要求CheckGemmV3WithAlphaBeta且DAV_2201；beta=0、cubeMathType=4来自既有技术审读，不能由这两段hunk独立还原全部谓词。",
        ["CANN10622"],
        [locator("CANN10622", "evidence/pilot/evidence/side/CANN-10622.diff",
                 "bool enableGemm16In32Out = NeedEnableFp32Output(matA->GetDataType(), matB->GetDataType(),",
                 "两个host调用点计算精度标志"),
         locator("CANN10622", "evidence/pilot/evidence/side/CANN-10622.diff",
                 "auto outGemmV3 = ExecGemmV3WithAlphaBetaOp(bias, matA, matB, alpha, beta, executor, enableGemm16In32Out);",
                 "addmm调用显式传播标志"),
         locator("CANN10622", "evidence/pilot/evidence/side/CANN-10622.diff",
                 "bool isSupportNpuArch = (npuArch == NpuArch::DAV_2201);", "可见平台门槛")],
        ["M001", "M009", "M013", "M017"],
        "M001/M009涉及低精计算范围，M013是block_dim标量支持及常量折叠，M017是PageAttention tiling差异。此处具体关系是精度标志传播；不能仅凭Inf或baddbmm名称继承M009客户根因，也不能把所有新增参数并入M013。",
        [candidate("API42", "1.C.3", "APPLICABLE", "可见调用含cubeMathType，适合计算模式对照；模式的合法枚举仍须契约。",
                   [(S, "cubeMathType作为此host API调用中的计算模式量明确可见。")], [],
                   family_gate="目标API签名含cubeMathType；实际schema需原样暴露此参数，不能以修改内部布尔量代替API实参。"),
         candidate("API42", "1.7.6", "PARTIAL", "可设计有限输入而低精中间值超范围的敏感数据；本hunk未证明GEMM内部中间精度。",
                   [(S, "matA/matB为数值矩阵，包含浮点或可转浮点的数值载荷。")],
                   [(NT, "该矩阵乘加路径不是无data的shape推导。")]),
         candidate("V4", "enum_compute", "APPLICABLE", "分别核对C1混合精度和C2显式计算模式，不以缺陷已证为分类前提。",
                   [(S, "标志明确读取输入及output dtype，构造目标是16in32out混合精度。"),
                    (S, "cubeMathType为显式计算模式；合法值待API契约限定。")],
                   [(NT, "本候选目标包含低位宽输入/FP32输出组合。"),
                    (NT, "调用含cubeMathType，并非完全不可选择的内部策略。")]),
         candidate("V4", "intermediate_overflow", "PARTIAL", "矩阵乘加可适用N4敏感分布；内部溢出只是待测假设。",
                   [(S, "baddbmm/addmm为乘加链，可构造量级差异明显的矩阵和alpha。")],
                   [(NT, "不是纯拷贝/索引路径。")])],
        design("NEEDS_FACTS", [
            variable("matA/matB/output dtype", "INPUT", "原始矩阵与输出精度组合", ["FP16,FP16->FP32", "合法FP32对照"], "混合组合的完整API合法域待核"),
            variable("alpha,beta,cubeMathType", "INPUT", "算式系数及计算模式", ["beta=0,cubeMathType=4候选", "合法相邻模式对照"], "完整CheckGemmV3WithAlphaBeta和模式合同未在hunk中"),
            variable("enableGemm16In32Out", "DERIVED", "NeedEnableFp32Output的结果，禁止当成用户输入", ["记录函数结果及传入末参"]),
            variable("npuArch", "CONTEXT", "平台门槛", ["DAV_2201"]),
            variable("幅值/缩放对照", "INPUT", "使高精参考有限、低精候选中间量敏感", ["A*B超FP16范围且alpha*(A*B)落在FP32有限域", "同比缩小幅值"], "先核GEMM乘加/alpha施加顺序，不能假定最终值有限就必溢出")],
            "仅命中CheckGemmV3WithAlphaBeta && DAV_2201的addmm/baddbmm调用，并记录标志是否传至消费者。",
            "同一转换后的输入做FP64/FP32参考；补丁前后相同模式；另设不过范围的数据对照。",
            "先判标志传播与目标分支，再判输出有限性及相对/绝对误差；标志正确不单独证明数值修复。",
            "离线可做host调用参数跟踪；目标平台、旧/新构建和dtype合同尚未核验。",
            ["NeedEnableFp32Output及CheckGemmV3WithAlphaBeta完整定义", "GEMM消费者签名/内部计算精度", "客户实际beta/cubeMathType及版本身份"]),
        ["两文件完整hunk，不是完整GEMM实现。", "公开修复与周报FP16多kernel中间传递是分别保存的技术事实；beat/batch/beta转录冲突不静默归一化。"]),

    case(
        "RC-024", "RC-024:topk-workspace-contract", "TopK临时空间需求、预算与分配一致",
        "host新增GetTopKMaxMinTmpSize并将maxsize写入tiling的tmpUbSize；kernel用此值同时扣除总预算并切出TopK临时区，替代20*S2的启发式。库API需求与分配容量应相符。",
        "对同一TopK问题和模式计算的临时字节数，应在host传递、kernel总量预算和GetWithOffset分配中保持一致；不把元素数、对齐后长度和字节数互换。",
        "host把maxsize保存为uint64 tmpUbSize；maxTopkBase的分子从190*1024-20*S2sizeAlign32变为190*1024-tmpUbSize；topKTmpLocal从20*S2sizeTopK字节改为tmpUbSize字节。",
        ["GC-cann-ops-transformer-8365"],
        [locator("GC-cann-ops-transformer-8365", "evidence/side/cann__ops-transformer__8365.diff", "AscendC::GetTopKMaxMinTmpSize(ascendcPlatform,", "库API临时区需求入口"),
         locator("GC-cann-ops-transformer-8365", "evidence/side/cann__ops-transformer__8365.diff", "tilingData.importanceScoreParams.set_tmpUbSize(static_cast<uint64_t>(maxsize));", "host到tiling传播"),
         locator("GC-cann-ops-transformer-8365", "evidence/side/cann__ops-transformer__8365.diff", "uint32_t maxTopkBase = (190 * 1024 - tmpUbSize) / (4 * S2sizeAlign32 + 8 * k_pad);", "总预算消费者"),
         locator("GC-cann-ops-transformer-8365", "evidence/side/cann__ops-transformer__8365.diff", "topKTmpLocal = allUbBuffer.GetWithOffset<uint8_t>(tmpUbSize, addrOffset);", "字节临时区分配")],
        ["M015", "M011", "M026"],
        "M015原例是FIA踩踏reducesum，M011是分支判断，M026原例是indices输入未对齐32B。此处是TopK库需求与容量规划；先比较关系再讨论扩展，不能因内存异常就继承原例对象/具体触发。",
        [candidate("API42", "1.2.6", "PARTIAL", "预算/分块边界已见，但使host API命中相同问题规模的完整映射尚未还原。",
                   [(S, "S2sizeTopK、S1Base和topkBase来自可变化的TopK问题规模。"),
                    (U, "190*1024预算公式可见；完整host模板门槛、各参数范围及topkBase的一致性未读全。")],
                   [(NT, "存在张量shape和TopK规模。")]),
         candidate("API42", "1.3.2", "NOT_APPLICABLE", "本子问题未显示索引位宽溢出；普通shape引起临时区不足不能绕过原1.3硬条件。",
                   [(N, "本设计改变S2/k及容量，不把索引结果当成可控TEN-INDEX或地址映射实参。"),
                    (N, "无>uint16/>int32的offset溢出证据或目标公式。")],
                   [(T, "在本子问题限定的普通数据shape/TopK规模构造中，没有可控索引/下标/窗口映射实参。")]),
         candidate("V4", "buffer_fit", "APPLICABLE", "明确存在临时空间需求查询、190KiB预算和分配字节数，可按S2做容量两侧对照。",
                   [(S, "shape可改变S2与k；实现存在明确容量公式。")],
                   [(U, "设备UB实际可用量、库返回字节数及执行器可达规模尚未测定；未评估不等于能力缺失。")])],
        design("NEEDS_FACTS", [
            variable("S2sizeTopK,k,S1Base,dtypesize", "INPUT", "影响TopK库需求及每行工作集的合法问题量", ["满足合同的S2/k网格", "S2在blockLength两侧"], "需确认外部shape到本地量的映射及合法k<=S2"),
            variable("S2sizeAlign32,k_pad,tmpUbSize,maxTopkBase", "DERIVED", "对齐长度、API需求字节和可容纳行数", ["Q=GetTopKMaxMinTmpSize(...)的maxsize", "old=20*S2", "remaining=190*1024-Q"], "库参数与kernel实际TopK参数必须逐项核对"),
            variable("UB/platform", "CONTEXT", "190KiB路径对应平台及可用总量", ["补丁指定目标平台"], "完整平台限制未读"),
            variable("memory checking", "EXECUTION_PROTOCOL", "容量越界检测而非只看输出NaN", ["旧/新构建相同输入并启用内存检测", "记录addrOffset与最终区间"] )],
            "NsaCompressAttention的TopKTiling及NsaCompressAttentionS1s2Bn2gs1SameAB中该TopK分配路径。",
            "库API返回的maxsize为需求基线；旧启发式容量与新容量对照，保持TopK输入和模式相同。",
            "检查各切片区间不重叠且末端<=有效UB；tmp分配>=对应实际TopK需求；补充TopK值/索引参考，不以NaN消失代替内存判据。",
            "可离线计算预算和区间；需要匹配版本库的需求查询及设备内存检测能力，未执行。",
            ["host和kernel使用的TopK问题参数是否完全一致", "合法S2/k及blockLength", "API返回size与实际可用UB"]),
        ["三个文件的完整hunk；未将相邻未读函数推为已核。", "PR说明tempUb超分配为作者声明，周报客户是否命中此模板未知。"]),

    case(
        "RC-029", "RC-029:vscale-call-binding", "相邻scale读取值与调用实参绑定",
        "旧代码从max(deScaleVOffset-1,0)读float到deScalePreVValue，并将它作为四处FlashUpdate调用末参；新代码删除此读，四处末参均改为deScaleVValue。可定位实参绑定变化，但完整被消费对象及阶段语义未知。",
        "FlashUpdateNew/FlashUpdateLastNew各scale实参须满足函数签名与所消费载荷的数值契约；邻接存储下标不自动表示前一块、前一token或前一时间步。",
        "非末S2循环/末S2循环及两个模板布尔分支均改相同末参；deScalePreVOffset和对应GM GetValue被删除。",
        ["GC-cann-ops-transformer-8005"],
        [locator("GC-cann-ops-transformer-8005", "evidence/side/cann__ops-transformer__8005.diff", "uint32_t deScalePreVOffset = (deScaleVOffset < 1) ? 0 : deScaleVOffset - 1;", "旧下标的精确表达式"),
         locator("GC-cann-ops-transformer-8005", "evidence/side/cann__ops-transformer__8005.diff", "float deScalePreVValue = this->deScaleVGm.GetValue(deScalePreVOffset);", "旧float值的来源"),
         locator("GC-cann-ops-transformer-8005", "evidence/side/cann__ops-transformer__8005.diff", "+                        deScaleVValue, deScaleVValue);", "四个调用末参替换；该marker有四处，应分别定位"),
         locator("GC-cann-ops-transformer-8005", "evidence/side/cann__ops-transformer__8005.diff", "FP8_DTYPE = torch.float8_e4m3fn", "同PR测试的明确FP8 dtype；不证明该测试已绑定本kernel"),
         locator("GC-cann-ops-transformer-8005", "evidence/side/cann__ops-transformer__8005.diff", "query_dtype=FP8_DTYPE,", "同PR调用测试的dtype参数；只支持C1结构语境，不证明C2或schema控制")],
        ["M010", "M024", "M004"],
        "M010是图优化Dequantize节点位置/量化链断裂，M024是内存排布转换，M004是window偏移踩踏。此处只已见scale读取下标及参数绑定；不能由变量名把它升级为阶段错绑或内存转换，也不能由scale一词建立S7。",
        [candidate("API42", "1.C.1", "PARTIAL", "FP8 fullquant上下文和量化选项可见，但此kernel分支对应的完整API实参合同未还原。",
                   [(U, "同PR测试包含query/key/value_quant_mode；这些模式到本四处调用的完整分派映射尚未核。")], [],
                   family_gate="必须核目标API确实暴露并允许这些quant模式；内部变量名不能替代SEM-QUANT。"),
         candidate("V4", "enum_quant", "PARTIAL", "C1量化载荷成立；C2目标API模式到本调用路径仍需独立核对。",
                   [(S, "文件为FP8 fullquant路径并含scale读取。"),
                    (U, "PR测试中的量化实参尚未建立到本kernel四分支的完整映射。")],
                   [(NT, "该候选不是仅固定高精、无量化载荷的路径。"),
                    (U, "合法API实参能否选择所需四分支待查。")]),
         candidate("V4", "scale_structure", "UNKNOWN", "本机理是标量读取/实参替换；S7必须另证scale shape与载荷轴对应，不能凭scale命名成立。",
                   [(U, "虽相邻checker和测试另有scale shape信息，但未证明这两个标量在本调用中的轴对应及映射。")],
                   [(U, "本标量位置对应的合法广播/辅助shape范围及消费者合同未知。")]),
         candidate("V4", "nondegenerate", "APPLICABLE", "hunk直接存在S2循环及第二轮条件，可设计一轮与多轮对照。",
                   [(S, "runInfo.isLastS2Loop及runInfo.s2Idx==s2BaseSize明确表明随规模变化的S2轮次。")],
                   [(NT, "已见多轮条件，不是单次无轮次实现。")])],
        design("NEEDS_FACTS", [
            variable("dequant_scale_value内容", "INPUT", "合法scale内容使邻接下标值可区分", ["全相等对照", "正有限、可精确表示且相邻不等，如1与2"], "需确认deScaleVGm对应哪个API tensor及其合法shape/数值域"),
            variable("deScaleVOffset,deScalePreVOffset,deScaleVValue", "DERIVED", "本分支算出的索引及实参值", ["offset=0与>0", "记录旧max(offset-1,0)值和两个实际末参"], "deScaleVValue定义及完整offset映射未见"),
            variable("S2规模/分块", "INPUT", "选择非末轮、末轮及第二轮条件", ["使循环轮数为1、2、3的合法序列长度"], "s2BaseSize及完整分派门槛待核"),
            variable("arch35/FP8 fullquant build", "CONTEXT", "目标实现及版本", ["8005补丁前后相同构建环境"], "设备执行能力未评估")],
            "四处FlashUpdateNew/FlashUpdateLastNew调用；逐分支记录签名位置和实际scale值，不用选段外函数语义作结论。",
            "全相同scale是低敏感基线；相邻不等scale配合固定Q/K/V，对照按实际输入反量化的高精Attention参考。",
            "先证目标调用和实参变化，再比输出/中间更新误差；同值对照通过不能否定错绑定假设。",
            "可先做实参跟踪及mock合同检查；完整数值oracle需要函数签名、变量定义和合法shape，设备未执行。",
            ["FlashUpdate完整签名及两scale角色", "deScaleVValue定义/索引到载荷映射", "同PR检查/Golden共改对结果的独立影响"]),
        ["此条只审kernel引用hunk及测试模式线索；PR其余checker/Golden变更不是同一scale根因证明。", "已知源码足以提出区分scale内容的设计，客户事件身份缺口不阻塞候选分类。"]),

    case(
        "RC-030", "RC-030:dequant-reduction-stride", "派生宽度到reduce重复步长的整数换算",
        "WholeReduceMax的源重复步长从(q/64)*8改成q/8（q=tl_->UbFactorDimy，常量值按既有审读64和8）。先整除64会丢失q在64内的余数，不能一般等同按8元素块换算。",
        "源行的实际元素间距换成指令块单位时，须保留合法q所需步长；q/64*8与q/8仅在相应整除条件下相等。q是tiling派生量，不能直接把输入shape当q。",
        "WholeReduceMax的srcRepStride由tl_->UbFactorDimy / MASK_NUM_T32 * MASK_BLK_STRIDE替换为tl_->UbFactorDimy / BLOCK_ELEM。",
        ["GH12123"],
        [locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-2.patch", "tl_->UbFactorDimy / MASK_NUM_T32 * MASK_BLK_STRIDE,", "旧先除后乘步长"),
         locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-2.patch", "tmpUbF32Gate, tmpUbF32Gate, MASK_NUM_T32, proDimsx, 1, 1, tl_->UbFactorDimy / BLOCK_ELEM,", "新reduce步长"),
         locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-3.patch", '([2, 192], 0.0, "small_192_misaligned"),', "新增输入192测试；名称不是实际q已采集证据")],
        ["M026", "M004", "M024"],
        "M026原例是indices输入未对齐32B，M004是window区偏移，M024是格式转换；本例是派生行宽到reduce块步长的整数换算。输入192可被64整除，不能把测试名misaligned当输入非64对齐；q值及映射需观测。",
        [candidate("API42", "1.2.2", "PARTIAL", "可以由合法shape使派生q处于64对齐两侧，但输入到q映射待核。",
                   [(S, "新增测试明确给出可配置x_shape。")], [(NT, "不是无shape接口。")]),
         candidate("API42", "1.3.2", "NOT_APPLICABLE", "步长换算错误不是索引位宽溢出，普通shape不能进入原1.3族。",
                   [(N, "本设计仅数据shape，未提供TEN-INDEX/MOE下标或SEM-INDEX-CTRL/SLICE实参。"),
                    (N, "没有超过uint16/int32的offset阈值证据。")],
                   [(T, "本子问题限定普通数值张量及shape，无索引/下标/窗映射实参。")]),
         candidate("V4", "tile_shape", "PARTIAL", "S5有指令粒度和派生tile宽度；C4完整输入分派谓词未核，分别登记。",
                   [(S, "reduce调用含MASK_NUM_T32/BLOCK_ELEM和tl_->UbFactorDimy，存在可定位分块步长。"),
                    (U, "x_shape到UbFactorDimy及模板分派的完整谓词未读全。")],
                   [(NT, "已有实际分块/步长代码。"), (U, "尚不知完整模式选择/输入驱动分派条件。")])],
        design("NEEDS_FACTS", [
            variable("x_shape", "INPUT", "原算子输入shape", [[2, 192], [4, 192], [8, 384], [1, 256]], "这些是新增测试输入；对应q必须读tiling/日志，禁止直接赋q=192"),
            variable("q=UbFactorDimy", "DERIVED", "reduce行间元素间距", ["q%8=0且q%64=0基线", "q%8=0且q%64!=0敏感组", "算术探针q=96:旧8/新12"], "96是离线算术反例，不声称外部输入必可达"),
            variable("proDimsx", "DERIVED", "重复行数", ["1与>=2"], "行数需从合法shape/tiling派生"),
            variable("row-tagged values", "INPUT", "不同源行具有不同绝对最大值及最大值位置", ["每行唯一最大值，行首/尾交替", "全相同最大值阴性对照"] )],
            "DequantSwigluQuantBase::DynamicQuant的WholeReduceMax，记录真实q、proDimsx和地址/指令步长。",
            "逐行abs最大值的高精参考；只改reduce步长的隔离构建与完整PR构建均对照。",
            "每行max和scaleOut对应本行；输出int8及scale分别核验；避免把共改scaleBuf的作用算到步长单因素。",
            "离线整数反例可直接审；可达q及设备reduce指令需要tiling合同/执行器，未执行。",
            ["常量定义和指令步长单位", "输入shape到真实q的映射", "与广播临时区共改的因果隔离"]),
        ["完整三个文件patch只提供变更hunk，不是CountMaxDim/DynamicQuant完整函数。", "新增测试有数值assert和NPUGraph replay，未由本轮运行；测试代码不等于设备复现。"]),

    case(
        "RC-030", "RC-030:dequant-broadcast-storage", "scale广播临时区的分配、使用与预算",
        "Brcb原写outLocal，再由Copy读outLocal；补丁新增float scaleBuf_并用brcbTmp承接广播，Copy改读它，同时修改host UB预算。临时广播展开量、独立存储和容量预算必须一致。",
        "广播的proDimsx到按BLOCK_ELEM展开的float结果，需要足够且生命周期受控的存储；host为新缓冲预留的字节数须覆盖kernel分配量。",
        "新增scaleBuf_，按ceil(UbFactorDimx/BLOCK_ELEM)*BLOCK_ELEM^2*sizeof(float)分配；Brcb/Copy改用brcbTmp并FreeTensor；CountMaxDim分子/分母均新增空间项。",
        ["GH12123"],
        [locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-2.patch", "((tl_->UbFactorDimx + BLOCK_ELEM - 1) / BLOCK_ELEM) * BLOCK_ELEM * BLOCK_ELEM * sizeof(float));", "新float广播区容量"),
         locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-2.patch", "Brcb(brcbTmp, scaleOut, blockCount, {1, MASK_BLK_STRIDE});", "广播写目标"),
         locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-2.patch", "tmpUbF32Gate, brcbTmp, AscendC::MASK_PLACEHOLDER, proDimsx,", "广播结果消费者"),
         locator("GH12123", "evidence/pilot/evidence/decoded/vllm-12123-1.patch", "BLOCK_ELEM * BLOCK_ELEM * static_cast<int64_t>(sizeof(float));", "host新增预算项")],
        ["M015", "M026", "M024"],
        "M015可比较临时区覆盖关系，M026可比较tiling容量，M024可比较广播排布；原例对象不同。未从hunk证明outLocal旧容量究竟不足多少，也未隔离步长与存储两项共改，不能称两项均已独立致因。",
        [candidate("API42", "1.2.6", "PARTIAL", "新增UB预算项可形成容量边界设计，但完整tiling门槛待核。",
                   [(S, "测试x_shape可配且CountMaxDim受输入派生维度影响。"),
                    (U, "预算增量明确；完整常量及shape->ubFactor映射未在选段还原。")],
                   [(NT, "存在可配shape。")]),
         candidate("V4", "buffer_fit", "APPLICABLE", "新缓冲字节公式和host预算共改直接支持容量关系测试。",
                   [(S, "shape变化影响UbFactorDimx，代码有明确UB空间预算。")],
                   [(U, "未核实际可用UB/构建/最大可达shape；记录容量不确定性。")])],
        design("NEEDS_FACTS", [
            variable("x_shape", "INPUT", "输入行数与宽度", [[2, 192], [4, 192], [8, 384], [4608, 2048]]),
            variable("UbFactorDimx,blockCount,scaleBuf bytes", "DERIVED", "按BLOCK_ELEM上取整后的广播存储需求", ["r=1,BLOCK_ELEM-1,BLOCK_ELEM,BLOCK_ELEM+1的可达tile", "bytes=ceil(r/B)*B*B*4"], "外部shape到tile r及B定义待核"),
            variable("allocation intervals/lifetime", "DERIVED", "outLocal/scaleBuf/其它UB区间与有效期", ["记录全部分配区间和最大同时存活量"], "完整分配列表与旧outLocal类型/容量未读全"),
            variable("isolated changes", "EXECUTION_PROTOCOL", "区分共改项", ["旧版", "仅步长修正", "仅广播区修正及匹配预算", "完整PR"] )],
            "Init的scaleBuf_分配、DynamicQuant的Brcb->Copy->FreeTensor、CountMaxDim的预算。",
            "逐行scale展开参考与内存区间基线；使用固定实际q使reduce步长不敏感作为广播对照。",
            "广播每行副本来自本行scale；写范围在分配内，无别名覆盖；总同时存活字节<=可用UB。",
            "可离线校核公式与区间；需要完整分配信息才能审预算闭合，设备检测未执行。",
            ["完整outLocal旧容量/类型及全部UB分配", "Brcb与Copy的精确写/读范围合同", "同PR步长改动的独立效应"]),
        ["观察到新临时区与预算共改；不把代码增加buffer直接当作已证明旧buffer越界。"]),

    case(
        "RC-030", "RC-030:megamoe-shared-row-stride", "MegaMoe复用区的行槽跨度一致",
        "8752的A2 W4A8路径为GMM1输入和SwiGLU/GMM2输入复用工作区；把GMM1行跨度从k改为max(k,k2)，并让预处理、专家组偏移及收发目标偏移使用此跨度。逻辑行宽与物理行槽不能混用。",
        "同一复用区各消费者及其地址生成方必须同意物理行跨度，跨度覆盖复用布局需求；GMM2保持native packed k2布局，不可把所有消费者一律改max。",
        "layoutA1RowStride=isW4A8?max(k_,k2):k_；从layoutA.stride(0)记录gmmA1PreRowStride；预处理processIndex*aStride、低半写偏移aStride/2、group/rowStart目标偏移同步更新。",
        ["GC-cann-ops-transformer-8752"],
        [locator("GC-cann-ops-transformer-8752", "evidence/side/cann__ops-transformer__8752.diff", "isW4A8 ? static_cast<uint32_t>(k_ > k2 ? k_ : k2) : static_cast<uint32_t>(k_);", "W4A8物理行跨度选择"),
         locator("GC-cann-ops-transformer-8752", "evidence/side/cann__ops-transformer__8752.diff", "const uint64_t relStartAddr = processIndex * aStride;", "预处理行偏移"),
         locator("GC-cann-ops-transformer-8752", "evidence/side/cann__ops-transformer__8752.diff", "gmGroupOffsetA += static_cast<int64_t>(inGroupProblemShape.m()) * params.gmmA1PreRowStride;", "组间偏移"),
         locator("GC-cann-ops-transformer-8752", "evidence/side/cann__ops-transformer__8752.diff", "gmA1I4_I8[absStartAddr + aStride / 2]", "低半存储偏移")],
        ["M015", "M024", "M004"],
        "容量覆盖、排布及偏移可与M015/M024/M004比较；这是MegaMoe A2 W4A8行槽复用问题，与12123的DynamicQuant reduce步长/广播区分别建卡，不能因同属RC-030或SwiGLU而合并。本patch是arch22两文件，不外推A3布局。",
        [candidate("API42", "1.2.6", "PARTIAL", "k与k2关系可区分物理跨度，但完整外部shape/模式到该分支的映射待核。",
                   [(S, "problemShape.k、k2、m是张量问题规模。"),
                    (U, "max(k,k2)转折可见；完整k2定义、合法组合与分派常量未读。")],
                   [(NT, "存在可配张量shape。")]),
         candidate("V4", "unequal_axes", "APPLICABLE", "代码明确处理k与k2不等；按合法shape对照大小关系。",
                   [(S, "复用区同时关联k/k2两个宽度，max关系说明实现为不等关系安排跨度。")],
                   [(U, "契约允许的k/k2组合及量化打包对齐限制需核；不承诺任意整数可用。")]),
         candidate("V4", "enum_quant", "PARTIAL", "C1 W4A8明确，C2是否作为目标API模式可选需另核。",
                   [(S, "isW4A8及Int8ToInt4预处理明确存在低位宽载荷。"),
                    (U, "isW4A8到公开API/配置实参的建立过程未读。")],
                   [(NT, "不是固定高精路径。"), (U, "合法实参能否选择该分支未核。")])],
        design("NEEDS_FACTS", [
            variable("m,k,k2,expert分组", "INPUT", "合法模型形状及组大小", ["k<k2敏感", "k=k2基线", "k>k2对照", ">=2行及>=2专家组"], "需k2定义、分组及W4A8对齐合法域"),
            variable("isW4A8/platform", "CONTEXT", "补丁限定A2 W4A8路径", ["arch22 A2 W4A8", "非W4A8对照"], "不把此patch作为A3已核实现"),
            variable("gmmA1PreRowStride", "DERIVED", "由layoutA.stride(0)得到的物理行槽", ["max(k,k2)"], "指针元素单位和packed布局需完整类型"),
            variable("row/expert tags and canaries", "INPUT", "区分未读GMM1行与SwiGLU写入范围", ["每行/专家唯一模式", "区间边界canary"], "canary只能在合同允许的测试分配中设置"),
            variable("workspace trace", "EXECUTION_PROTOCOL", "逐阶段记录地址区间", ["self-rank与remote路径各核", "记录group/rowStart地址与读写完成时点"] )],
            "A2 W4A8 layoutA1->Params.gmmA1PreRowStride->FetchAndPreprocess/SendTokensV3/RecvTokensV3地址链。",
            "不复用的独立区参考或正确packed布局参考；固定k=k2作基线；比较补丁前后。",
            "每个消费者读取本行/本专家数据，无覆盖仍未消费的GMM1行；逐项核row/group偏移与分配末端，不只比最终MoE输出。",
            "可离线建立跨度/区间模型；真实打包字节单位、通信及工作区生命周期需补全，设备未执行。",
            ["k2与dtype/packed布局精确合同", "完整工作区生命周期与容量", "跨rank收发和分组实际可达路径"]),
        ["只将arch22两文件引用hunk作为机理依据。", "代码注释说明预防未读行覆盖，尚无本轮硬件隔离复现。"]),

    case(
        "RC-099", "RC-099:topk-prequant-dtype", "路由权重dtype绑定量化前激活",
        "15018在prepare前保存activation_dtype，传给_select_experts，转换topk_weights时改用该dtype而非可能已量化的hidden_states.dtype。路由权重与承载量化激活的表示不是同一个对象契约。",
        "如果路由权重应跟随模型浮点激活dtype，则必须保存量化前的dtype并传播；不能从prepare后载荷dtype逆推原激活dtype。",
        "forward_impl新增activation_dtype=hidden_states.dtype，_select_experts新增可选参数及fallback，并把to(hidden_states.dtype)改为to(activation_dtype)。",
        ["GH-PR-vllm-project-vllm-ascend-15018"],
        [locator("GH-PR-vllm-project-vllm-ascend-15018", "evidence/decoded/PATCH-RC-099-15018-1.diff", "+        activation_dtype = hidden_states.dtype\n+\n         prepare_output = _EXTRA_CTX.moe_comm_method.prepare(", "prepare前保存dtype，包含相邻调用以区别fallback"),
         locator("GH-PR-vllm-project-vllm-ascend-15018", "evidence/decoded/PATCH-RC-099-15018-1.diff", "topk_weights = topk_weights.to(activation_dtype)", "路由权重dtype消费者"),
         locator("GH-PR-vllm-project-vllm-ascend-15018", "evidence/decoded/PATCH-RC-099-15018-1.diff", "activation_dtype=activation_dtype,", "跨调用传播")],
        ["M030", "M001", "M010"],
        "M030原例是conv2d输入强转FP16；M001是混精计算次序，M010是图Dequantize位置。这里被错误转换的是路由权重，其dtype取值时点来自另一对象；可讨论扩展，不能直接继承三类原例或客户身份。",
        [candidate("API42", "1.C.2", "PARTIAL", "本接口显式activation_dtype是内部方法参数；是否算目标公开API的out dtype开关未证。",
                   [(U, "内部_select_experts参数不是当然的SEM-DTYPE-OUT/SEM-QUANT公开实参。")], [],
                   family_gate="若只调内部mock方法，可作为单元设计；不能因此宣称公开API42控制参数成立。"),
         candidate("V4", "enum_dtype", "APPLICABLE", "浮点激活与量化载荷分离，dtype对照有明确目标。",
                   [(S, "prepare前浮点激活和后量化hidden_states、路由浮点权重形成混合dtype组合。")],
                   [(NT, "不是固定单一精度路径。")])],
        design("DESIGN_READY", [
            variable("original activation dtype", "INPUT", "prepare前模型激活精度", ["float16", "bfloat16", "float32"]),
            variable("prepare result dtype", "INPUT", "单元mock模拟prepare后的载荷", ["float8_e4m3fn", "uint8", "int8"], "模型端具体量化方案的合法组合需单独核；mock不证明端到端可达"),
            variable("activation_dtype", "DERIVED", "prepare前保存并跨调用传递的元数据", ["与original activation dtype相等"]),
            variable("topk weights", "INPUT", "未量化的路由权重", [[0.6, 0.4], [0.25, 0.75]]),
            variable("mock call trace", "EXECUTION_PROTOCOL", "隔离dtype传播与设备计算", ["固定router输出，mock prepare换载荷dtype，捕获_select_experts参数"] )],
            "forward_impl在prepare前取dtype并传给_select_experts；另测activation_dtype=None的fallback。",
            "未量化prepare基线；明确传入浮点activation_dtype的router输出转换参考。",
            "保存与传入的dtype必须相同；输出dtype符合原激活精度，值等于按该dtype舍入后的参考；量化fallback需单独暴露，不能假定已有guard。",
            "离线mock测试设计已可具体化；仓库依赖/实际模型和设备可执行性未验证。",
            ["PR未合入，不能称已上线修复", "可选参数为None且hidden_states已量化时仍fallback量化dtype，补丁本身没有15613白名单", "端到端模型/API合法量化组合"]),
        ["单文件变更hunk，不是完整forward_impl/dispatcher实现。", "15018未合入；作者示例Float8×Bool错误与原周报不是自动同事件。"]),

    case(
        "RC-099", "RC-099:topk-floating-whitelist", "路由权重使用浮点白名单并覆盖第二消费者",
        "15613在routed_experts和grouped_topk_router两处只允许fp32/fp16/bf16跟随hidden_states，其它dtype把topk_weights转float32。它补充int8情况并覆盖另一处路由转换，与15018保存原dtype是不同方案。",
        "浮点路由概率不能继承int8/fp8/packed uint8载荷表示；dtype正确与概率值保持须分别验证。",
        "两处旧dtype跟随逻辑改浮点白名单/float32 fallback；新增六组dtype UT仅assert topk_weights.dtype和topk_ids.dtype，没有assert权重数值或下游算子输出。",
        ["GH-PR-vllm-project-vllm-ascend-15613"],
        [locator("GH-PR-vllm-project-vllm-ascend-15613", "evidence/decoded/PATCH-RC-099-15613-2.diff", "if hidden_states.dtype in (torch.float32, torch.float16, torch.bfloat16):", "routed_experts白名单"),
         locator("GH-PR-vllm-project-vllm-ascend-15613", "evidence/decoded/PATCH-RC-099-15613-3.diff", "topk_weights = topk_weights.to(torch.float32)", "grouped_topk_router fallback"),
         locator("GH-PR-vllm-project-vllm-ascend-15613", "evidence/decoded/PATCH-RC-099-15613-1.diff", "router_weights = torch.tensor([[0.6, 0.4]], dtype=torch.float32)", "UT输入权重"),
         locator("GH-PR-vllm-project-vllm-ascend-15613", "evidence/decoded/PATCH-RC-099-15613-1.diff", "assert topk_weights.dtype == expected_dtype", "UT仅dtype判据")],
        ["M030", "M001"],
        "与M030强转低精最接近，但对象是路由概率且由已量化激活dtype错误控制，非conv2d输入固定FP16；M001的计算次序也不能替代此对象关系。两PR未合入，不能算两次修复验证。",
        [candidate("API42", "1.C.1", "PARTIAL", "量化上下文可见，目标公开接口是否暴露相关量化开关未从这些hunk确认。",
                   [(U, "PR注释列W8A8/MXFP方案，但_select_experts自身没有公开SEM-QUANT实参。")], [],
                   family_gate="须沿公开配置/inputs核量化模式暴露；注释中的方案名不是API实参证明。"),
         candidate("V4", "enum_dtype", "APPLICABLE", "UT精确列出浮点和量化hidden dtype，可独立构造混合类型检查。",
                   [(S, "六组dtype含float32/float16/bfloat16/float8_e4m3fn/int8/uint8。")],
                   [(NT, "显式覆盖低位宽及混合类型。")])],
        design("DESIGN_READY", [
            variable("hidden_dtype", "INPUT", "沿用公开UT六个dtype", ["float32", "float16", "bfloat16", "float8_e4m3fn", "int8", "uint8"]),
            variable("router_weights", "INPUT", "包含0到1非整数，避免全0/1隐藏截断", [[0.6, 0.4], [0.25, 0.75]]),
            variable("expected_dtype", "DERIVED", "浮点三类跟随，否则float32", ["fp32/fp16/bf16原dtype", "其它float32"]),
            variable("two consumers", "EXECUTION_PROTOCOL", "两处路由分别验证，不继承一处UT覆盖", ["_select_experts", "GroupedTopkRouter._compute_routing"], "第二处完整方法及renormalization需读全后接集成测试")],
            "routed_experts的dtype转换及grouped_topk_router的topk后dtype转换，分别记录输出。",
            "固定float32 router输出；非量化dtype按对应dtype舍入的参考；量化hidden对照保持权重float32。",
            "补dtype、逐元素值保持、非零权重不被截断和ids不变断言；分开检查grouped router归一化/缩放，不能将原UT宣称为值保持测试。",
            "离线单元设计可实现；需依赖环境。实际token_dispatch/unpermute合同及设备路径另核，未运行。",
            ["PR未合入", "原UT不验证值、归一化、dispatcher或设备结果", "白名单fallback与15018保留原激活dtype的输出精度策略不同"]),
        ["三个文件完整变更hunk，不是完整路由或下游实现。", "作者报告16 passed/A5验证是来源声明；本轮未执行，不能变成本报告设备验证。"]),

    case(
        "RC-122", "RC-122:rank-preservation", "rank参数不被入口无条件重置",
        "4946删除allreduce_bucket入口的rank=None，使调用者传入的rank不被立即清空。代码只直接证明参数保留；作者正文称原重置导致use_multi_rank_bucket_allreduce=False也不走reduce，完整下游分派不在本patch hunk。",
        "若rank用于选择目标rank/reduce行为，必须将调用者的rank保留到选路消费者；函数缺省rank=None与有参调用后无条件覆盖不是一回事。",
        "allreduce_bucket(self,bucket,rank=None,...)函数签名未改，仅删除函数内第一条rank=None。",
        ["GH-PR-deepspeedai-DeepSpeed-4946"],
        [locator("GH-PR-deepspeedai-DeepSpeed-4946", "evidence/decoded/PATCH-RC-122-4946-1.diff", "def allreduce_bucket(self, bucket, rank=None, log=None, divide=True, process_group=None):", "签名缺省值仍保留"),
         locator("GH-PR-deepspeedai-DeepSpeed-4946", "evidence/decoded/PATCH-RC-122-4946-1.diff", "-        rank = None", "删除无条件覆盖"),
         locator("GH-PR-deepspeedai-DeepSpeed-4946", "evidence/decoded/BODY-RC-122-4946.txt", "it will never use the reduce method even if `use_multi_rank_bucket_allreduce` is set to False.", "作者对下游影响的声明，不能当作此hunk已走读分派")],
        ["M011", "M013", "M028"],
        "M011条件分支可作关系对照，M013是block_dim适配，M028是HCCL/LCCL确定性能力。此处是rank传播，非确定性能力或梯度完成等待；不能与7371双buffer同步合并。",
        [candidate("API42", "1.C.5", "NOT_APPLICABLE", "use_multi_rank_bucket_allreduce选通信实现，不等于deterministic/accumulate或索引控制。",
                   [(N, "本子问题没有SEM-DETERMINISTIC/SEM-INDEX-CTRL的接口实参依据。")], [],
                   family_gate="通信配置不是目标API42该项列出的语义开关，禁止只因有False开关就映射。"),
         candidate("V4", "enum_behavior", "PARTIAL", "可讨论行为选路；C2数值策略API暴露未证，C4正文有配置但完整谓词尚未读。",
                   [(U, "配置是否属于目标API暴露的数值实现选项及其合同未核。"),
                    (U, "正文给use_multi_rank_bucket_allreduce=False，patch仅见rank入口；需调用点及分派体。")],
                   [(U, "合法实参到该实现路径尚未建立。"),
                    (U, "未读完整消费者，不能宣称已识别完整选路条件。")])],
        design("NEEDS_FACTS", [
            variable("rank", "INPUT", "有参目标rank与缺省None", ["None", "0", "另一合法rank"], "合法rank域由process_group决定"),
            variable("use_multi_rank_bucket_allreduce", "CONTEXT", "来源正文中的上层配置", ["False", "True"], "配置到allreduce_bucket调用链未在hunk中"),
            variable("rank at consumer", "DERIVED", "传播后的实际值及选路结果", ["有参保留原值", "缺省仍None"], "真实通信消费者位置需读完整函数"),
            variable("mock communication trace", "EXECUTION_PROTOCOL", "无设备检查传播和选路", ["stub flatten和通信调用，记录调用方法、目标rank及process_group"] )],
            "allreduce_bucket入口到真实reduce/allreduce消费者，补读完整函数后绑定spy。",
            "rank=None基线、有参旧版和新版对照；通信数学参考按每rank固定梯度计算。",
            "有参rank不被入口覆盖；完整函数核实后再断言具体reduce/allreduce分派与各rank结果，不凭标题断言。",
            "参数保留可离线检查；真实分派测试依赖未读函数/调用点，不需要客户事件身份才可继续。",
            ["完整allreduce_bucket函数和配置调用点", "process_group及目标rank合法域", "原周报2025版本身份"]),
        ["patch只有删除一行的hunk；下游影响分别标为作者正文声明。", "这是独立公开技术卡，不能证明RC-122原事件。"]),

    case(
        "RC-122", "RC-122:ipg-buffer-stream-dependency", "IPG双buffer切换前建立stream依赖",
        "7371在reduce_ipg_grads之后、bucket.index双buffer切换之前，针对contiguous_gradients&&overlap_comm且加速器不自动解依赖，新增reduction_stream与current_stream两个方向的wait_stream。",
        "buffer的生产、归约消费及下一次复用必须按实际stream依赖排序；双buffer索引改变本身不代表先前读写已完成。",
        "新增if not resolves_data_dependency及两条wait_stream，保留原bucket.index=1-bucket.index；无rank处理变更。",
        ["GH-PR-deepspeedai-DeepSpeed-7371"],
        [locator("GH-PR-deepspeedai-DeepSpeed-7371", "evidence/decoded/PATCH-RC-122-7371-1.diff", "if self.contiguous_gradients and self.overlap_comm:", "既有双buffer路径门槛"),
         locator("GH-PR-deepspeedai-DeepSpeed-7371", "evidence/decoded/PATCH-RC-122-7371-1.diff", "if not get_accelerator().resolves_data_dependency():", "新增能力门槛"),
         locator("GH-PR-deepspeedai-DeepSpeed-7371", "evidence/decoded/PATCH-RC-122-7371-1.diff", "self.reduction_stream.wait_stream(get_accelerator().current_stream())", "第一方向依赖"),
         locator("GH-PR-deepspeedai-DeepSpeed-7371", "evidence/decoded/PATCH-RC-122-7371-1.diff", "get_accelerator().current_stream().wait_stream(self.reduction_stream)", "第二方向依赖")],
        ["M007", "M015"],
        "M007原例多核同时搬运，当前是框架current/reduction两stream和IPG双buffer复用；参与者和生存期边界须明确。M015覆盖只是可能后果。4946参数选路与本同步问题单独建卡，不由相同RC-122来源合并。",
        [candidate("API42", "1.C.5", "NOT_APPLICABLE", "overlap_comm/contiguous_gradients和stream协议并非原deterministic/accumulate项。",
                   [(N, "未见SEM-DETERMINISTIC/SEM-INDEX-CTRL接口依据。")], [],
                   family_gate="执行协议不伪装成原42的输入开关。"),
         candidate("V4", "enum_behavior", "PARTIAL", "C4显式模式门槛可核；C2数值实现API选项未证，分别评估。",
                   [(U, "overlap/contiguous是框架调度配置，是否符合C2数值实现API参数须独立限定。"),
                    (S, "hunk有contiguous_gradients&&overlap_comm及能力门槛，能识别该模式路径。")],
                   [(U, "不能把执行协议自动当成数值策略API选项。"),
                    (NT, "存在可见模式选择门槛。")])],
        design("DESIGN_READY", [
            variable("contiguous_gradients,overlap_comm", "CONTEXT", "框架调度配置", ["四种布尔组合"]),
            variable("resolves_data_dependency", "CONTEXT", "加速器自动依赖能力", ["mock True", "mock False"], "真实设备能力由后端报告，禁止为制造路径伪造设备事实"),
            variable("bucket.index", "DERIVED", "双buffer当前槽", ["0->1", "1->0"]),
            variable("stream schedule", "EXECUTION_PROTOCOL", "显式记录两个wait及换槽时序", ["mock stream调用顺序", "真实后端多次bucket复用，生产/归约有可控延迟"], "真实竞态压力与数值验证另需设备"),
            variable("gradient values", "INPUT", "各轮/各rank独特有限值", ["不同轮次/参数块标记，防旧槽数据恰好相同"] )],
            "reduce_independent_p_g_buckets_and_remove_grads中reduce_ipg_grads后、bucket.index切换前的条件块。",
            "mock协议以补丁控制流为基线；硬件数值另用overlap=False串行归约及高精梯度参考。",
            "满足门槛时两条依赖各执行一次且先于换槽；其它配置不执行新增wait。真实复用时每轮结果对应本轮梯度，稳定性与正确性分别检查。",
            "八种配置mock协议设计可直接具体化；设备并发/数值复现未执行、后端能力未知。",
            ["完整IPG buffer生产/消费生命周期", "真实后端能力与stream语义", "作者报告loss恢复不是本轮设备验证，原2025事件仍未知"]),
        ["完整返回hunk不是完整梯度同步实现；双向wait代码事实不单独隔离哪条缺失造成作者现象。"]),

    case(
        "RC-031", "RC-031:rope-position-read-carrier", "RoPE位置从UB元素提取改为GM标量读",
        "16699删除positions的向量tl.load和get_element(x,(i,))，内循环直接tl.load positions_gm_ptr+min(row,last_row)。代码确认位置读取载体及地址边界变化；UB传输竞争/旧轮位置是作者解释，未由本轮硬件隔离。",
        "每个有效token的Q/K旋转必须消费其自身position对应的sin/cos；尾部无效行读取须落在合法存储范围且不影响有效行。稳定输出与正确位置绑定是两个判据。",
        "新增last_row=input_batch_offset_end-1；内层pos按clamped row从GM标量读取；去掉get_element导入并新增nightly测试调度。",
        ["GH-PR-vllm-project-vllm-ascend-16699"],
        [locator("GH-PR-vllm-project-vllm-ascend-16699", "evidence/decoded/PATCH-RC-031-16699-1.diff", "-            pos = get_element(x, (i,))", "旧UB元素提取"),
         locator("GH-PR-vllm-project-vllm-ascend-16699", "evidence/decoded/PATCH-RC-031-16699-1.diff", "pos = tl.load(positions_gm_ptr + min(input_batch_offset + pos_offset + i, last_row))", "新GM标量读取与clamp"),
         locator("GH-PR-vllm-project-vllm-ascend-16699", "evidence/decoded/PATCH-RC-031-16699-1.diff", "last_row = input_batch_offset_end - 1", "末有效行边界")],
        ["M007", "M015", "M004"],
        "M007缺同步最接近作者race解释，但本轮只核载体替换；M015内存覆盖与M004 window偏移未由此成立。保留位置对象绑定、读取载体和时序三个层次；不能把GM读替换等同于已证旧UB竞争。",
        [candidate("API42", "1.6.1", "APPLICABLE", "kernel以batch_size和token行分批，可做多行对照。",
                   [(S, "input_batch_offset/batch_size及token行维在hunk明确存在。")],
                   [(NT, "不是无batch的标量核。")]),
         candidate("V4", "nondegenerate", "APPLICABLE", "外层iter和pos_offset明确存在，适合一轮/多轮和末轮对照。",
                   [(S, "iter_num_per_vec与batch_size_per_iter_per_vec决定多轮处理。")],
                   [(NT, "有随输入规模变化的轮次。")]),
         candidate("V4", "index_edge", "APPLICABLE", "positions与末行clamp有显式端点映射。",
                   [(S, "读取地址显式min(row,last_row)，且用position索引cos/sin缓存。")],
                   [(NT, "存在明确有效域和端点映射。")])],
        design("DESIGN_READY", [
            variable("num_tokens,q_heads,kv_heads,head_dim", "INPUT", "沿作者给出的有限、可复核规模", ["num_tokens=1,16,257,1024", "heads=(12,1),(64,4)", "head_dim=128/full RoPE"], "这些是作者报告参数；需目标测试合同/后端支持，未声称设备已可运行"),
            variable("positions", "INPUT", "每行不同的合法位置，增强错行可辨性", ["position[t]=t且cache足够", "全相同position阴性对照"]),
            variable("iter_num_per_vec,last_row", "DERIVED", "实际轮次和末行边界", ["记录1轮及>1轮，末轮不足整块"], "确切轮次须运行元数据或完整编译公式确认"),
            variable("repeat protocol", "EXECUTION_PROTOCOL", "固定相同输入反复调用", ["24次重复", "每轮分别做FP32参考，不能只比重复一致性"] )],
            "split_qkv_rmsnorm_rope_kernel的position读取及cos_sin_cache取值；覆盖有效行、尾部mask和多轮。",
            "按每行实际position构造FP32 Q/K RoPE参考，V作为不旋转对照；同位置阴性组与逐行不同位置组。",
            "逐行Q/K与参考比较，同时查前一token位置误配；按作者测试候选atol=5e-2并先核合同；24次稳定性另外计数，V正确不能替代Q/K正确。",
            "测试输入和判据可具体化；设备/backend及编译路径未验证，作者数值结果只作来源声明。",
            ["完整tail/mask处理与batch_size>=1合同", "UB race需要传输依赖隔离，不能由替换本身确认", "旧/新版本与原客户事件身份"]),
        ["两个文件变更hunk；作者测试正文不能当成已读取完整nightly测试函数。", "新增CI调度只证明调度变更，不证明CI已运行或通过。"]),
]


# Each association is reviewed at its own original mount.  An observed source
# predicate is not an observed device execution, and a proposed stress test is
# never promoted to a positive condition association.  These records are about
# the public technical case, not the weekly event carrying the same task ID.
def association(basis, status, reason, *, requires_unknown=False, skip_unknown=False,
                branch_hint=None):
    return dict(association_basis=basis, semantic_applicability=status, reason=reason,
                requires_unknown=requires_unknown, skip_unknown=skip_unknown,
                execution_branch_hint=branch_hint)


_ASSOCIATION_REVIEWS = {
    ("RC-002:gemm-precision-flag", "API42", "1.C.3", "1.C"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "host代码确实使用cubeMathType计算标志；选段未含API/schema签名及合法枚举，因此只确认该计算模式量的结构关联，公开控制实参暴露仍待核。", requires_unknown=True),
    ("RC-002:gemm-precision-flag", "API42", "1.7.6", "1.7"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "补丁只显示精度标志计算和传参，未显示触发大值、内部溢出值或GEMM中间计算精度。大值/缩放分布仅是拟议敏感测试，不能成为此技术卡已见1.7.6的正向关联。"),
    ("RC-002:gemm-precision-flag", "V4", "enum_compute", "C1"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "NeedEnableFp32Output显式读取输入与output dtype，支持审混合精度选择关系；完整定义和合法dtype组合未见，不能称某个16in32out输入已构造或已命中。", requires_unknown=True),
    ("RC-002:gemm-precision-flag", "V4", "enum_compute", "C2"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "cubeMathType在host调用链明确参与计算模式判定；其API/schema暴露和完整模式到消费者合同仍未知，不继承C1的dtype事实。", requires_unknown=True, skip_unknown=True),
    ("RC-002:gemm-precision-flag", "V4", "intermediate_overflow", "N4"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "矩阵乘加允许设计量级差异分布，但该hunk没有实际幅值、抵消或溢出中间量。N4敏感数据属于proposed_design，不能写成源码已观察的触发条件。"),

    ("RC-024:topk-workspace-contract", "API42", "1.2.6", "1.2"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "190KiB扣减与maxTopkBase是容量/分块公式，并未给出完整模板选择边界。围绕容量构造shape不能直接满足1.2.6从src读模板边界的要求；此方向仅拟测。"),
    ("RC-024:topk-workspace-contract", "API42", "1.3.2", "1.3"):
        association("STRUCTURAL_APPLICABILITY", "NOT_APPLICABLE",
                    "本子问题限定普通TopK问题规模与临时区容量，既无可控索引/窗映射实参又无窄整型offset溢出公式；按原1.3硬限制排除，索引输出不替代索引输入。"),
    ("RC-024:topk-workspace-contract", "V4", "buffer_fit", "S2"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "API需求字节、190KiB扣减、GetWithOffset分配三者在源码可逐项对应，直接构成容量规划关系。未知的是合法规模映射和可达容量，不是由NaN症状推得S2。"),

    ("RC-029:vscale-call-binding", "API42", "1.C.1", "1.C"):
        association("UNKNOWN", "UNKNOWN",
                    "kernel中的scale实参不等于schema暴露SEM-QUANT；同PR测试虽有quant_mode参数，但尚无测试到该kernel调用的完整绑定。原42量化control关联未建立。", requires_unknown=True),
    ("RC-029:vscale-call-binding", "V4", "enum_quant", "C1"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "同PR测试显式定义float8_e4m3fn及query/key/value dtype，支持量化载荷的结构语境；仍缺该测试实参到四处FlashUpdate调用的分派对应。不是仅由scale命名推C1。"),
    ("RC-029:vscale-call-binding", "V4", "enum_quant", "C2"):
        association("UNKNOWN", "UNKNOWN",
                    "量化载荷/scale读取不证明数值策略作为目标API实参暴露；完整quant_mode合法域和到此kernel的分派尚未核实。", requires_unknown=True, skip_unknown=True),
    ("RC-029:vscale-call-binding", "V4", "scale_structure", "S7"):
        association("UNKNOWN", "UNKNOWN",
                    "相邻GM下标及末参替换可定位，但两个标量与载荷轴、辅助shape和广播关系未建立；scale一词不满足S7。", requires_unknown=True, skip_unknown=True),
    ("RC-029:vscale-call-binding", "V4", "nondegenerate", "S9"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "runInfo.isLastS2Loop及s2Idx==s2BaseSize是代码可见的S2轮次条件，支持一轮/多轮对照；未据此声称某次输入已运行多轮。"),

    ("RC-030:dequant-reduction-stride", "API42", "1.2.2", "1.2"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "拟对派生q的64对齐关系采样；新增输入192本身可被64整除，真实q及外部shape映射未知。不能把测试名misaligned或内部除法改动当成已观察的API输入尾块不对齐。"),
    ("RC-030:dequant-reduction-stride", "API42", "1.3.2", "1.3"):
        association("STRUCTURAL_APPLICABILITY", "NOT_APPLICABLE",
                    "本问题是派生步长整数换算，设计只有普通数据shape；没有原1.3所要求的索引映射实参或>uint16/int32的offset边界。"),
    ("RC-030:dequant-reduction-stride", "V4", "tile_shape", "S5"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "UbFactorDimy和reduce块步长换算是可定位的内部tile结构，支持审S5；实际q、完整tiling边界及合法外部shape对应仍未取得，不能称已观察尾块触发。"),
    ("RC-030:dequant-reduction-stride", "V4", "tile_shape", "C4"):
        association("UNKNOWN", "UNKNOWN",
                    "reduce指令的步长改变不等于输入到模板分派的完整谓词；选段未还原该谓词，不能继承同一construction下S5的结构事实。", requires_unknown=True, skip_unknown=True),
    ("RC-030:dequant-broadcast-storage", "API42", "1.2.6", "1.2"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "新缓冲预算可用于容量压力设计，但未读到API shape驱动模板选择的完整边界。容量两侧采样不能自动变成原1.2.6模板边界事实。"),
    ("RC-030:dequant-broadcast-storage", "V4", "buffer_fit", "S2"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "新增scaleBuf字节公式、Brcb/Copy读写对象和host预算项同时可见，直接支持容量一致性审读；旧区实际越界与具体触发shape仍待验证。"),
    ("RC-030:megamoe-shared-row-stride", "API42", "1.2.6", "1.2"):
        association("PROPOSED_TEST_ONLY", "UNKNOWN",
                    "max(k,k2)是复用行槽跨度选择，未证明它是原1.2.6要求的tiling模板选择边界。k<k2/k=k2/k>k2仅保留为跨度机理测试。"),
    ("RC-030:megamoe-shared-row-stride", "V4", "unequal_axes", "S3"):
        association("STRUCTURAL_APPLICABILITY", "PARTIAL",
                    "代码明确比较k/k2并取max，两个宽度的关系直接影响物理行槽；合法外部shape是否可独立改变两轴以及打包对齐域仍待合同，故不声称任意不等组合可构造。"),
    ("RC-030:megamoe-shared-row-stride", "V4", "enum_quant", "C1"):
        association("OBSERVED_CONDITION", "APPLICABLE",
                    "isW4A8条件块及FetchAndPreprocessInt8ToInt4/Cast低四位处理在变更hunk可见，低位宽载荷关系有代码依据；这不同时证明C2的公开量化模式控制。"),
    ("RC-030:megamoe-shared-row-stride", "V4", "enum_quant", "C2"):
        association("UNKNOWN", "UNKNOWN",
                    "isW4A8是内部路径量；其从公开API/config合法实参建立的过程未读，内部bool不自动成为C2输入control。", requires_unknown=True, skip_unknown=True),

    ("RC-099:topk-prequant-dtype", "API42", "1.C.2", "1.C"):
        association("UNKNOWN", "UNKNOWN",
                    "activation_dtype是内部_select_experts参数，topk_weights是内部结果；未证明schema向用户暴露SEM-DTYPE-OUT/SEM-QUANT，故不能把内部dtype转换映射为原42输出dtype开关。", requires_unknown=True),
    ("RC-099:topk-prequant-dtype", "V4", "enum_dtype", "C1"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "prepare前保存dtype并传给权重转换的代码链可见，支持原激活dtype与量化载荷dtype分离的类型关系审读；具体量化prepare函数未读全，不宣称每种模型组合均可达。"),
    ("RC-099:topk-floating-whitelist", "API42", "1.C.1", "1.C"):
        association("UNKNOWN", "UNKNOWN",
                    "内部权重dtype白名单和注释所列量化方案，未给出目标公开schema的SEM-QUANT实参；UT传hidden_dtype也不是量化control开关。", requires_unknown=True),
    ("RC-099:topk-floating-whitelist", "V4", "enum_dtype", "C1"):
        association("OBSERVED_CONDITION", "APPLICABLE",
                    "新增UT明确列六组hidden_dtype/expected_dtype并调用_select_experts，代码有浮点白名单/float32 fallback。只观察测试构造与dtype断言，未观察值保持或设备执行。"),

    ("RC-122:rank-preservation", "API42", "1.C.5", "1.C"):
        association("STRUCTURAL_APPLICABILITY", "NOT_APPLICABLE",
                    "rank及通信实现配置不属于原42该项的deterministic/accumulate或索引控制语义；删除rank=None不建立该项。"),
    ("RC-122:rank-preservation", "V4", "enum_behavior", "C2"):
        association("UNKNOWN", "UNKNOWN",
                    "allreduce_bucket的rank参数保留不证明目标数值策略作为API选项暴露；需公开合同和完整调用链，不能由False配置推C2。", requires_unknown=True, skip_unknown=True),
    ("RC-122:rank-preservation", "V4", "enum_behavior", "C4"):
        association("UNKNOWN", "UNKNOWN",
                    "作者正文提通信配置，hunk仅删rank覆盖。未取得合法输入到reduce/allreduce分派的完整谓词；配置只能作为Branch3执行上下文线索，不能充当C4输入条件。", requires_unknown=True, skip_unknown=True,
                    branch_hint="Branch3: configuration/communication context; no input-driven condition established"),
    ("RC-122:ipg-buffer-stream-dependency", "API42", "1.C.5", "1.C"):
        association("STRUCTURAL_APPLICABILITY", "NOT_APPLICABLE",
                    "contiguous/overlap及stream依赖是框架调度协议，未见原42此项要求的deterministic/accumulate输入语义。"),
    ("RC-122:ipg-buffer-stream-dependency", "V4", "enum_behavior", "C2"):
        association("UNKNOWN", "UNKNOWN",
                    "调度配置和加速器能力分支不是已证明的数值策略API实参，C2条件关系未建立。", requires_unknown=True, skip_unknown=True,
                    branch_hint="Branch3: stream protocol and accelerator capability"),
    ("RC-122:ipg-buffer-stream-dependency", "V4", "enum_behavior", "C4"):
        association("UNKNOWN", "UNKNOWN",
                    "contiguous_gradients&&overlap_comm&&not resolves_data_dependency是可见执行门槛，但只是Branch3配置/能力上下文。没有输入驱动分派谓词或目标接口行为模式合同，不能映射成C4正向条件。", requires_unknown=True, skip_unknown=True,
                    branch_hint="Branch3: stream protocol and accelerator capability; not an input condition"),

    ("RC-031:rope-position-read-carrier", "API42", "1.6.1", "1.6"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "kernel的batch_size、input_batch_offset和token行映射明确存在，可独立审多行规模条件；不把来源报告的257/1024当本轮已执行输入。"),
    ("RC-031:rope-position-read-carrier", "V4", "nondegenerate", "S9"):
        association("STRUCTURAL_APPLICABILITY", "APPLICABLE",
                    "外层iter_num_per_vec、pos_offset和末批边界在代码明确，构成规模到多轮处理的结构关系；具体阈值和竞态仍待实际路径确认。"),
    ("RC-031:rope-position-read-carrier", "V4", "index_edge", "I2"):
        association("OBSERVED_CONDITION", "APPLICABLE",
                    "GM读取地址使用min(row,last_row)，last_row由有效batch末端-1计算，端点映射有直接代码依据；实际尾部输入与所有mask合同尚未执行验证。"),
}


def _review_association(card, condition):
    key = (card["issue_key"], condition["system"], condition["condition_id"], condition["class_id"])
    review = _ASSOCIATION_REVIEWS[key]  # No keyword-based/default association.
    condition["initial_candidate_reason"] = condition["reason"]
    condition["association_basis"] = review["association_basis"]
    condition["association_scope"] = "SOURCE_LEVEL_NO_EXECUTION; INDEPENDENT_PUBLIC_TECHNICAL_CASE"
    condition["reason"] = review["reason"]
    condition["semantic_applicability"] = review["semantic_applicability"]
    if review["execution_branch_hint"]:
        condition["execution_branch_hint"] = review["execution_branch_hint"]
    for flag, field in [("requires_unknown", "requires_check"), ("skip_unknown", "skip_if_check")]:
        if review[flag]:
            for check in condition[field]:
                check["status"] = U
                check["reason"] = review["reason"]
    for assessment in condition["class_assessments"]:
        assessment["semantic_applicability"] = condition["semantic_applicability"]
        assessment["requires_check"] = deepcopy(condition["requires_check"])
        assessment["skip_if_check"] = deepcopy(condition["skip_if_check"])
    return condition


def _flatten_predicates(items):
    result = []
    for item in items:
        if isinstance(item, dict):
            result.extend((item.get("class_id"), text) for text in item.get("conditions", []))
        else:
            result.append((None, item))
    return result


def _bind_checks(original, notes, issue_key, axis):
    predicates = _flatten_predicates(original)
    if len(predicates) != len(notes):
        raise ValueError(f"{issue_key}: {axis} needs {len(predicates)} exact checks, got {len(notes)}")
    return [dict(class_id=mount, predicate=predicate, status=note[0], reason=note[1])
            for (mount, predicate), note in zip(predicates, notes)]


def mechanism_cases(definitions=None, mode_index=None):
    """Return the pilot cards bound to exact R3 definitions, without mutation.

    Optional ``definitions`` accepts the frozen definitions document, its list,
    or an index keyed by (system, condition_id). ``mode_index`` accepts the
    original30 document, list, or index. Missing predicates fail closed instead
    of silently dropping an original Requires/Skip clause.
    """
    if definitions is None:
        definitions = json.loads((R3 / "condition_definitions.json").read_text(encoding="utf-8"))
    if isinstance(definitions, dict) and "definitions" in definitions:
        definitions = definitions["definitions"]
    if isinstance(definitions, list):
        definitions = {(d["system"], d["condition_id"]): d for d in definitions}
    if mode_index is None:
        mode_index = json.loads((R3 / "baseline_30_index.json").read_text(encoding="utf-8"))
    if isinstance(mode_index, dict) and "modes" in mode_index:
        mode_index = mode_index["modes"]
    if isinstance(mode_index, list):
        mode_index = {m["mode_id"]: m for m in mode_index}
    result = deepcopy(_CASES)
    for card in result:
        card["original30"]["similar_modes"] = [
            dict(mode_id=mid, name=mode_index[mid]["name"],
                 original_definition=mode_index[mid]["original_definition"])
            for mid in card["original30"]["similar_mode_ids"]]
        bound_conditions = []
        for c in card["candidate_conditions"]:
            d = definitions[(c["system"], c["condition_id"])]
            c["original_definition"] = deepcopy(d)
            c["requires_check"] = _bind_checks(d["requires"], c.pop("_requires_notes"), card["issue_key"], "requires")
            c["skip_if_check"] = _bind_checks(d["skip_if"], c.pop("_skip_notes"), card["issue_key"], "skip_if")
            c["class_assessments"] = []
            selected_mounts = c["reviewed_class_ids"] if c["system"] == "V4" else d["class_ids"]
            for mount in selected_mounts:
                if mount not in d["class_ids"]:
                    raise ValueError(f"{card['issue_key']}: unrecognized original mount {mount}")
                rq = [x for x in c["requires_check"] if x["class_id"] in (None, mount)]
                sk = [x for x in c["skip_if_check"] if x["class_id"] in (None, mount)]
                if any(x["status"] == N for x in rq) or any(x["status"] == T for x in sk):
                    status = "NOT_APPLICABLE"
                elif any(x["status"] == U for x in rq + sk):
                    status = "PARTIAL" if any(x["status"] == S for x in rq) else "UNKNOWN"
                else:
                    status = "APPLICABLE"
                c["class_assessments"].append(dict(class_id=mount, semantic_applicability=status,
                                                   requires_check=deepcopy(rq), skip_if_check=deepcopy(sk)))
            c["classification_scope"] = "INDEPENDENT_PUBLIC_TECHNICAL_CASE_ONLY"
            c["construction_feasibility"] = "SEE_PROPOSED_DESIGN"
            if c["system"] == "V4":
                for assessment in c["class_assessments"]:
                    mounted = deepcopy(c)
                    mounted["class_id"] = assessment["class_id"]
                    mounted["requires_check"] = assessment["requires_check"]
                    mounted["skip_if_check"] = assessment["skip_if_check"]
                    mounted["class_assessments"] = [deepcopy(assessment)]
                    # Resource limits affect feasibility, not whether a shape
                    # or dtype relation is expressible. Preserve the authored
                    # semantic decision for a single reviewed mount.
                    if len(selected_mounts) > 1:
                        mounted["semantic_applicability"] = assessment["semantic_applicability"]
                    else:
                        mounted["class_assessments"][0]["semantic_applicability"] = mounted["semantic_applicability"]
                    bound_conditions.append(_review_association(card, mounted))
            else:
                c["class_id"] = d["class_ids"][0]
                bound_conditions.append(_review_association(card, c))
        card["candidate_conditions"] = bound_conditions
    return result


# Convenient immutable-source snapshot for report generators. Call the function
# when an independent copy is needed; consumers should not mutate this list.
CASES = mechanism_cases()
