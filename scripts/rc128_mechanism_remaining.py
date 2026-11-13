"""Manually adjudicated test directions for the remaining frozen R3 records.

This module is a review draft, not a root-cause classifier or test executor.
Each entry below was written against its particular weekly claim and the R3
relations/source audit. Helpers only attach that review to the frozen evidence.
Public findings remain independent observations; they never become weekly facts.
No ACCEPT, knowledge-base write, generated tensor, or production change occurs.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


EXCLUDED_TASK_IDS = frozenset(f"RC-{n:03}" for n in (2, 24, 29, 30, 31, 99, 122))
R3 = Path(__file__).resolve().parents[1] / "reports" / "archive" / "rc128-evidence-review-20261112-r3"


def p(reference, checks, path, conditions="", scope="SPECIFIC_TEST_DIRECTION"):
    """A literal, case-specific plan. The condition tokens are explicit choices."""
    return dict(reference=reference, checks=checks.split("；"), path_to_verify=path,
                condition_tokens=conditions.split(), analysis_scope=scope)


# Number and order follow the R3 failure relations. There is intentionally no
# keyword inference, contract-to-condition lookup, or default test parameter.
PLANS = {
 1: [
  p("同一输入/权重的高精RMSNorm数学参考；两侧真实dtype链", "分别保存归一化结果、权重乘积与回转值；比较先升FP32再乘和低精乘后回转，逐阶段判误差；340个回答的差异仅作模型指标", "ATB rms_norm→权重乘法→后续层；提升位置待查", "V4:enum_dtype:C1"),
  p("transformers与MindIE对应版本的RoPE定义", "固定位置、旋转维度与sin/cos，逐项核对pair/interleave及旋转公式；排除RMSNorm差异后单独比较RoPE输出", "位置与sin/cos生产→apply_rotary_pos_emb→attention；真实布局待查")],
 3: [p("相同请求配置下逐token轨迹，而非仅最终回答", "记录100并发请求的请求身份、token输入、seed与前序状态；从5–7条复读请求找第一处分歧，再确认实际算子", "服务调度→各请求prefill/decode→首个分歧消费者未知", scope="FACT_COLLECTION_ONLY")],
 4: [p("Ring-1T合法推理输入和有限输出要求待提供", "保存首次NaN的调用链和输入；先确定是有限输入产生NaN还是上游已有非法值；未给算子与实参前不生成NaN/Inf输入", "vLLM整网→首个NaN消费者未知", scope="FACT_COLLECTION_ONLY")],
 5: [p("相同模型/请求在短时与长稳服务中的参考", "补模型与实际异常指标；记录失效前请求历史和复现时长；定位最早状态/数值分歧后才设计算子参数", "服务请求历史→失效调用；模型及消费者未知", scope="FACT_COLLECTION_ONLY")],
 6: [p("同一RMSNorm调用的数学参考及输出dtype合同", "将to(x.dtype)、去patch、dump级别各自单因素对照；保留原始输出dtype和首个NaN位置；分别检查数值变化与stream依赖，不用dump治愈直接证明竞争", "npu_rms_norm→后续反向梯度→grad norm；首错边待查", "V4:enum_dtype:C1")],
 7: [p("实际attention输入的高精前/反向及已约定单算子容差", "分别替换低精前向和反向，记录局部误差及训练loss；对8k/128k/256k分别取真实shape，检查长归约路径而非假设误差随长度单调；区分单算子达标与模型累计误差", "attention前反向→训练多步loss；累积误差消费者待定位", "API42:1.5.2 V4:enum_dtype:C1 V4:long_reduce:S9")],
 8: [p("训练FA同输入与修复前后.o的依赖图", "标出数据搬运写完与训练FA计算读取之间的具体event/wait；确认80卡首步相同输入/权重；核对.o替换前后首错和loss，推理FIA的PIPE_M补丁独立保留", "训练FA搬运生产者→计算消费者；实际流水边待查")],
 9: [p("相同逻辑输入的独立新缓存执行", "按非连续→连续、连续→非连续及各自冷启动比较；保存shape/stride、缓存key、命中tiling和实际内核；若仅复用后错，核对缓存等价类遗漏而非把布局本身判非法", "前次rmsnorm建立tiling缓存→当前命中→内核消费", "API42:1.4.1 V4:view_stride:T1")],
 10: [p("TPipe构造有无及指定ctrl位的架构/模板合同", "核对去TPipe前后构造副作用与ctrl初始/期望值；对同histc实参检查状态设置、消费与复位顺序；bincount仅作规避对照，不据此断言计数数学错误", "模板初始化→ctrl寄存器→histc或同模板算子；具体bit待查")],
 11: [p("equal的逐元素布尔语义和上游算子各自容差", "恢复缺失的equal输入并量化约1%相对误差对比较结果的影响；依次固定conv/maxpool/relu/softmax输入找首错；已换卡解决的偶现不一致另查设备，不能并作equal精度原因", "上游conv/maxpool/relu/softmax→equal→模型输出；具体首错待查")],
 12: [p("同Prefill请求关闭/开启负载均衡后的等价通信分片", "记录alltoall发送/接收分片及GMM实际输入，先找首个不等价对象；分别固定userconf和boot配置；确认B020/B050调用差别，不以版本名直接推构建变体", "Prefill负载均衡→alltoall→GMM→token；分片映射待查")],
 13: [p("相同脚本/数据集的GPU与NPU浮点基线，再作量化对照", "先对齐modetest和客户脚本的样本、token与评分；固定BF16基线后比较w8a16的实际载荷/scale和首错；0.55与0.87不作为单算子误差", "评测脚本→浮点模型→量化模型；具体量化消费者未知", "V4:enum_dtype:C1 V4:enum_quant:C1")],
 14: [p("310B实际SDPA调用的高精attention分阶段参考", "保存已对齐SDPA输入及内部QK/softmax/AV；以完全相同实参单独复现可疑matmul；先核310B此路径支持的dtype与接口，再定容差", "SDPA输入→内部matmul/softmax→输出；matmul根因仍是假设")],
 15: [p("B030/B050相同AIME样本与评测协议", "锁定权重、采样、并行及评分脚本，保存80.00/66.67对应回答；二分到首个行为变化提交再抽取算子；未定位前不构造算子shape", "MindIE版本→评测回答；首错调用未知", scope="FACT_COLLECTION_ONLY")],
 16: [p("Lmhead相同输入/权重的高精矩阵参考", "同时报告绝对/相对/ULP误差与输入微差；将两侧实际Lmhead输入互换，区分上游微差和当前计算；B070/B080同实参选路待核，不借mlir/ReduceSum工单归因", "上游hidden→Lmhead→logits→模型评分")],
 17: [p("exponential_规定分布、参数及采样器的统计合同", "固定分布参数，比较CPU/NPU样本统计而非要求逐点相同；保持temperature=1其余配置一致，对照替换随机源后的评分；另测生成完成到采样消费的流依赖，区分质量和同步", "Tensor.exponential_→temperature采样→回答/评分；随机状态与流待查")],
 18: [p("271条固定样本的归约数值与整体评分两层参考", "记录HCCL_DETERMINISTIC环境配置实际生效与归约后端；比较同输入多次归约的首处分歧及评分分布；0.424接近不当逐bit相同，也不自动分配API deterministic条件", "HCCL归约→模型logits→271条评分；内部归约实现待查")],
 19: [p("相同allgather发送载荷的接收完整性", "先核原文双卡/双机范围冲突；固定rank身份和发送标记，交换物理卡/链路并保留HCCL test日志；比较BIOS修订前后可见性，避免把硬件诊断当软件数值公式", "对端卡写→PCIe/HCCL→allgather接收→wordEmbedding后续消费")],
 20: [p("具体linear内核的dtype支持及相同微调权重的参考", "核输入/累加/输出dtype与cast位置，不接受平台整体不支持BF16的过宽描述；在固定权重下比较计算路径；在固定路径下比较充分/未充分训练权重，隔离鲁棒性因素", "BF16载荷→指定linear计算→图像生成；具体内核待查", "V4:enum_dtype:C1")],
 21: [p("A5支持矩阵与同输入causal_conv1d数学参考", "记录A5为何不选custom及实际fallback；同参数比较causal_conv1d_fn和可用NPU实现的首个输出差异；所选公开cast-once性能改动不代替精度修复证据", "SoC分派→causal_conv1d_fn→首token；A5实现合同待查")],
 22: [
  p("TopK明确的排序稳定性/tie-breaking合同", "用逐bit相同的专家分数比较索引；分别测试合法相等分数与近似分数，记录稳定排序是否为API承诺；独立看索引差异对专家选择的影响，不由Radix同步PR反推", "专家分数→gating_moe_topk排序→专家消费", "V4:constant_repeat:N3"),
  p("同门控MM输入的高精结果及允许容差", "逐bit核对MM输入与权重；保存累加/输出dtype、tiling和误差；将两侧MM结果送同TopK隔离微差放大，不要求跨硬件累加顺序相同", "门控MM→专家分数→排序/专家选择", "V4:enum_dtype:C1")],
 23: [p("sorted_indices负值/未激活专家的合法语义与掩码参考", "先核负索引是合法哨兵还是应被拦截；对同路由比较abs前后有效集合和实际MLP写入集合；用受控未激活槽内容检查unpermute是否错误读取，grad_probs反向dtype补丁独立", "路由负标记→abs→未激活专家槽→token_unpermute合并", "API42:1.3.4 V4:index_mask:I4 V4:index_edge:I2")],
 25: [p("实际量化格式、权重和转置布局的高精batchmatmul参考", "补npu_transpose_quant_batchmatmul合法签名与故障实参；分别核载荷/scale解释及转置元素对应；冻结相同输入找首个不达标输出，当前ND权重buffer代码不当历史修复", "量化权重/输入→转置量化batchmatmul→后续token", "V4:enum_dtype:C1 V4:enum_quant:C1")],
 26: [p("同Prefill实参的小算子参考及图编译守卫", "分别核Decode开关为何使Prefill torch.compile，以及融合数值误差；保存图节点与实际qkv_rmsnorm_rope调用；在相同输入下比较融合/分解路径，不以同名PR证明现场", "Decode配置→Prefill编译→qkv_rmsnorm_rope→评测", "V4:enum_operation:C3")],
 27: [p("quant_sparse_flash_attention明确支持的KV编码/scale合同", "记录dsa_cp与mla_prolog_v3产生的FP8/MXFP8载荷及scale布局；在消费前检查格式支持/明确转换或拒绝；同合法语义下对比两路径，删除foreach_copy的PR不作修复", "dsa_cp产MXFP8 / mla_prolog_v3产FP8→KV Cache→稀疏FA", "V4:enum_quant:C1 V4:enum_layout:T2")],
 28: [p("CANN9.1.0同all_reduce操作数的高精归约参考", "保存原位buffer、各rank输入及归约类型；分别审参数排布误差累积和AIV原位竞争的证据，确认哪份属于现场；同步或版本对照仅定位范围，不拼接两个摘要为唯一根因", "各rank输入→all_reduce→首token；具体实现与失效边未知")],
 32: [p("aclnn两阶段封装的资源所有权与异步存活合同", "列executor/workspace/ACL tensor分配大小、提交、最后使用与释放时点；对照手工封装和EXEC_NPU_CMD并保留旧显式同步；先区分分配不足、所有权与提前释放，不能直接命名UAF", "frequency_regulator封装→异步执行器→workspace/tensor→完成释放")],
 33: [p("310P setitem支持矩阵与Python赋值语义", "补真实索引/目标shape和设备支持证据；检查未支持时应fallback或明确报错；对已支持路径核目标存储写回，不把适配需求当已证数值公式缺陷", "310P setitem调用→适配/fallback→fg-clip2消费")],
 34: [p("bs1/2/4/8中相同样本的高精matmul参考", "抽取同一样本的真实输入/权重及batch布局，分别比较matmul误差；记录各batch实际tiling与precision模式；输出替换仅证明范围，后续token对齐不直接证明特定累加错误", "按batch组装输入→matmul→token选择", "API42:1.6.1 V4:nondegenerate:S9")],
 35: [p("QKV生产者与Triton attention的真实stream/event依赖", "在17K第二micro_step核对生产完成→attention读取的流边；以定点event/wait替代cpu规避并观察loss；单独追踪规避后仍NaN的反向gnorm，1K sanitizer无结果不当排除证据", "QKV写→Triton attention读→loss；反向首错仍未知")],
 36: [p("512卡GRPO首步的输入/参考合同待提供", "记录DeepSeekv3.2首loss NaN的首个算子及rank输入；检查初始化、权重、数据一致性后再抽取单算子；A5 GMM K=0技术例不继承", "512卡训练→首loss；实际算子未知", scope="FACT_COLLECTION_ONLY")],
 37: [p("同prompt/图像/权重/seed下狗脸编辑任务的预期", "保留狗脸预期/人脸实际的原始生成结果；补编辑图像、prompt、采样和实现版本；定位首个数值/语义差异后才能拟算子测试，不从RC020继承linear原因", "qwen-image-edit basecase→图像结果；算子未知", scope="FACT_COLLECTION_ONLY")],
 38: [p("整网反向同调用与可独立复现参考待提供", "补问题算子名、完整实参和前序状态；保存单卡launch_blocking仍错与单算子不复现的差别；逐步移入前序依赖与buffer生命周期，避免认为launch_blocking排除所有状态问题", "整网前序→未知反向算子输入正常/输出异常", scope="FACT_COLLECTION_ONLY")],
 39: [p("cat按维拼接的逐元素精确参考", "保存每个成员的shape/dtype/stride及dim，核输出元素对应；比较输入输出storage与异步完成时点，监测是否被后续覆盖；记录eval bs512，但不把bs直接当cat尺寸", "输入tensor列表→cat写出→推荐模型消费", "V4:tuple_size:S8")],
 40: [p("M12本记录确定性重跑的独立证据", "补当前训练配置、实参和spike前首错；核是否与RC009同一记录身份；未证同事件前不继承rmsnorm缓存根因或布局条件", "M12训练→gnorm spike；调用未知", scope="FACT_COLLECTION_ONLY")],
 41: [p("368卡与单机M12各自首错轨迹", "收集相同权重/数据/构建及最早NaN调用；按单机和多机分别找共同最小复现；不因模型名相同继承RC009缓存问题", "单机/多机训练→gnorm NaN；算子未知", scope="FACT_COLLECTION_ONLY")],
 42: [p("合法shape[0,4]下seg_reduce输出shape和恒等元合同", "核空输入是否仍应产生非空结果；用受控输出分配初值检查early return是否完整写回；比较空与匹配非空输入，明确NaN来自未写输出而非输入含NaN", "空输入→empty分配→seg_reduce空路径→下游读", "API42:1.1.1 V4:zero_extent:D3")],
 43: [p("M8单机/千卡/4k卡明确重复性合同待提供", "固定权重、数据、构建和允许随机行为；保存前10步首处分歧并缩减rank；未有算子及API开关，不生成deterministic实参测试", "M8分布式训练→重复结果；实现未知", scope="FACT_COLLECTION_ONLY")],
 44: [p("训推双方相同输入/相同语义的融合与分解参考", "先补具体融合算子与训练/推理参数差别；用同一tensor复现输出不一致，核dtype与舍入；单独记录40步reward下降和图路径，不把局部差异直接当最终因果", "训推融合输出→rollout/reward；具体融合消费者待核", "V4:enum_operation:C3 V4:enum_dtype:C1")],
 45: [p("同输入causal_conv1d_fn与npu_causal_conv1d参考", "保存替换前后真实参数、设备与首个差异；核因果卷积状态/边界和dtype；回复恢复是范围定位，不能把310P或A5别条修复作为本次机理", "causal_conv1d替换路径→多模态理解输出")],
 46: [p("setitem实际索引赋值与目标存储的参考", "补修复提交及写回对象、view/stride和赋值范围；同实参比较旧新实现的首个不同位置；分开记录A3/A5、256k 8p训练指标，不能从症状指定布局缺陷", "setitem写目标buffer→后续训练loss/gnorm")],
 47: [p("固定sum输入、物理设备交叉对照", "导出首个异常sum操作数与期望；交换rank和物理卡并保留压测，检查问题是否跟卡；bool ReduceSum工单无事件关系，不当当前软件根因", "特定卡sum→gnorm Inf；硬件边界待查")],
 48: [p("embedding/scatter/topk各自合法输入与重复性合同", "三个算子分别建立首错条目和输入输出；确认embedding是前向还是梯度，scatter具体变体和TopK排序合同；先定位哪一个违反合同，不拼成一条链或套scatter_reduce工单", "embedding / scatter / topk分别待核；下游确定性观察", scope="FACT_COLLECTION_ONLY")],
 49: [p("相同checkpoint、样本与v_weight更新轨迹", "追踪42step checkpoint之前v_weight首次差异及optimizer/通信写回；比较加载同ckpt后的前向，隔离当步计算与历史累积；MatMul二进制查找PR独立保留", "历史训练更新→v_weight→第一层前向→gnorm spike")],
 50: [p("1230版本反向NaN最小复现待提供", "补切换前后构建、首个反向异常算子和实参；记录前向输出及梯度参考；未确认关联前不从ATK RmsNorm工单指定算子", "版本切换→未知反向调用", scope="FACT_COLLECTION_ONLY")],
 51: [p("专家token计数的整数频次参考", "固定top_k_indices，核histc bins/min/max与bincount合法域及计数总和；比较专家分配后有效写入集合；核与RC010身份后再审ctrl状态，不凭替换治愈继承TPipe原因", "top_k_indices→histc/bincount计数→专家分配→loss")],
 52: [p("step7报错的完整异常和反向首错待提供", "先取得错误栈与发生在loss/gradnorm打印之前的调用；保存该step实际batch和梯度输入；无算子/shape前不捏造测试参数", "step7反向→报错；算子未知", scope="FACT_COLLECTION_ONLY")],
 53: [p("固定woa/wob权重及同输入的可信训推参考", "将hf权重替换和实现替换分开消融；在相同权重下逐层比较einsum与npu_transpose_batchmatmul；分别记录PPL/logpdiffmean并验证哪个baseline可信，packed分块PR不作历史修复", "woa/wob权重→训练einsum/推理batchmatmul→logits/指标", "V4:enum_operation:C3")],
 54: [p("GLM5各训推差异点独立参考待提供", "列明0.15→0.014期间每个修改与首个模块差异；逐项固定输入消融，分开评估full_decode_only图路径；剩余0.014仍需定位，不宣布全部根因已知", "训推模块→图推理→log_prob_diff_mean/乱码", scope="FACT_COLLECTION_ONLY")],
 55: [p("同HY-V3样本的图/非图评分和调用轨迹", "保留0.6→0.42及badcase逻辑正常的现象；补图编译配置、真实算子和首错；泛化split_qkv工单与CPU OOM不替代现场根因", "HY-V3图推理→文本理解评分；首错未知", scope="FACT_COLLECTION_ONLY")],
 56: [p("GLM5单batch首token输入及参考待提供", "保留首token为!且单batch稳定复现；补模型权重、框架、dtype与首错；不从另一GLM5记录继承MXFP8原因", "GLM5单batch推理→首token!；算子未知", scope="FACT_COLLECTION_ONLY")],
 57: [p("HY-V3首token乱码的逐层轨迹待提供", "核原始记录身份与all_reduce摘要是否真正关联；两份重复参数排布摘要只算一来源；先取得实际调用/构建，PCIE测试不当根因", "HY-V3推理→首token乱码；all_reduce关系未知", scope="FACT_COLLECTION_ONLY")],
 58: [p("同attention反向实参的gradV数学参考", "保留从all2all接收端回溯rank3/7再至attn gradV的先后；补缺失自定义反向区段和最终hook日志；仅当命中公开FAG模板时核dimD/mm1BaseK的实际搬运长度，不反向给周报归因", "attention反向gradV→pool/truediv反向→all2all→loss NaN", "V4:unequal_axes:S3")],
 59: [p("gnorm跑飞的真实数值合同待提供", "补模型、训练步数、输入、版本和首错；区分Inf/NaN或正常大梯度；无调用前不构造算子用例", "训练→gnorm；算子未知", scope="FACT_COLLECTION_ONLY")],
 60: [p("已与整网二进制一致的FIA单算子及CPU参考", "保留真实key/value/k_scale/v_scale与切片前后关系；用非1但合法的V scale对照，核缩放值、索引与广播合同；scale=1通过只定位缩放路径，不证明deScalePreVValue就是现场错误", "KV和scale生产→FIA读取/计算→attention输出", "V4:scale_structure:S7 V4:enum_quant:C1")],
 61: [p("FIA前置输入生产者与真实stream依赖", "在FP16/FP8两路线分别记录生产stream和FIA读取；移除torch.tensor隐式同步后用精确event/wait重建必要依赖；比较同实参多次输出并核修复是否仅补失效边", "前置kernel写入→FIA消费；torch.tensor/Host同步可掩盖缺依赖")],
 62: [p("同RoPE配置在verl与单推产生的sin/cos内容", "分别记录创建、加载、sleep/wakeup及切pe/nope前后值；查明全零是初始化、释放后恢复还是错误覆盖；按真实位置验证sin/cos，公开transformers5适配不当cache修复", "辅助cache初始化/恢复→切pe/nope→RoPE消费者")],
 63: [p("speciale在verl与vLLM单推的相同输入参考", "锁定两环境权重、采样与运行状态后找首个数值差异；补真正的推理调用；训练SparseFAG event ID/卡死修复独立，不拿它解释未定位推理精度", "verl rollout / vLLM单推→异常输出；实际算子未知", scope="FACT_COLLECTION_ONLY")],
 64: [p("同decode迭代FLA state读写数学参考", "区分第一个token对齐与后续decode分歧；标出中间state的写入、持久化及下一步读取位置；RingMLA对齐仍乱码与拼写PR分别保留，不把名称改动当状态修复", "前步FLA写state→decode读中间结果→后续token")],
 65: [
  p("相同训练步与相同EMA配置的权重递推参考", "分别记录GPU/NPU原权重、当前权重、EMA shadow及生效状态；复核2k步82%原权重的递推计算；用同一组实际推理权重比较编辑效果，与gnorm精度分开", "optimizer更新→EMA shadow→评估/图像编辑权重读取"),
  p("同repeat_interleave反向输入的FP32/BF16参考", "固定repeat与维度映射，记录反向计算和累加dtype；分别量化FP32/BF16误差与首步gnorm影响；公开INT32大轴分派是独立技术观察，不生成超大轴作为本故障参数", "repeat_interleave反向→上游梯度→首步gnorm", "V4:enum_dtype:C1"),
  p("同RMSNorm输入/权重的先升FP32再回BF16参考", "保存归一化及乘权重阶段dtype；单独对齐NPU小算子的提升位置并测首步gnorm；不把EMA效果原因或repeat反向修复混入", "RMSNorm小算子→前/反向中间值→gnorm", "V4:enum_dtype:C1")],
 66: [p("相同确定性重跑的最小扰动轨迹", "对async dump的md5/xorsum/统计量分别记录同步与分配扰动；先取实际首错和LightningIndexer调用关系；只有确认命中后才核DUPSIZE256、尾mask及UB容量，工具治愈不证明同步", "训练→未知首错；LI KLLossGrad关联待核", scope="FACT_COLLECTION_ONLY")],
 67: [p("lr=0与非0下相同梯度及grad norm定义", "核截图代码、norm归约范围及缩放因子，解释约2倍是否为脚本/并行语义；保存首次更新前后权重及loss；IndexSelect空self/index7与Gather计数修复均不自动继承", "梯度生成→grad norm/优化更新→loss；具体算子未知", scope="FACT_COLLECTION_ONLY")],
 68: [p("Qwen3.5 SFT首步梯度参考待提供", "记录首个NaN梯度与对应算子输入、权重、设备和构建；确认前向loss及反向边；不从GDN推理长packed公开例生成训练参数", "SFT首步→gnorm NaN；算子未知", scope="FACT_COLLECTION_ONLY")],
 69: [p("相同样本在Megatron与参考前向的多模态输入合同", "逐阶段核图像数据、占位token及模型参数；定位图像输入丢失的第一个接口；恢复后比较首步logpdiff并保留残差，BOOL ReduceAll选路PR独立", "图像预处理→Megatron前向入参→多模态融合→logpdiff")],
 70: [p("同mul实参的约定计算dtype和高精乘法", "记录原/对齐后的两侧dtype及cast先后；独立复现mul输出并解释误差传播到loss/gnorm；800步1.2%按模型指标评估，不当单算子通过率", "mul输入→类型处理/乘法→训练loss与gnorm", "V4:enum_dtype:C1")],
 71: [p("Embedding实际前反向合同及每步indices/梯度输入", "保存首NaN步indices、shape及梯度，定位是否已在输入；以低扰动hook记录前序依赖；固定确定性仍NaN不证明空输入或未清零，RC100只保留重复线索", "embedding反向→权重梯度→gnorm；空输入未知")],
 72: [p("Megatron与HuggingFace的MLA head参数映射", "列query/key/value head配置和实际tensor轴；用同hidden输入单独核配置修复前后MLA；分别保留0.02、0.01、0.008和0.0009基线及24/40步观察，残差继续定位", "MLA head配置→实际QKV形状/计算→logp与reward")],
 73: [p("相同LayerNorm/linear/attention语义的高精分解参考", "补TE融合和NPU分解的真实输入/参数；分别比较融合开关的dtype、舍入和输出；MindSpeed TE替换是拟议实验，未执行结果不能写闭环", "GPU TE融合 / NPU LayerNorm与attention→长稳loss", "V4:enum_operation:C3")],
 74: [
  p("同ReduceMean原始输入的高精归约及保留dtype路径", "保存provider最终生效precision_mode和实际计算dtype；比较ReduceMean误差与容差，固定输入阻止下游放大混入；保持dtype后仍有精度差，须独立定因", "原始输入→ReduceMean→Sub；真实累加路径待核", "V4:enum_dtype:C1"),
  p("有限输入下Sub/Mul各阶段高精结果与FP16范围", "记录ReduceMean残差经Sub放大到Mul的实际范围；检测第一个非有限中间值；分别对齐均值与保持dtype测Inf消失，不把输出Inf当输入特殊值", "ReduceMean输出→Sub→Mul溢出→ONNX输出", "API42:1.7.6 V4:intermediate_overflow:N4")],
 75: [p("同matmul操作数的高精参考与原dtype执行", "核ONNXRuntime CANN有效配置/实际kernel dtype；保存有限输入的最大乘积与累加中间范围；比较保持dtype前后误差，输出NaN/Inf不转成输入特殊值条件", "ONNX输入→内部FP16 matmul→非有限输出", "API42:1.7.6 V4:enum_dtype:C1 V4:intermediate_overflow:N4")],
 76: [p("有效prompt的语义与业务期望", "保留用户输入语义问题和停止定位的结论；如复核先取得有效prompt及参考回答；不把旧层间余弦下降当已证算子缺陷", "prompt→模型回答；当前没有可确认算子故障", scope="FACT_COLLECTION_ONLY")],
 77: [p("图与eager对相同通信语义的必要归约次数", "保存图IR、通信方法与所有融合/提前归约位置；验证profile缺最后allreduce是否真的少算；变化运行时配置时核trace冻结谓词，#16484技术例只作待核方向", "编译/trace通信决定→图重放→必要allreduce→模型输出")],
 78: [p("同一多模态样本的dataloader和embedding输入", "在首step核样本身份、预处理、token及embedding输入shape；先纠正上游输入不等价；无具体shape前不生成边界/对齐标签", "dataloader→embedding入参→训练loss")],
 79: [p("客户自定义调用和对应梯度合同待提供", "先取得实际代码与调用数据，再定位>1000梯度尖刺前首错；区分前向/反向和上游异常；公开autograd错误不当本事件证据", "verl Qwen3-VL→未知自定义算子→梯度尖刺", scope="FACT_COLLECTION_ONLY")],
 80: [
  p("timestamp/step_embedder两侧的时间步语义", "补timestamp输入、生成公式和对应修复；固定其他路径只对齐step_embedder并测首步/50步；不得用RMSNorm转CPU效果解释时间步原因", "时间步生产→step_embedder→训练前向"),
  p("同RMSNorm输入及约定精度的参考", "将CPU替换与dtype/公式/同步因素分开；保留318/335及规避后318/312的gnorm；单独评估RMSNorm对50步残差的贡献", "RMSNorm→后续反向→首步及50步gnorm", "V4:enum_dtype:C1")],
 81: [
  p("同mhc权重值在BF16/FP32表示下的高精参考", "记录权重加载/降精位置并固定其他模块；分别测局部输出及Pearson0.93→0.97；指标改善不等于全部训推根因解决", "mhc权重读取→推理前向→logits相关系数", "V4:enum_dtype:C1"),
  p("FusedSwiGlu与AscendSiluAndMul的同实参数学参考", "确认285B两实现输入逐元素等价、dtype和门控顺序；比较5.90625/5.875所在tensor而非与Pearson相混；按算子容差判定是否违规", "SwiGLU输入→激活/乘法→下游logits")],
 82: [p("合法空shape时EmbeddingDenseGrad的输出shape与零梯度合同", "确认empty tensor和null指针含义；保存上游梯度及返回tensor初始化情况；以受控输出初值核所有空路径，不从RC110直接继承未初始化根因", "空前向索引→EmbeddingDenseGrad空路径→权重梯度消费", "API42:1.1.1 V4:zero_extent:D3")],
 83: [p("trainpipeline分桶输出的合法索引域与完成依赖", "保存多流/单流及算子后npu.sync三个对照的同一输入；追踪分桶写完→index_add读取及buffer复用；核异常值是否在完成前/被覆盖后出现，sanitizer未命中不排除也不证明踩踏", "多流分桶写→index_add读→索引异常报错；具体事件/容量待查")],
 84: [p("topk输入生产者与aclgraph内存归属", "在topk前寻找首个NaN/Inf和workspace写入者；标记各图节点buffer生命周期及复用；输入已有非法值时topk可能为受害者，不把特殊值当该事件人工触发因果", "上游图节点→topk input/workspace→topk报错")],
 85: [p("相同CodeLlama模型/权重及MLP高精参考", "先确认客户模型修改与双卡CUDA参考等价；抽取两个异常层的同输入逐算子比较；区分>7%距离指标与仍通过业务测试，未取得dump不指定首错算子", "修改模型→MLP→层间累计误差；具体首错待查")],
 86: [p("相同97次调用的融合/非融合matmul+add/bias参考", "导出首次与最大误差调用的完整输入，核广播、内部dtype和舍入；分开7B/135B与模型8分变化；当前Inductor补metadata的公开改动不证明历史路径", "matmul→add/bias或融合kernel→attention_linear→评分", "V4:enum_operation:C3 V4:enum_dtype:C1")],
 87: [p("同样本的tokenizer结果与attention_mask语义", "逐token核tokenizer、特殊token和mask有效位置；用修复前后相同badcase及全数据集分别验证；mask是模型输入差异，未核算子合同前不挂原API42 mask组合", "tokenizer/mask生成→模型attention→评分", "V4:enum_mask:C3")],
 88: [p("客户修改llama70B与可信参考的同长文本输入", "补完整layer dump和模型修改范围；分别核attention_flash与lm_head的首错，不由长短差异猜序列阈值；P2POp实际op类型未确认前不推通信原因", "长文本→attention/可能lm_head→输出；首错未知", scope="FACT_COLLECTION_ONLY")],
 89: [p("固定prompt/采样参数下可复现的MedBench评测参考", "核TGI是否走ATB模型及实际融合实现；保存GPU回答波动和最高分answer无法复现事实；先建立可信评分分布，再定位logits，不从低分推算子失败", "MedBench样本→服务推理/采样→评分；算子未知", scope="FACT_COLLECTION_ONLY")],
 90: [p("同230帧输入、初始状态与分割后处理的参考", "对第一遍/第二遍分别固定跨帧状态和输入；同时核ONNX已有问题的输出及抠图后处理；Conv/transdata已被算子侧否认，余弦类似不能证明累计误差或内存残留", "视频帧/状态→ONNX/OM→分割后处理", scope="FACT_COLLECTION_ONLY")],
 91: [p("相同输入在ckpt/AIR/ONNX/OM每个导出边界的输出", "固定CANN/HDK/训练配置，比较转换前后图及tensor；用同问题视频定位第一个导出边界；少量视频正常和Lite跑通只作范围证据，不宣布具体图变换错误", "ckpt→AIR或ONNX→OM/Lite→视频推理")],
 92: [p("310P具体kernel特殊值支持及改图前高精有限运算", "保存mul_sub_sub/where的真实输入和第33帧前后中间范围；核是有限输入产生溢出再被不支持的路径消费；比较改图防溢出和整集输出，不从帧号推缓存残留", "图内有限计算→Inf/NaN中间值→310P where/后续消费", "V4:intermediate_overflow:N4")],
 93: [p("短序列在相同RoPE配置下的模型位置编码参考", "记录rope_scaling存在与删除时的真实分派谓词；固定短序列位置、权重和sin/cos比较路径；删除字段是规避，不当API显式RoPE选项或长序列阈值已证", "模型config rope_scaling→长序列策略→短序列RoPE→输出")],
 94: [p("图模式RoPE缓存覆盖缩放后合法位置的合同", "分别核decode/prefill seq_len派生和scaling_factor；在旧范围内、超旧但在扩展范围内的位置比较缓存读取；原摘要与a3a3d38的代码对应仍待现场版本/输入核验，M006的-1不继承", "max_position_embeddings×scaling_factor→图模式cos/sin切片→RoPE消费", "API42:1.5.2")],
 95: [p("相同prompt与输入下MindIE/torch_npu的逐层参考", "核权重、token、采样和实现版本相同；从dump找第一处数值/语义差异后抽算子；未有首错前不从相邻qwen案例补原因", "同prompt→两推理实现→回答差异；算子未知", scope="FACT_COLLECTION_ONLY")],
 96: [p("PD分离与可信基线的同请求逐token轨迹", "记录prefill/decode交接输入、token位置及两版本构建；先定位混杂语言出现前首处分歧；PD名称不足证明KV传输或通信实现故障", "Prefill→交接→Decode→多语言回答；实际失效边未知", scope="FACT_COLLECTION_ONLY")],
 97: [p("每请求逻辑输出shape与实际分配/拷贝长度", "核自写接口是否重复乘BS，并分别以元素数/字节数计算容量；对单请求及多请求检查返回shape、写入范围和请求隔离；M006的infer-shape -1机制不继承", "客户推理封装→输出shape/容量→多请求消费者", "API42:1.6.1 V4:nondegenerate:S9")],
 98: [p("LiveCodeBench固定样本、采样和可靠golden待建立", "区分A2/A3与不同模型/商用版本的评分分布；补可比较的首token/logits数据；缺golden时不凭kernel包差异声明算子错误", "模型/版本/评测→64.55评分；算子未知", scope="FACT_COLLECTION_ONLY")],
 100: [p("本条embedding反向的实际indices、梯度与重复记录身份", "保存首NaN步输入shape和上游梯度；用低扰动hook追首错，确认dump五倍开销影响；与RC071文本重复仅作线索，不继承空输入/未写输出机制", "embedding反向→权重梯度→gnorm；空路径未知")],
 101: [p("替换前后HCCL调用对象及同归约输入待提供", "补版本、collective类型、各rank实参和首个指标变化；先看替换是否改变归约语义/输入；没有调用前不造归约长度或确定性参数", "HCCL替换→训练效果劣化；具体collective未知", scope="FACT_COLLECTION_ONLY")],
 102: [p("相同正则化目标下dropout概率/分布及下游效果", "分别记录FA/MLP dropout实际概率、训练模式与随机状态；比较关闭、FA关MLP增大和伪随机方案的统计/任务指标；语义改变导致掉分不等于算子错，CSE随机注册PR独立", "FA/MLP dropout→训练loss/grad_norm→下游评分")],
 103: [p("CANN7.0/8.0实际ReduceSum同输入参考", "补旧故障dtype/shape、归约维和真实修复提交；保存每阶段有限性和容差；升级解决是来源声明，不能仅凭ReduceSum名字判累加序或溢出", "ReduceSum→后续loss NaN；具体实现失效未知")],
 104: [
  p("相同linear输入/权重在先FP32计算再回BF16的参考", "比较GPU linear与NPU matmul+bias的cast/累加/输出dtype顺序；逐阶段记录误差并单独测loss；不得把mask或数据集问题算作同一数值根因", "linear输入/权重→提升/乘加→回转BF16→loss", "V4:enum_dtype:C1"),
  p("多轮对话历史/当前token的训练mask规范", "记录拼接边界、当前轮标签和有效mask；对照修复前当前数据被mask与应保留位置；只固定mask其余输入相同，验证监督token集合", "对话拼接→mask当前/历史对象→loss有效token", "V4:enum_mask:C3"),
  p("同packed样本的token/label与序列边界参考", "逐元素核两侧token、label及pack元数据；在相同pack边界下比较有效监督位置；输入对齐后再看计算残差，不将pack存在视为实现缺陷", "packing→token/label/SEQ-LEN→模型loss", "API42:1.8.1"),
  p("相同全局样本顺序和epoch尾部保留/丢弃政策", "枚举数据集可/不可被GBS整除时两侧实际消费样本ID；核尾部drop/pad及下epoch起始游标；先对齐样本集合再比loss，GBS不是已知算子batch参数", "dataloader尾样本→epoch游标→下一epoch loss")],
 105: [p("PTA通信配置结构的字段保留与传播合同", "追踪deterministic字段初始化、buffer配置写入、传给HCCL的最终值；同一通信调用只改变buffer配置检查字段被覆盖；确认ReduceScatter实际进入目标分支，环境/框架项不伪作API参数", "确定性配置→新增buffer配置覆盖→ReduceScatter分派")],
 106: [p("相同逻辑矩阵元素在两侧排布下的数学参考", "逐元素核是否真是等价布局或不同输入；记录shape/stride/format及变换顺序；仅在元素等价后比较matmul路径和容差，不先判布局转换实现错误", "输入排布/脚本变换→matmul→stage2 loss", "V4:view_stride:T1 V4:enum_layout:T2")],
 107: [p("客户自定义融合实现明确承诺的重复性合同", "先核实现是否承诺确定性及可用控制方式；同二进制同输入重复，定位内部归约/写入规则；若无该承诺记录能力限制，不自动代表CANN库缺陷", "客户自定义融合算子→重复结果；内部机制待查")],
 108: [
  p("npu rms_norm反向数学梯度及实际实参", "补输入、weight、grad_output及具体错误值；以高精分解参考定位梯度公式/精度；不由同条自定义xpu shape问题指定此算子边界", "npu rms_norm反向→输入/权重梯度；错误关系未知"),
  p("用户自定义xpu反向在目标合法shape的梯度参考", "取得特定shape数值、代码与错误位置；比较相邻合法shape仅在确认分派/分块后进行；不得继承前一rms_norm原因", "客户xpu反向→梯度；shape谓词及消费者未知")],
 109: [p("客户自定义FA同实参反向数学参考", "保存第二步首个异常中间梯度与grad_output；对比NPU标准FA仅定位范围，再审自定义实现；没有shape/dtype前不造反向场景或同步根因", "自定义FA反向→grad norm NaN；内部边待查")],
 110: [p("合法空前向输入下EmbeddingDenseGrad零梯度写回合同", "确认null指空tensor而非无效指针及返回权重梯度shape；以可控初值验证每条空路径完整清零；核RC1修复行与B010行为，BF16 atomic_add摘要独立", "空前向→反向输出分配/early return→权重梯度消费", "API42:1.1.1 V4:zero_extent:D3")],
 111: [p("现场版本GPU SDPA与NPU FA的显式数学scale合同", "核head_dim和默认scale分别为1/sqrt(d)、1的真实接口版本；对同QKV显式传相同合法scale比较，另保留默认值差异对照；scale参数语义不同与V scale对象错绑分别审", "省略scale→两API默认值→attention logits/softmax→loss", "V4:optional_absent:D1 V4:scalar_branch:C5")],
 112: [p("实际mm合法输入与tiling选择谓词待提供", "保存选中的tiling、shape/dtype与误差，核目标平台；用同输入比较旧新策略而非只看评分；无谓词前不构造核数/边界参数或确认M011/M023", "mm Host tiling→内核→推理评分；具体分支未知")],
 113: [p("各rank应该参与同一归约的样本/张量语义", "对照dataloader样本ID和预处理，找卡间输入不一致的起点；核layernorm前allreduce实际聚合的对象；修输入后再比较layernorm，不把下游norm异常当kernel首错", "各rank dataloader→allreduce→layernorm输入norm→模型")],
 114: [p("旧/新mm349同实参计算参考待提供", "补kernel代码、shape/dtype与RC1修复；在相同首次启动条件保存matmul输入输出；首次拉起关联不证明初始化，FA竞争Wiki不能回填mm349", "mm349计算→首次grad_norm NaN；具体失效未知")],
 115: [
  p("固定压力负载的物理设备完整性参考", "保留坏卡身份与压测失败日志；交换rank/卡并更换设备复测；硬件结果独立记录，不作为新增CANN数值机理", "物理卡→计算/传输→训练结果"),
  p("客户融合GPU/NPU实现的同输入数学参考", "取得两实现代码与实际参数；逐阶段比较公式、dtype和结果；在健康设备上隔离验证，不能以坏卡证据证明实现差异", "客户自定义融合前向/反向→训练指标；具体合同待查")],
 116: [p("自定义FA确定性开关两路径的同输入反向参考", "记录开关是否API承诺及实际选择的kernel；比较step0 grad_output和首个增大/NaN中间值；用标准FA替换定位范围，精确同步/归约机制仍需代码证明", "确定性设置→自定义FA反向路径→step0梯度NaN")],
 117: [p("AdamW更新结果与模型实际存储别名的可见性合同", "同时记录param.data、模型param及view的storage/offset和更新值；追踪npu_apply_adam_w之后inplace copy写回对象；比较旧新mindspore包及下一step前向实际读取，避免只看API自身变值", "AdamW更新param.data→inplace copy/alias→模型权重→下一step", "V4:view_stride:T1")],
 118: [p("相同样本顺序/optimizer/RNG状态的epoch边界参考", "固定同checkpoint并保存第二epoch前的状态；分别消融切分策略和融合，不能一次改多项定因；单独比较大学习率与epoch尾部样本处理，找到首个状态差异", "checkpoint/切分/融合→epoch切换→loss")],
 119: [p("同任务下rank身份与物理设备的交叉定位", "核rank2交换和更换设备记录，检查问题随哪一实体移动；保留HCCL压测与FastGatherSyncBatchNorm首错输入；设备已确认结论不变，首错模块不等于算子实现缺陷", "设备/链路→rank2模块输出→loss NaN")],
 120: [p("相同optimizer参数/梯度的融合与小算子更新参考", "保存clip_grad、norm累加dtype、归约范围及每阶段中间值；在同一grad输入比较融合公式/小算子；loss改善仅定位优化器范围，首错值与容差继续核", "梯度→grad_norm/clip→分布式optimizer融合或小算子→权重", "V4:enum_operation:C3")],
 121: [p("MC2 allgather与matmul实际窗口足迹和配置传播", "固定8机输入，对照8.0.RC3/8.0.0及MC2开关四组合；记录ag写/mm读的时间和范围，分别核window偏移与useBufferType传播；来源称8机必现，profiling扰动可消失，不能写复现概率完全未知", "MC2配置→HCCL窗口ag写→matmul读/复用→首step NaN")],
 123: [p("对应PyTorch/CUDA版本GPU cumsum的重复性合同", "固定同输入/dtype/设备重跑并保存首个不一致元素；CPU规避与GPU前缀和高精参考分别评估；不以当前torch.compile issue证明旧事件，也不把GPU问题登记NPU缺陷", "GPU cumsum→后续训练；CPU为规避参考")],
 124: [p("TP2复制/切分权重及其梯度同步规范", "列未切分权重对象、各rank初值/梯度/更新后值；分别验证梯度allreduce和确定性/mbs更改对同步的影响；在相同数据下回归评分，配置相关不等于算子确定性根因", "TP2复制权重→各rank梯度/同步→更新→评测")],
 125: [p("MatMulV3同实参的合法launch配置及高精输出", "保存第二步matmul有限输入、旧新block dim和所选kernel；核启动核数来自哪项tiling谓词及平台范围；新包正常只证明规避，不能自动移植M023核数原因", "Host tiling/block dim→MatMulV3启动→输出NaN→grad")],
 126: [p("首次/第二次embedding同实参的逐元素参考", "先证两次token、权重、构建和warmup配置相同；记录前序调用及cache/存储状态，再寻找第一个不同位置；稳定差异不自动证明缓存污染", "首次/第二次embedding及前序状态→输出；具体实现未知", scope="FACT_COLLECTION_ONLY")],
 127: [p("同dropout语义/概率下的训练与下游评分参考", "核FA/MLP概率、训练模式与伪随机方案的分布；分开关闭dropout与调整正则化的效果，保留RC102近重复身份线索；上游闭环不代表本轮实机或算子错误已证", "FA/MLP dropout→训练→下游任务评分")],
 128: [p("原表与修复代码对初始化/未初始化的真实表述", "先确认null含义及本条写初始化而RC110写未初始化的冲突；核空输入返回shape和各路径写回；只提出可控初值检查，不把缺少的未字补成事实或复现成功", "空前向→EmbeddingDenseGrad输出分配/写回→梯度消费；失效边未定", "API42:1.1.1 V4:zero_extent:D3")],
}


SOURCE_CORRECTIONS = {
 37: "旧decisions称没有异常结果不准确；原weekly_progress明确预期狗脸、实际人脸。仍无算子/实参，不能继承RC020。",
 55: "旧decisions称周报无现象不准确；原weekly_progress有开启图模式0.6降0.42，badcase逻辑正常。",
 56: "旧decisions称仅模型名不准确；原weekly_progress有首token为!、单batch稳定复现。",
 57: "周报根因字段为空，但weekly_progress明确首token即乱码且非!；独立摘要仍不回填根因。",
 83: "旧摘要遗漏多流/单流/npu.sync对照；原weekly_progress明确分桶大值致index_add报错、多流出现、单流和同步后不报错。该事实只支持依赖排查，不确认竞争。",
 121: "旧missing称复现概率未知过宽；原weekly_progress明确8机必现，原进展也称profiling可使不复现。保留两个条件下的原始声明。",
}


# Additional independent weekly claims that the old R3 relation combined. These
# are manual splits, not new customer events or new evidence. Their source
# relation remains unchanged and is attached explicitly below.
PLANS[11] = [
 p("equal逐元素比较语义和上游各算子精度合同", "恢复equal输入，确认约1%相对误差如何改变布尔结果；固定conv/maxpool/relu/softmax的各自输入依次找首错；余弦接近不等于equal输入逐bit相同", "conv/maxpool/relu/softmax→equal→确定性输出差异"),
 p("偶现输出不一致的物理卡交叉对照", "保留1月21日换卡后解决的原进展；在同输入同构建下交换卡和rank，取得压测与设备日志；不以这个硬件子问题解释后续equal输入微差", "特定设备→偶现输出不一致→换卡对照")]
PLANS[20] = [
 p("具体linear内核的dtype支持与高精参考", "记录输入/累加/输出dtype和cast位置；固定相同权重比较BF16/FP32路径；核特定kernel支持，不能接受A2/A3整体不支持BF16的泛化", "BF16载荷→指定linear路径→后续图像生成", "V4:enum_dtype:C1"),
 p("相同计算路径下微调权重的效果与稳健性参考", "固定prompt/输入图像/采样及计算实现；比较实际微调checkpoint与可信权重，记录权重训练状态；权重替换效果不直接证明linear内核错误", "微调权重加载→相同图像编辑路径→狗脸/人脸效果")]
PLANS[26] = [
 p("Decode配置对Prefill编译守卫的规定", "记录Decode开关传播到Prefill torch.compile的真实谓词；比较Prefill图节点与eager选路；核开关是否应影响该阶段，不用算子内部精度问题证明守卫错误", "Decode配置→Prefill compile守卫→融合实现选择"),
 p("同qkv_rmsnorm_rope实参的高精分解参考", "固定同QKV/位置/sin-cos/权重，只比较融合与分解输出；核dtype、部分RoPE范围和内部步骤；公开UB分块补丁不能代替现场误差机制", "已选融合qkv_rmsnorm_rope→输出→评测", "V4:enum_operation:C3")]
PLANS[35] = [
 p("QKV生产完成至Triton attention读取的stream合同", "在17K第二micro_step记录实际stream/event；用局部wait重建依赖代替cpu规避，检查loss NaN是否消失；1K sanitizer三次无结果不排除依赖问题", "QKV写→Triton attention读→第二micro_step loss NaN"),
 p("loss规避后反向梯度的独立参考", "保留cpu规避后gnorm依然NaN；补首个反向异常调用与grad_output，核它是否已从上游带入NaN；不能因前向同步假设成立就宣布反向闭环", "loss规避后的反向链→首个NaN梯度→gnorm")]
PLANS[48] = [
 p("实际embedding变体与重复性合同待提供", "确认前向/反向、indices与对应首错；单独固定embedding输入重跑；不借scatter/topk或RC110空输入原因回填", "embedding→训练确定性观察；调用未知", scope="FACT_COLLECTION_ONLY"),
 p("实际scatter变体与重复性合同待提供", "补scatter目标索引、重复写语义和归约类型；先找本算子独立首错；公开scatter_reduce现象不直接证明客户scatter失效", "scatter写入→训练确定性观察；变体未知", scope="FACT_COLLECTION_ONLY"),
 p("实际topk排序/tie-breaking合同待提供", "补真实输入分数和排序参数；以相同输入分开比较分数与索引；不从其他两个算子或Radix修复继承同步根因", "topk分数/索引→训练确定性观察；首错未知", scope="FACT_COLLECTION_ONLY")]
PLANS[53] = [
 p("固定实现下同woa/wob训练权重与hf权重参考", "分别替换woa、wob与其他权重，保持数据/实现相同；追踪0.3→0.017及单woa0.03的指标变化；验证训练权重是否经过可信推理校验", "训练checkpoint/hf权重→固定推理实现→logpdiffmean"),
 p("同权重/输入的einsum与npu_transpose_batchmatmul参考", "固定相同woa/wob权重比较两个实现逐元素结果；分别记录PPL与logpdiffmean，PPL不变不能证明所有内部结果相同；packed分块公开改动只作独立旁证", "同权重→训练einsum/推理batchmatmul→logits/PPL", "V4:enum_operation:C3")]

SPLIT_SOURCE_RELATIONS = {11: [1, 1], 20: [1, 1], 26: [1, 1],
                          35: [1, 1], 48: [1, 1, 1], 53: [1, 1]}
SPLIT_SCOPES = {
 11: ["equal输入不等价与上游首错", "偶现输出差异的硬件子问题"],
 20: ["linear dtype计算路径", "微调权重鲁棒性"],
 26: ["Decode配置影响Prefill编译", "qkv_rmsnorm_rope数值差异"],
 35: ["第二micro_step前向loss NaN与流依赖", "规避后反向gnorm仍NaN"],
 48: ["embedding调用待定位", "scatter调用待定位", "topk调用待定位"],
 53: ["woa/wob训练权重差异", "einsum与transpose_batchmatmul实现对照"],
}

# (mechanism summary, expected relationship, optional evidence-level override).
# Unknowns describe open questions, not a guessed internal defect.
ISSUE_OVERRIDES = {
 (11, 1): ("equal输入已有约1%相对差异，可被布尔比较放大；上游首错未定位。", "判断equal是否错误前先要求输入逐元素等价；上游误差按各算子自身合同判定。", "logic_hypothesis"),
 (11, 2): ("原1月21日进展将另一偶现输出不一致归于硬件，称换卡后消失。", "相同合法输入下健康设备应保持约定计算完整性；需要交叉换卡日志核实。", "source_declared"),
 (20, 1): ("原文称BF16内部转FP32使linear与GPU有差异，但具体kernel支持和cast路径未证。", "所选linear内核须按实际dtype支持合同执行，输入/计算/累加/输出精度各自明确。", "logic_hypothesis"),
 (20, 2): ("原文另称GPU微调权重未充分训练、鲁棒性不足；尚无隔离实验。", "相同任务效果比较必须固定权重与计算语义；权重质量不能由平台dtype陈述证明。", "logic_hypothesis"),
 (26, 1): ("开启Decode图模式使Prefill也torch.compile并选融合算子；是否违背配置守卫合同待核。", "编译作用阶段应与配置合同一致，Prefill/Decode选路应可追踪。", "source_declared"),
 (26, 2): ("周报称被选qkv_rmsnorm_rope有精度问题，尚未给具体数值失效关系。", "同合法实参下融合计算应满足其规定语义和容差，具体公式/dtype待补。", "unknown"),
 (35, 1): ("cpu操作可规避17K第二micro_step loss NaN；QKV与Triton attention缺流间同步只是原文怀疑。", "attention读取前QKV生产必须完成；需要明确实际stream及event/wait边。", "logic_hypothesis"),
 (35, 2): ("cpu规避loss NaN后反向gnorm仍NaN，反向残差原因未定位。", "应先找有限grad_output下首个异常梯度及其参考，不能继承前向流依赖假设。", "unknown"),
 (37, 1): ("原文有狗脸预期/人脸实际的图像编辑效果差异，未定位算子或机理。", "先固定编辑输入、prompt、权重与采样，建立业务预期及可比参考；当前不能指定算子失效合同。", "unknown"),
 (48, 1): ("原记录将embedding列为可疑算子，未给首错、变体或根因。", "先核实际embedding调用和重复性承诺，再核其输出是否违反合同。", "unknown"),
 (48, 2): ("原记录将scatter列为可疑算子，未给变体、索引及根因。", "先核scatter索引与重复目标写入/归约语义，再判断数值重复性。", "unknown"),
 (48, 3): ("原记录将topk列为可疑算子，未给输入分数和排序合同。", "同输入的分数、索引及tie-breaking应分别按真实TopK合同比较。", "unknown"),
 (53, 1): ("woa/wob权重替换显著改变logpdiffmean，支持权重状态排查；可信baseline未确定。", "比较训推计算前应使用等价权重；指标变化还需定位权重最早差异来源。", "logic_hypothesis"),
 (53, 2): ("推理batchmatmul换训练einsum后PPL不变；尚不知哪个实现可作可信baseline。", "同权重同实参的两实现须先比较局部输出和数学参考，再评估PPL等下游指标。", "logic_hypothesis"),
 (55, 1): ("原文明确HY-V3开启图模式后评分0.6降0.42，badcase逻辑正常；本条没有根因。", "同样本/配置的图与非图需先建立可比参考和首错，不指定某个融合算子。", "unknown"),
 (56, 1): ("原文明确GLM5单batch首token为!且稳定复现；没有根因。", "先取得同token/权重/配置的正常参考，定位首个不一致调用。", "unknown"),
 (57, 1): ("原文明确HY-V3首token乱码且非!；根因字段为空，all_reduce摘要尚未建立事件关系。", "先确认现场调用与来源身份，不能凭相同症状选通信根因。", "unknown"),
 (83, 1): ("多流分桶输出异常大导致index_add报错，单流或算子后npu.sync可规避；具体失效边未证。", "index_add消费分桶输出前应完成有效写入并保持存储不被覆盖；合法输出必须在约定索引域内。", "logic_hypothesis"),
}

# The R3 record-level comparison cannot be copied onto unrelated subproblems.
# Tuples are (nearby original modes, proposal, explanation); all remain drafts.
SUBISSUE_COMPARISONS = {
 (1, 1): ("M001", "PENDING", "RMSNorm升精位置与M001相近；缺具体提升/乘法实参，未证同机理。"),
 (1, 2): ("M019", "PENDING", "M019要求数学等价但有限精度求值次序不同；RoPE公式/布局差异尚不证明数学等价，不能继承RMSNorm标签。"),
 (11, 1): ("M001 M030", "PENDING", "equal是差异放大点；未定位上游dtype处理，M001/M030仅排查近邻。"),
 (11, 2): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "换卡解决的硬件子问题与原30软件实现模式分开，不能证明equal的数值根因。"),
 (20, 1): ("M001 M029 M030", "PENDING", "需区分精度路径、特定内核能力和输入强转；平台整体不支持BF16的陈述不足以选择其中一条。"),
 (20, 2): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "微调权重稳健性是模型状态假设，不继承linear的精度/能力模式。"),
 (22, 1): ("M008", "PENDING", "M008含router对微差敏感的情境，但稳定/非稳定排序是索引语义问题，不能据此归为累加序缺陷。"),
 (22, 2): ("M008", "PENDING", "门控MM累加序与M008直接相近；M005为集合通信rank归约，不自动套到本地MM。"),
 (26, 1): ("M011 M021", "PENDING", "编译阶段守卫与选路有关；M021原为MatmulAtomicAddUbFusion，不能直接等同所有图模式差异。"),
 (26, 2): ("M001 M019", "PENDING", "融合内部可能涉及精度或求值序，但当前无公式/dtype证据，不能由编译触发代替数值根因。"),
 (35, 1): ("M007", "PENDING", "有具体生产/消费流依赖假设，仍需找到真实缺失边；cpu规避不是依赖缺失确证。"),
 (35, 2): ("", "PENDING", "反向仍NaN属于独立未定位残差，不能继承前向M007假设。"),
 (37, 1): ("", "PENDING", "存在业务效果差异，但无算子机理；与RC020同模型不构成继承M001/M029证据。"),
 (48, 1): ("", "PENDING", "仅列embedding，未证空输入或初始化，不能按名称归M020。"),
 (48, 2): ("", "PENDING", "仅列scatter，具体重复索引/累加语义未提供；独立scatter_reduce工单不决定本条模式。"),
 (48, 3): ("", "PENDING", "仅列topk，未给同分/排序/同步证据；不能套RadixTopK技术根因。"),
 (53, 1): ("", "PENDING", "权重替换支持模型状态排查，不证明M001精度路径或M024排布转换。"),
 (53, 2): ("M001 M024", "PENDING", "两实现可比较精度与元素对应，但尚无局部首错；PPL不变不能裁定新增/并入。"),
 (55, 1): ("M021", "PENDING", "图开关评分下降只提供编译路径排查线索；M021的特定融合数值机制未被证明。"),
 (56, 1): ("", "PENDING", "首token为!是输出症状，不能从相同GLM5名称继承格式或scale根因。"),
 (57, 1): ("M005 M028", "PENDING", "只保留通信模式近邻；all_reduce摘要尚无事件关联，不裁为累加序或确定性能力问题。"),
 (65, 1): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "EMA是否生效/权重递推属于模型状态，不继承repeat/RMSNorm的M001/M030。"),
 (65, 2): ("M001", "PENDING", "FP32/BF16反向计算路径与M001相近；INT32大轴选路公开技术例不是该精度机理。"),
 (65, 3): ("M001", "PENDING", "RMSNorm先升FP32再回BF16与M001相近，和EMA效果原因分开；M030特指输入降精，未证本例相同。"),
 (74, 1): ("M001 M030", "PENDING", "ReduceMean路径的dtype与精度差需独立确认；M030输入强转机制不能只由保持dtype改善而确定。"),
 (74, 2): ("M009", "PENDING", "有限输入的中间低精溢出与M009相近，前序ReduceMean误差来源另审。"),
 (80, 1): ("", "PENDING", "timestamp语义修改缺公式，不继承RMSNorm的精度模式。"),
 (80, 2): ("M001", "PENDING", "RMSNorm转CPU仅范围定位；需dtype/公式对照才可与M001比较。"),
 (81, 1): ("M030 M001", "PENDING", "权重BF16/FP32是表示精度线索，未证M030的输入强制降精机制。"),
 (81, 2): ("M019 M001", "PENDING", "SwiGLU两个实现须先证明数学/输入等价，norm差异本身不能确认求值序或提升位置。"),
 (83, 1): ("M007 M015", "PENDING", "同步规避给出M007依赖排查方向，异常值也可能来自M015覆盖；均需真实写读时序，原M011缺具体分派证据。"),
 (104, 1): ("M001", "PENDING", "先FP32计算再回BF16与M001相近；M030的强制输入降精须另证。"),
 (104, 2): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "当前/历史对话mask对象错误是模型输入语义，不能继承linear的M001/M030。"),
 (104, 3): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "packed token/label两侧不等价先修输入；packed是条件方向，不是原30数值根因。"),
 (104, 4): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "尾部样本保留/丢弃政策是数据集语义，GBS不是算子已知batch，不能继承linear模式。"),
 (108, 1): ("M001", "PENDING", "RMSNorm反向计算异常尚无dtype/公式证据，M001仅近邻。"),
 (108, 2): ("M011", "PENDING", "自定义xpu特定shape只提供选路线索，未给shape/谓词，不能继承RMSNorm根因。"),
 (115, 1): ("", "OUTSIDE_CANN_NUMERICAL_ROOT", "坏卡压测是独立硬件问题，不增加CANN软件模式。"),
 (115, 2): ("", "PENDING", "客户融合两实现差异尚无具体公式/dtype，健康设备上的单独对照不能省略。"),
}

CURRENT_UNKNOWNS = {
 37: ["缺编辑图像、prompt、权重/采样配置及可信效果参考；故障算子与数值机理未知。"],
 55: ["图配置、相同评测样本和真实算子首错尚缺；0.6/0.42评分不是单算子证据。"],
 56: ["现场框架、构建、dtype和首token前首错缺失；不能继承其他GLM5条目的根因。"],
 57: ["现场实际all_reduce调用及与摘要的事件关联未知，缺构建/输入及首错。"],
 83: ["缺分桶算子变体、合法索引域、同输入输出数据、实际stream/event及buffer生命周期；同步规避未证明哪条边错误。"],
 121: ["缺MC2实际ag/mm窗口足迹、SetSkipBufferWindowCopy/useBufferType传播及旧新实现；8机无工具必现与profiling扰动不复现须分别记录。"],
}


@lru_cache(maxsize=1)
def _sources():
    def rows(name):
        return [json.loads(line) for line in (R3 / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    result = {r["task_id"]: r for r in rows("results.jsonl")}
    relations = {r["relation_id"]: r for r in rows("failure_relations.jsonl")}
    modes = {r["task_id"]: r for r in rows("mode_comparison.jsonl") if r.get("entity_type") == "WEEKLY_RECORD"}
    audits = {r["task_id"]: r for r in rows("field_audits.jsonl")}
    conditions = rows("condition_relations.jsonl")
    findings = rows("public_findings.jsonl")
    definitions = json.loads((R3 / "condition_definitions.json").read_text(encoding="utf-8"))["definitions"]
    definitions = {(r["system"], r["condition_id"]): r for r in definitions}
    return result, relations, modes, audits, conditions, findings, definitions


def _condition(token, definitions, source_conditions, task_id):
    bits = token.split(":")
    system, condition_id = bits[:2]
    class_id = bits[2] if len(bits) > 2 else None
    definition = definitions[(system, condition_id)]
    if system == "V4" and class_id not in definition["class_ids"]:
        raise ValueError(f"Unreviewed V4 class for {token}")
    # Do not inherit all classes attached to a V4 construction code. A plan's
    # explicit class selects the one question being asked; Requires still must
    # be proved from the real API before a positive classification is possible.
    requires = definition.get("requires", [])
    skip_if = definition.get("skip_if", [])
    if system == "V4":
        requires = [r for r in requires if r.get("class_id") == class_id]
        skip_if = [r for r in skip_if if r.get("class_id") == class_id]
    prior = [r["relation_id"] for r in source_conditions if r.get("task_id") == task_id
             and r.get("system") == system and r.get("condition_id") == condition_id]
    return dict(system=system, condition_id=condition_id, class_id=class_id,
                status="UNKNOWN", purpose="SUGGESTED_TEST_DIRECTION_ONLY",
                semantic_applicability="UNKNOWN_REQUIRES_NOT_REPROVED",
                construction_feasibility="NOT_RUN", requires_check=deepcopy(requires),
                skip_if_check=deepcopy(skip_if), prior_condition_relation_ids=prior,
                definition_ref="condition_definitions.json", counts_as_verified_coverage=False,
                unknown_reason="需真实API签名、合法域与实参证明Requires及未命中Skip；已有原文声明不能替代此检查。")


def review(task_id):
    """Return a detached review draft, or None for the seven separate reviews."""
    if isinstance(task_id, int):
        task_id = f"RC-{task_id:03}"
    elif task_id.startswith("RC") and not task_id.startswith("RC-"):
        task_id = "RC-" + task_id[2:]
    if task_id in EXCLUDED_TASK_IDS:
        return None
    n = int(task_id.removeprefix("RC-"))
    plans = PLANS[n]
    results, relations, modes, audits, conditions, findings, definitions = _sources()
    record, audit, mode = results[task_id], audits[task_id], modes[task_id]
    public = [r for r in findings if task_id in r.get("task_ids", [])]
    issues = []
    seen_relations = set()
    for index, plan in enumerate(plans, 1):
        source_index = SPLIT_SOURCE_RELATIONS.get(n, list(range(1, len(plans) + 1)))[index - 1]
        relation_id = f"{task_id}:REL-{source_index:02}"
        issue_key = relation_id if relation_id not in seen_relations else f"{relation_id}:SUB-{index:02}"
        seen_relations.add(relation_id)
        rel = relations[relation_id]
        level = {"SOURCE_DECLARED": "source_declared", "INTERNAL_SUMMARY_DECLARED": "source_declared",
                 "HYPOTHESIS": "logic_hypothesis", "UNKNOWN": "unknown"}.get(rel.get("basis"), "unknown")
        mechanism, expected = rel["actual_relation"], rel["expected_relation"]
        if (n, index) in ISSUE_OVERRIDES:
            mechanism, expected, level = ISSUE_OVERRIDES[(n, index)]
        unknowns = CURRENT_UNKNOWNS.get(n, list(dict.fromkeys(rel.get("unresolved", []) + audit.get("remaining_gaps", [])))).copy()
        unknowns.append("实际合法调用、参数值、参考容差及目标路径尚未由本模块构造/执行；不补写未知参数。")
        if n == 128:
            unknowns.insert(0, "初始化/未初始化转录冲突尚未解决；未确认输出未写。")
        comparison = dict(mode_ids=list(mode.get("similar_original_mode_ids", [])),
                          decision=mode.get("action", "PENDING"),
                          explanation=mode.get("reason") or "仅为相似机制候选，需以本子问题实际失效关系逐一核对；未作新增/并入裁决。",
                          decision_status="PROPOSAL_NOT_FORMAL_ADOPTION")
        if (n, index) in SUBISSUE_COMPARISONS:
            mode_ids, decision, explanation = SUBISSUE_COMPARISONS[(n, index)]
            comparison.update(mode_ids=mode_ids.split(), decision=decision, explanation=explanation)
        issues.append(dict(
            issue_key=issue_key, issue_scope=SPLIT_SCOPES[n][index - 1] if n in SPLIT_SCOPES else rel["issue_scope"],
            evidence_level=level, mechanism_summary=mechanism,
            expected_relation=expected,
            consumer=plan["path_to_verify"], path_to_verify=plan["path_to_verify"],
            source_relation_id=relation_id, source_evidence_ids=list(rel.get("evidence_ids", [])),
            suggested_conditions=[_condition(t, definitions, conditions, task_id) for t in plan["condition_tokens"]],
            condition_unknowns=[] if plan["condition_tokens"] else ["没有足够语义证据选择API42/V4正向条件；仅按本子问题补事实/验证关系。"],
            design=dict(status="NEEDS_FACTS", analysis_scope=plan["analysis_scope"], execution_status="NOT_RUN",
                        reference=plan["reference"], checks=plan["checks"],
                        required_capability=["取得本子问题实际合法输入/配置与对应实现，并保留dtype、shape、stride、设备和构建身份。",
                                             "可观测并隔离此路径：" + plan["path_to_verify"],
                                             "取得指定参考及容差；如需设备/多流/多rank，须由执行器真实支持，不能用模拟结果冒称命中。"],
                        unknowns=unknowns, generated_parameters=None, pass_fail=None),
            original30_comparison=comparison,
            admission="NOT_EVALUATED", source_verified=False, hardware_validated=False,
            formal_adoption=False))
    return dict(task_id=task_id, reviewer="AGENT_MANUAL_FROZEN_R3", review_scope="CLAIM_SCOPED_TEST_DESIGN_DRAFT",
                execution_status="NOT_RUN", issues=issues,
                original_claim=deepcopy(record["original_input"]["fault"]),
                source_corrections=[SOURCE_CORRECTIONS[n]] if n in SOURCE_CORRECTIONS else [],
                independent_public_observations=[dict(finding_id=r["finding_id"], finding=r["finding"],
                        weekly_event_relation="UNDETERMINED", used_as_weekly_root_cause=False,
                        boundary=r.get("original30_boundary", "")) for r in public],
                missing_does_not_block_registration=True, manual_accept_created=False,
                formal_adoption=False, hardware_validated=False, admission="NOT_EVALUATED")


def all_reviews():
    """121 records; the seven representative reviews are owned separately."""
    return [review(n) for n in sorted(PLANS)]


if __name__ == "__main__":
    print(json.dumps(all_reviews(), ensure_ascii=False, indent=2))
