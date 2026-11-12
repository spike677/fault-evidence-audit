"""Agent-reviewed R3 decisions, bound to the immutable 128-record input.

These are explicit semantic review notes, not a keyword inference engine.
The builder joins them to actual collection receipts and exact source excerpts.
"""
INPUT_SHA256='683de7190a421fc56ab10c50e7edcc1d29d03f02dfd58b8f7b4fb95b34db5812'

# Every record has a separate disposition; missing public evidence is not a
# negative event identity. Source-declared explanations remain source-declared.
NOTES='''001|rms_norm升精度乘法与ROPE实现差异须分别核对；PTA和CANN rms_norm检索未取得本客户修复。|需要ATB版本、两个接口的调用及中间量，不把340个回答差异当作算子误差率。
002|沿用试跑实读：#10622补传GEMM精度标志，限定beta=0、cubeMathType=4；未证明原事件走此分支。|需原调用参数、dtype和Issue5928身份联系；FP16中间溢出与标志遗漏不能直接合并。
003|沿用试跑三轮：R1采样建议和V4 prefix-cache泄漏Issue均不能解释R1-0528复读。|需采样、缓存、版本及串并行对照；相同100并发不是事件身份。
004|VA的Ring NaN候选与MindSpeed Ring1T查询未定位本条代码路径。|需要首个异常tensor、Ring型号版本和算子调用；NaN不说明输入含NaN。
005|long running precision只得到宽泛候选，缺少长稳首错及状态对照。|需重复调用顺序、缓存状态、版本及首错；不能仅由长稳推断状态残留。
006|rms_norm相关Issue标题不支持本条to(x.dtype)、去patch与dump扰动的具体因果。|需等输入数值及流时序对照；精度变化与插桩同步效应尚未分离。
007|MindSpeed低精attention两次检索无匹配；保留消融结果这一来源声明。|需前反向各自输入、算法、容差与权重；单算子达标不证明整网相同。
008|两份FIA PR同Diff，确有M/V屏障新增；公开Issue是量化推理FIA，不是原训练FA事件。|需CANN8.1RC1的训练FA实现与替换.o对应；两份分支不算两次验证。
009|opbase缓存与PTA rms_norm搜索未取得host-tiling-cache修复；已读融合配置Issue不支持缓存串用。|需布局描述、stride单位、缓存生成失效与命中谓词；不能预断key遗漏，M011仅边界讨论。
010|opbase279在两个极致头开销模板构造中补get_ctrl/set_ctrl，代码支持ctrl设置遗漏这一公开技术关系。|ISA位含义、设备上下文、初始实际值与复位责任仍未知；不等同同步或内存初始化，也未确认客户事件。
011|equal precision检索无匹配；原记录仍在追溯equal以前的输入差异。|需equal原输入与上游首错；1%输入误差放大不证明equal缺陷。
012|MindIE load balance precision查询无匹配，保留alltoall+gmm定位声明。|负载均衡映射、对端数据和GMM输入待核；不串用MLA FlashDecoding摘要。
013|GLM4量化候选未支持0.55与0.87脚本间差异根因。|需固定数据集、脚本及浮点基线后再核量化；版本和模型名不足。
014|310 attention precision查询无匹配，仍仅怀疑SDPA内部matmul。|需要首错调用、shape、精度模式及参考，不把怀疑写作修复结论。
015|MindIE AIME检索无匹配，分数回归不能独立定位算子。|需包版本、评测配置、badcase和首错链。
016|Lmhead检索无匹配；BOOL归约或MLIR反向摘要不支持本条输出首差异。|需Lmhead输入原值与权重、精度模式和误差合同。
017|PTA RFC1921描述A5随机API对齐计划；不是历史exponential_评分问题的已验证修复。|需随机分布统计、种子/算法、框架版本和评分对照；改CPU不证明数学实现错误。
018|原HCCL_DETERMINISTIC查询无匹配；补读PTA5929实际是A5日志/测试默认值问题，与配置透传无关。|原评分约0.424接近仅来源观测；需归约对象、拓扑与逐值对照，分数接近不是bit一致。
019|allgather NaN检索无匹配，原记录主板BIOS通信异常仍为来源诊断。|需HCCL test日志和BIOS修复记录；不能改归算子数值机理。
020|Qwen Image BF16返回的是宽泛候选，不能证实A2/A3整体不支持BF16。|需具体指令/算子路径及模型权重；平台能力不能由局部cast泛化。
021|causal_conv1d A5候选包含性能改动，未定位原替代实现精度故障。|需A5实际fn实现、输入和正确性参考；不把性能PR当数值修复。
022|RadixTopK PR分别增加同步及库API workspace；不证明GLM5稳定排序、MM累加序声明。Issue2757还指出随机输入对照不一致。|需原topk tie规则和等输入；跨shape运行不自动证明跨调用污染。
023|op-plugin4833修grad_probs的dtype取值对象及None兼容，是反向meta问题；不支持前向负索引abs与专家槽位NaN。|需负值合法语义、有效集合、默认填充及消费者掩码；未执行MLP不证明未初始化。
024|8365/8367改用TopK API给出的tmpUbSize并传到kernel，支持临时区容量规划技术事实。|客户是否命中NsaCompressAttentionTopK模板及实际UB容量未知；原30内存类仅相似边界。
025|19674是DSV4 MXFP8 wo_a二维权重被三维perm消费的IndexError修复，2/7文件审读。|原记录只有batchmatmul精度异常，缺同一配置与错误；不能用功能报错替代数值根因。
026|6827正文宣称新增prefill kernel，但取得的kernel补丁是单kernel UB分块/partial RoPE；描述与Diff冲突。|需现场commit、prefill调用及首错；不能按正文推定新增分支已实现。
027|原挂7443实际删除A5 foreach_copy；补读7179是GLM5.3 quant_mode=2/3与DCP组合支持，维护者仍要求环境与对照。|需原GLM5消费者实际类型及dsa_cp生产值；只选读7179，不宣称36项全部已读或确认同事件。
028|PTA all_reduce precision无匹配；两份内部摘要是不同技术解释，不能拼成同一根因。|需CANN9.1构建、通信路径与对应修复；同算子不说明同事件。
029|8005四处FlashUpdate参数由deScalePreVValue换成deScaleVValue，代码支持替换事实。|完整对象、类型、数值合同及调用关系仍未知，不从变量名推出前块/当前块/时间关系。
030|8752/8766是MegaMoe GMM复用跨度，不是dequant64对齐；另读12123归约步长与scaleBuf共改。|需客户shape与实际tiling量；[2,192]输入可整除64，不把输出96或内部q偷换为输入不对齐。
031|16699与Issue16674明确关联，改position从UB读取为GM标量并夹到末行；作者报告Q/K不确定。|原MiniMax事件未给同kernel、shape或版本；公开race报告与代码事实分列，未实机确认。
032|548改为EXEC_NPU_CMD，旧实现已经有aclrtSynchronizeStream。|封装与所有权适配可确认；不能仅由移除手工资源推断早释放/UAF，需队列和资源生命周期契约。
033|310P setitem查询无匹配，保留不支持/适配缺口声明。|需PTA版本与具体setitem入口；支持缺失不自动是数值故障。
034|补读PTA5960/49099确有GEMM融合epilogue元数据漏传，缺少应有舍入截断；原bs1/2事件未证此Inductor版本和路径。|需原shape、精度配置与实现，不能由同matmul继承新修复。
035|Ling NaN查询无匹配，跨流依赖只是原记录怀疑。|需生产者/消费者stream、event/wait及各自串行参考；加CPU操作不是完整修复。
036|verl751是R1-Distill-Qwen1.5B特定step输出!，评论提出low_var_kl exp溢出/裁剪；不是DSV3.2首步NaN的确认根因。|评论是作者分析，需原任务KL形式、输入范围和首错，不据此确认CANN exp缺陷。
037|Qwen Image accuracy候选不能补出原记录没有的异常。|先补输入、输出与期望；basecase名称不是故障证据。
038|NaN launch_blocking无匹配；单卡同步仍出现问题不排除状态与参考差异。|需具体算子、单算子与整网完整参数差异。
039|cat precision无匹配，尚未取得输入正常但输出量级异常的代码依据。|需cat维度、view/alias、输出分配和首错数据。
040|M12 gnorm未命中公开修复；与RC009标题相同只登记可能重复。|本条无cache归因，不能继承RC009根因或事件身份。
041|M12 NaN查询无匹配，模型名相同不足以合并。|需单/多机对照与具体首错、版本。
042|seg_reduce empty在MindSpeed无匹配；空0×4与输出empty占位的关系仍由原摘要声明。|需输出契约、初始化/写回分支；可对照M020但不代表公开修复已证。
043|M8 deterministic查询无匹配，仅有内部非确定性症状。|需同实参同二进制控制、设备/流及首错，不等同API deterministic参数。
044|训练推理候选未定位原融合算子，不能按DeepSeek名关联。|需两侧等输入、权重及算子完整名称。
045|10507明确是FP32 cast-once ring性能优化，作者称数值不变；不是causal_conv1d_fn精度修复。|需原fn版本和替换前后误差；吞吐提升不支持数值因果。
046|setitem precision无匹配，原记录修复后loss贴合仍是摘要声明。|需索引、alias、写回与修复Diff。
047|sum precision无匹配；只在某卡错、换卡恢复仍需硬件记录。|BOOL归约不能证明特定坏卡同事件。
048|embedding scatter topk无匹配，多算子需各自首错。|不能把三个算子拼成一个机理；需输入/配置与对应工单正文。
049|2285改支持性检查中bias dtype的取值对象，修MatMul二进制查找；与v_weight累计差异不同。|需尖刺步权重来源、更新与复现；功能支持检查不能替代训练精度机理。
050|仅1230版本可供探索查询，结果为空，无法定位公开版本或算子。|需可识别版本、模型、报错堆栈与首错；保留INPUT_IDENTITY_GAP。
051|histc/bincount检索及Issue5790提供的是新版崩溃线索，不是原专家计数NaN修复。|需min/max/bin包含边界和输出dtype；不能自动继承RC010 ctrl原因。
052|step7 NaN探索查询无匹配，原文尚无gradnorm/loss。|需真实报错、模型与算子；不能把没有指标当NaN已确认。
053|21494固定q上投影前packed tokens>65536时路径不一致，是另一个明确实现问题。|原替换woa/wob权重的logpdiff事件未给该投影分支；65536阈值不自动是整数溢出或Batch>1原因。
054|GLM5 log_prob两次查询无匹配；多项对齐后差异变小未分离因果。|需各改动与full_decode_only路径对照。
055|HY graph accuracy候选不能补出空白周报现象。|独立DTS用例精度与CPU OOM不能继承给本条。
056|GLM5 first token返回泛化候选，原文没有可核异常。|需现象、模型配置和对应子问题。
057|HY garbled候选无法说明本条；两份近同标题all_reduce摘要不算两份独立证据。|需完整原事件及通信输入；PCIE打流资料关系待定。
058|3901/4152修FAGrad MTE2搬运长度和空tiling结构，不能直接解释自定义反向首个gradv NaN。|原追溯显示all2all前已有NaN，不能把通信输出当首错。
059|gnorm NaN仅探索查询无匹配，xxx模型身份未知。|需公开模型/算子与首错数据。
060|17180是A5 C8-MXFP特性与静态V scale cache，非本条FIA精度70%/scale=1规避的确认修复；8005仅作同方向旁证。|需原FIA模板、CPU标杆、V量化语义和等输入；不得继承RC029具体参数关系。
061|同步消失与torch.tensor隐式同步来自原记录；公开FP8 Attention候选未定位同路径。|需依赖链及去除同步的最小复现；不能仅由插桩影响判race。
062|verl7620修GLM4V transformers5 rotary导入/API，不是sin/cos全零或sleep/wakeup修复。|先核两侧位置、配置和目标调用可比；构造、初始化、传递、取错对象、恢复均待核。
063|8443/8445是SparseFA Grad事件字段及等待/屏障，作者报偶现挂死。|原是speciale verl推理异常，无根因；前反向、数值异常与挂死不能串写。
064|ATB2207只改FIRST_RING拼写并保留旧别名，同值；未修改中间结果消费逻辑。|需Ling decode FLA实际中间量与消费者，不由ring同名归事件。
065|6170是大轴>INT32的RepeatInterleave选路，原是反向FP32/BF16、RMSNorm与EMA差异。|需原轴长度及实现，不能因同算子继承大轴机理；EMA是独立子问题。
066|9834修LightningIndexer缓冲尾部与mask/uint16跨度，代码具体，但未连接MindSpeed DSV4确定性任务。|需原LI调用、tiling与未插桩现场，工具消失不单独证明同步。
067|1562包含GatherV3 indexSize改1、scalar/BF16接口、IndexFill键及loss参数属性，不能一概叫文档PR。|与MiniMax H3 gnorm×2无联系；多个子问题独立保留，不把形状/字节含义猜作已知。
068|Qwen3.5 SFT NaN在MindSpeed无匹配，原记录未给算子。|需框架脚本、首错及参数。
069|6026/3344是BOOL输出在910B/910_93走ReduceAll，不是DSV4图像输入丢失。|同0.404数值须核量的含义；BOOL路径不能冒充图像事件证据。
070|mul dtype检索无匹配，dtype差异仍属来源排查。|需乘数各自对象、dtype提升规则与同输入参考。
071|EmbeddingDenseGrad NaN查询无匹配；Issue90维护者说明清零在执行前，标题不能证明未初始化。|需B067首次异常梯度及shape；不继承空输入根因。
072|attention head MLA无匹配，head参数差异修复后指标改善仍为声明。|需两侧head映射、权重与剩余差异，不把指标改善当完整因果。
073|TELayerNormColumnParallelLinear无匹配，建议切融合尚未验证。|需融合/非融合等价输入及每步输出；建议不是根因。
074|Side重读ORT CANN选项声明与解析，只证明precision_mode是选项，字段未设FP16默认。|原ReduceMean→Sub→Mul溢出链仍是摘要；需实际配置、图和数值范围。
075|ORT两文件不证明全局默认force_fp16；Matmul溢出与保留dtype恢复仅来源声明。|需现场选项默认决策、Matmul输入与FP16中间值。
076|DeepSeek prompt accuracy候选不推翻原文最新“输入语义问题、非问题”处置。|保留早期排查历史，不制造算子缺陷。
077|12649是910C Qwen3下投影融合新增功能，非原0.20图模式缺allreduce的确认修复。|沿用R2的16482/16484选段作独立图归约技术线索；需原版本和实际降图路径。
078|Qwen3 Omni dataloader无匹配，embedding输入shape已不同。|先固定输入数据，不能把输出差异归kernel。
079|verl6319是H20/CUDA的Qwen3.5 SFT NaN，非Qwen3VL NPU自定义算子梯度尖刺。|需客户算子源与实际调用；不能迁移GPU根因。
080|Gemma RMSNorm无匹配；timestamp修复与CPU RMSNorm后仍有差异。|需分别固定两改动及50步权重轨迹。
081|FusedSwiGlu无匹配；5.90625与5.875及FP32权重改善不独立证明缺陷。|需量的含义、输入、dtype、ULP和容差。
082|CANN embedding_dense_grad全28项标题查阅，Issue90不是空shape故障；未找到对应修复。|需空输入输出合同和分支Diff；标题“没初始化”不能越过维护者反证。
083|bucketize英文是搜索假设；Issue5790是histc/bincount崩溃，未确认分桶真实API。|需多流生产消费、event/wait、桶边界；npu.sync规避不证明物理越界。
084|GLM topk NaN graph无匹配；topk输入已NaN/Inf，workspace混乱只是踩踏怀疑。|需上游写入与容量/生命周期证据，不把含NaN当输入构造标签。
085|CodeLlama precision无匹配，客户改模和缺dump仍阻塞。|需原模型/改模及完整层输入参考。
086|补读5960/49099支持新Inductor融合epilogue舍入点缺失这一技术关系；不同于2024盘古融合97次对照。|需原图、实现和容差；新代码关系不能反向确认旧事件。
087|attention_mask tokenizer无匹配；修改两者后badcase对齐是脚本输入方向。|需完整测试集与两侧token/mask，不误标算子根因。
088|P2POp llama无匹配，历史采集磁盘不足属现场采集阻塞。|需P2POp类型与完整layer dump；不能记成公开站点不可访问。
089|internlm accuracy无匹配，GPU参考自身不稳定。|先固定可重现参考、配置与评测，不以评分差认缺陷。
090|ORT CANN segmentation无匹配，原最新ONNX同样有问题且算子侧否认Conv/transdata缺陷。|需图及逐层数值，累计误差是假设。
091|mindspore AIR ONNX precision无匹配，导出路线/版本仍在对齐。|需导出图前后相同输入与算子属性，不预断图变换错误。
092|310P nan where无匹配，防溢出改图有效仍为来源记录。|需合法数值域与硬件支持合同；第33帧不是状态残留证明。
093|rope_scaling候选是不同模型/路径线索；原配置存在即长序列策略的触发关系未找到对应修复。|需短序列合法配置、分派谓词与旧版本代码；不直接继承RC094提交。
094|a3a3d38两个MLA图路径把seq_len乘scaling_factor，代码支持缓存长度计算修正。|周报原文仍是打点/二分计划；四份近重复摘要不算四证，未确认现场commit。
095|DeepSeek distill precision无匹配，原文只写dump定位中。|需输入、首错与实现，不继承RC001同类模型归因。
096|DeepSeek PD language候选不支持本条混杂语言具体原因。|PD分离不自动说明KV传输错；需首错和两端配置。
097|output shape batch无匹配，源称自写推理接口输出shape扩大BS倍。|需输出尺寸与batch契约和接口代码；不是M006的-1推导。
098|QwQ LiveCodeBench无匹配，未固定golden仍是主要缺口。|需稳定参考和各模型共同首错，不能给出确定算子原因。
099|15018/15613展示topk权重错误跟随量化载荷dtype的具体公开关系；保留浮点dtype并加[0.6,0.4]测试。|原2025 DSV3 Base与新DSV4/SP路径、版本不同，机理相关不等于同一事件。
100|共享RC071同一查询及Issue90反证审读，保留两个原始身份。|尚无空输入证据，不能将重复文本计作独立支持。
101|HCCL LCCL探索查询无匹配，原文未给具体归约或替换配置。|需对象、后端、拓扑及评分，不能默认M028。
102|5880/49092是NPU随机算子未登记rand_ops导致编译CSE合并的公开修复，RFC1921另属计划。|原关闭FA dropout改变正则化，未提供compile配置；不把效果差自动认CSE事件。
103|ReduceSum precision及CANN reduce_sum首批标题未得7.0→8.0具体修复。|需旧kernel与输入；升级恢复不定位失效关系。
104|packing labels无匹配；四项脚本差异分别保留，不拼成一个CANN机理。|需各输入/权重/mask/epoch基线，旧稀疏分类仅来源层。
105|PTA5929正文明确是日志格式/默认值导致测试失败，与配置透传无关；没有取得原buffer覆盖确定性配置的Diff。|编码、写入/复位责任、分派消费者及RC1版本未知；不指定结构覆盖或位域操作。
106|matmul format无匹配；两侧是否为等价布局尚未核。|需输入值与stride/format转换，合法转换不是缺陷证据。
107|fused nondeterministic探索无匹配，客户自定义算子未公开。|需接口承诺和源代码；不支持确定性不等于违反接口。
108|PTA Issue1507说明dgamma meta dtype与真实FP32不一致，未给修复PR。|原rmsnorm反向数值及自定义xpu shape问题两项未被证实；meta与数值不可混同。
109|FA backward NaN无匹配，仅来源称自定义反向异常。|需反向合同、同输入参考与首错，第二步不是初始化证明。
110|EmbeddingDenseGrad null及CANN标题未定位8.0RC1空输入修复；Issue90有预清零说明。|本条与RC128“初始化/未初始化”冲突保留；需原分支与版本。
111|沿用试跑固定NPU schema默认scale=1和PyTorch2.6 SDPA None→1/sqrt(d)。|支持指定API契约差异，现场接口/版本/参数未知；不同数学scale不直接归M019等价重排。
112|matmul tiling precision无匹配，原文仅tiling策略问题。|需分派条件、shape和误差链；不能直接确认M011。
113|dataloader allreduce无匹配；原声明不同卡输入先不同，再归约到layernorm。|需卡间样本/归约对象，不误指layernorm kernel先错。
114|mm349无匹配；所附FA竞争Wiki不支持mm349根因。|需kernel定义、输入和RC1补丁，不能从首次拉起推初始化遗漏。
115|PTA186是950DT einsum+masked-softmax不确定的作者报告，根因未定。|原坏卡压测失败与自定义融合实现差异要分开，不能由Issue证明硬件坏卡。
116|MindSpeed FA backward无匹配，替换自定义FA后消失仅限定范围。|需determinism两模式同输入与内部依赖，不预断同步。
117|补读PTA5951是graph bridge梯度detach共享存储被replay覆盖，只有作者CPU替身验证，未取WIP补丁。|原MindSpore param.data变而模型权重不变是另一写回声明；需别名及inplace copy路径，不迁移新Issue根因。
118|Qwen SFT dtype无匹配，多配置更改找到基线未隔离机理。|需切分/融合各自实验、epoch数据顺序和权重。
119|FastGatherSyncBatchNorm标题搜索未定位代码缺陷；原最新确认设备问题。|需换设备/rank流转与压测，模块首错不证明算子实现错。
120|distributed optimizer precision无匹配，切小算子改善仍未定位具体中间量。|需clip_grad、norm及更新写回数据，不能只凭优化器同名挂PR。
121|allgather matmul查询无匹配，MC2 ag/mm踩踏与M004 useBufferType漏传仍是两个待连接声明。|需传参链、HCCL消费与窗口范围；不把讨论升级已证根因。
122|4946修rank参数被置None的reduce选路，7371补IPG双缓冲交换前双向wait_stream；后者有明确同步关系代码。|原0.14.2/0.14.3 2025Apr与公开Qwen2.5VL/A100路径未证同一事件；不能只按开关名认修复版本。
123|PT75240是CUDA cumsum不确定复现，191251是后续性能/确定性scan方案，不是原事件修复。|需原GPU版本、dtype和长度；不计NPU缺陷或实机通过。
124|TP weight检索无匹配，原未切分权重同步声明保留。|需参数分片和梯度同步合同，不因开确定性改善归确定性kernel。
125|matmul block_dim检索无匹配；新包正常后未继续定位。|需旧包tiling/核数与实际输入，block_dim异常不是完整原因。
126|10938是跨版本embedding差异，17797是310P长输入chunked prefill和服务重启差异；均不是首次/第二次调用的确认解释。|需同输入、长度、缓存/warmup和服务边界；不能猜首次未初始化。
127|共享RC102的Dropout查询、RFC与49092正文/Diff，不重复采集，不合并原始记录。|上游已闭环不代表本轮验证；实际正则化与编译CSE关系仍未证。
128|共享空输入检索与Issue90反证，仍保留原文“初始化的空间”与RC110相反的转录。|需原始说明和8.0RC1 Diff，不能静默补“未”，不能用标题证明初始化遗漏。'''

def notes():
    out={}
    for line in NOTES.splitlines():
        n,assessment,gap=line.split('|')
        out['RC-'+n]=dict(assessment=assessment,remaining_gap=gap)
    assert list(out)==[f'RC-{n:03}'for n in range(1,129)]
    return out

# Additional code-reading explanations are scoped to PUBLIC resources. They do
# not transfer a repair, event identity or device result to the weekly record.
# (key, record ids, finding, required relationship, comparison boundary)
FINDINGS=[
('CANN10622','002','beta=0路径补传enableGemm16In32Out给GemmV3 AlphaBeta接口。','精度标志应由原矩阵/输出dtype和cubeMathType生成并交给消费者；完整kernel语义未走读。','M009 FP16溢出相似但未证原参数；不能把精度标志遗漏直接当历史中间溢出根因。'),
('GH12123','030','WholeReduceMax stride q//64*8改q//8，新增scaleBuf_/brcbTmp并修改容量预算。','单位转换不能先丢余数；广播临时区、读取及容量需一致。两个共改组件的独立致因未隔离。','M026/M015/M024相似；q不是原客户输入shape，192输入可整除64。'),
('SIDE-RC111-PINNED-SCHEMA','111','固定commit的npu_fusion_attention scale默认1。','缺省参数来自具体API契约，不泛化成所有NPU API或现场版本。','与M019等价重排不同；显式数学scale差异改变运算含义，仍待核客户调用。'),
('SIDE-RC111-TORCH-SDPA','111','PyTorch2.6 SDPA在scale=None时取1/sqrt(query.size(-1))。','调用迁移须传相同的数学缩放；与NPU schema对应须确认接口和输入维度。','契约参考，不是修复PR或历史事件身份。'),
('SIDE-REFERENCE-3','094','两个图模式MLA路径seq_len从max_position_embeddings改为再乘scaling_factor。','cos/sin缓存长度应覆盖经缩放策略要求的位置跨度。','与M011分派/M014范围相似，但不是窄整数算术溢出证明；原事件commit待核。'),
('GC-Ascend-pytorch-49099','034 086','render前补_compute_fusion_metadata，并显式拒绝不支持的prologue融合。','epilogue消费者需要融合元数据来在指定位置执行acc_dtype→output_dtype→acc_dtype舍入；下游完整实现仅作者说明。','与M021编译/二进制精度与M019顺序相似；原事件路径/版本不同，仍待审。'),
('GC-cann-ops-transformer-12509','008','Mmad之间增加PIPE_M，Cast到入队之间增加PIPE_V屏障；12716相同Diff。','生产数据完成后才可由后续矩阵/向量阶段消费；本轮只审同步相关hunk，未走读所有格式改动。','与M007同步缺失技术相似；训练FA与推理量化FIA调用边界未连接。'),
('GC-cann-opbase-279','010','ElementwiseSch16B及WithScalar构造补get_ctrl、保留一位并set_ctrl。','执行模板首次消费前应设置所需ctrl；精确位语义、设备上下文及复位合同未知。','初始化对象是控制状态，不由初始化关键词归内存模式；六条候选仍待审。'),
('GC-cann-ops-math-4871','022','TopK补同步并将AscendC库API workspace计入临时区。','同PR的同步依赖与workspace容量是两个子问题；不能合成唯一首因。','M007/M015是相似原模式，原GLM5排序与MM机理未被该PR证明。'),
('GC-Ascend-op-plugin-4833','023','grad_probs dtype来源从grad_unpermuted_tokens改为probs，并处理probs None。','输出梯度的dtype绑定其对应概率对象，而非另一梯度载荷。','属于独立反向meta/适配问题，不证明前向负索引abs槽位消费关系。'),
('GC-cann-ops-transformer-8365','024','启发式20*S2align预算改为GetTopKMaxMinTmpSize得到的tmpUbSize并传到消费者。','库算法实际临时空间需求必须由分配方预算并传递；旧启发式与库需求不等价。','M015内存覆盖/M011分派仅相似；新对象与容量边界可讨论扩展，暂不定卡。'),
('GH-PR-vllm-project-vllm-ascend-19674','025','wo_a与scale先reshape为分组维度，再分配持久推理buffer并处理reload。','消费者perm_x2三轴要求对应的权重/scale有分组形状；持久地址另有reload生命周期合同。','M024布局转换相关；原数值故障不能被IndexError替换。'),
('GH-PR-vllm-project-vllm-ascend-6827','026','所选kernel补丁是UB分块循环、partial RoPE与单kernel launch。','合法shape驱动分块和RoPE范围；正文声称的独立prefill路径未在该文件补丁出现。','M018/M011仅作为路径边界参照；正文与当前Diff冲突单列。'),
('GC-cann-ops-nn-7443','027','DEBUG PR删除foreach_copy A5实现与测试文件。','实际修改对象与原quant_sparse_flash_attention消费者不同；这是链接内容不支持，不是仅凭算子名作事件否定。','不作为FP8/MXFP8契约的修复证据。'),
('GC-cann-ops-transformer-8005','029 060','四个FlashUpdate调用将deScalePreVValue换为deScaleVValue。','量化载荷与scale参数必须满足消费者合同；代码可确认替换，完整对象/阶段语义未知。','M010/M024仅暂定边界讨论；不推导前块、当前块或时间步。'),
('GC-cann-ops-transformer-8752','030','MegaMoe复用SwiGLU/GMM1 buffer时，以max(K,K2)安排跨度或专家槽位。','同一复用区两种消费者的最大需求与行/专家偏移必须相容；A2和A3布局方案不同。','M015/M024容量与布局相似，非dequant64对齐事件。'),
('GH-PR-vllm-project-vllm-ascend-16699','031','RoPE position由UB get_element改从GM按clamped row标量读取。','Q/K消费者必须获得其token位置；作者报告UB读取竞争，代码更换载体，未执行硬件隔离致因。','M007同步/M015内存仅相似；读取载体、对象绑定和race解释分别保留。'),
('GC-Ascend-MindIE-SD-548','032','手动ACL两阶段封装改EXEC_NPU_CMD；旧代码有显式流同步。','框架executor、tensor、workspace与队列契约需一致；移除手动封装本身不证明早释放。','适配是载体，不决定独立机理；原封装错误声明未细化到UAF。'),
('GH-PR-vllm-project-vllm-ascend-10507','021 045','causal_conv1d采用FP32 cast-once ring及较小tile作性能优化。','数值保持是作者声明，不能从cast改动自动推出原精度错误；本轮无设备测试。','不作为M001数值精度故障的确证。'),
('GC-cann-ops-nn-2285','049','MMV3支持检查改用support_info中的self和bias dtype。','检查器应消费转换后的支持信息，不能把转换前属性与目标二进制要求混配。','与M029支持性接口和对象归属相似，不支持v_weight累计误差事件。'),
('GH-PR-vllm-project-vllm-ascend-21494','053','q上投影改为固定token网格分块并始终调用融合batchmatmul，避免packed总量跨阈值切成torch.bmm。','同一行结果应不随同批其它行数量改变；代码按固定网格，不是按request切分；行独立性需对应kernel合同。','M018路径相关；不自动归整数溢出，也不能由packed数量推出Batch>1历史触发。'),
('GC-cann-ops-transformer-3901','058','FAGrad四处MTE2加载K长度由mm1BaseK改dimD，空tiling结构也更正。','搬运长度与实际D维度、空分支tiling类型需要一致；两个修正分列。','M026/M015切分容量相似，不能替代自定义反向首错。'),
('GH-PR-vllm-project-vllm-ascend-17180','060','增加C8-MXFP E8M0 scale支持、静态V scale cache与测试。','新特性的scale缓存与块形状需对应；2/20文件审读不足以解释原FIA 70%精度。','这是独立特性与旁证，不确认M010或RC029同机理。'),
('GH-PR-verl-project-verl-7620','062','GLM4V适配transformers5 rotary函数及mrope_section配置位置。','API迁移要消费兼容的函数与配置；不是原sin/cos全零根因。','辅助张量内容/生命周期关系仍待核；恢复遗漏仍只是解释之一。'),
('GC-cann-ops-transformer-8443','063','SparseFA Grad补事件ID、tiling字段/对齐及等待屏障。','参与者要取得对应event字段并遵守依赖；同PR多项变化未隔离唯一致因。','M007相关技术例；原前向speciale推理异常无身份连接。'),
('GC-cann-ascend-transformer-boost-2207','064','FISRT_RING拼写改FIRST_RING并保留原值别名。','符号兼容改动不等于改变FLA中间结果消费。','不作新故障机理或原decode修复。'),
('GC-cann-ops-nn-6170','065','大于INT32_MAX_NUM的轴与允许dtype组合优先返回V2支持。','合法大轴不能落入不适用实现，分派消费者需看到轴长度和dtype。','M011分派/M014位宽相似，但代码未证明具体算术溢出；与反向精度、EMA分离。'),
('GC-cann-ops-transformer-9834','066','UB空间增加DUPSIZE256，mask与尾部uint16跨度修改。','容量、mask表示与指令写入跨度需一致；不能把元素/字节/uint16单位混为一个数字。','M015/M026类似；原LI调用和实际tiling未确认。'),
('GC-cann-ops-nn-1562','067','Gather indexSize改1；另有IndexSelect、IndexFill与loss属性改动。','每个子问题按各消费者合同分析；一个混合PR不是一条完整故障。','与原训练gnorm×2无代码连接，禁止跨子问题拼接机理。'),
('GC-cann-ops-math-6026','069','BOOL输出在指定SoC分派ReduceAll，其余走ReduceProd。','输出dtype与平台共同决定等价归约实现的适用域。','M011/M029接口分派相似；与图像输入丢失无事件身份。'),
('GH-PR-vllm-project-vllm-ascend-12649','077','增加910C Qwen3下投影融合开关和注册。','融合是否保留原归约需实际降图路径；新增特性不是旧图遗漏归约的修复证明。','2/28文件，只作独立功能参照；机器人评论不是代码依据。'),
('GH-PR-vllm-project-vllm-ascend-15018','099','在量化前保存activation_dtype并让topk_weights按原激活dtype转换。','路由权重应绑定数学激活域，不能绑定量化后载荷表示。','与M001数值格式相似但对象取值阶段更具体；是否扩展仍待审。'),
('GH-PR-vllm-project-vllm-ascend-15613','099','量化hidden_states的fp8/int8不得成为路由权重dtype，保留float32并补测试。','0到1的权重不能转int8丢为0；浮点权重与量化载荷的对象/表示域独立。','与15018相关技术方向不算两次设备验证；原2025事件未确认。'),
('GC-Ascend-pytorch-49092','102 127','将NPU随机算子注册进Inductor rand_ops，避免CSE合并随机调用。','相同实参的随机操作不具普通纯函数CSE复用资格。','M012/M028确定性名称相近但目标相反；随机语义与确定性控制不合并。'),
('GH-PR-deepspeedai-DeepSpeed-4946','122','删除rank=None重置，使use_multi_rank_bucket_allreduce=False进入reduce。','选路消费者必须收到原rank，而非无条件覆盖值。','不是缺少梯度完成等待；同一开关不说明同根因。'),
('GH-PR-deepspeedai-DeepSpeed-7371','122','contiguous+overlap且设备不自动解依赖时，切换IPG buffer前双向wait_stream。','复用buffer前生产和消费必须完成；两个stream各自依赖需满足。','与M007同步相关，但框架与参与者边界不同；原版本身份未证明。'),
]

# The resource has been inspected to its stated scope. These relations concern
# a CLAIM, not the provenance of the URL or a deterministic event exclusion.
MISMATCH_FINDINGS={
 'RC-022','RC-023','RC-025','RC-027','RC-045','RC-049','RC-058','RC-062',
 'RC-063','RC-064','RC-065','RC-067','RC-069','RC-077'}
SIX={'RC-009','RC-010','RC-023','RC-029','RC-062','RC-105'}
