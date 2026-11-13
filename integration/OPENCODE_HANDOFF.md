# 原始规则流程交接（0.1.21）

先执行仓库README中的安装、doctor和输入核验。核心不直接调用模型或登录网站；执行器读取单项不可变request，在独立上下文中返回对应response，核心负责`next/submit/drive`、证据和状态。现场工具、模型及权限必须在接手环境核验。

## 输入与规则

使用本仓原件：`knowledge/trigger_library.md`、`knowledge/precision_trigger_knowledge_v4.md`。不要使用本地archive中的修订42、解释覆盖或映射替代它们。原42与V4独立判断，映射缺失不阻塞。

`inputs/cann30_original.txt`是用户最早四字段文本，不是后期15列XLSX。原始XLSX未随此交付取得；如需走XLSX导入，显式准备并记录字段映射和派生关系，不把转换表冒称原工作簿。缺失字段保留UNKNOWN，不从旧整理稿回填答案。

## 当前流程

1. **A1**：以模式原文和来源清单展开有据定义。SOURCE_DECLARATION、MODEL_DERIVED、UNKNOWN分开，保持原模式身份。
2. **A2**：独立核对原V4及选中构造；未选是NOT_ASSESSED，不等于排除。
3. **A3**：独立核对原42的完整条件，不能复制V4标签或通过crosswalk转换。
4. **A4**：整理原E1–E5方法和证据缺口。设计不是执行，缺设备保持NOT_RUN。
5. **横向审查与冻结**：逐项对照定义、边界、复合机制及待定项；由显式finalize冻结，不自动入库或创建人工ACCEPT。

模式定义、来源核验、硬件验证分别记录。无历史Wiki不自动阻止有原定义的工作；没有抓到正文也不能标来源已确认。保留反证和真实冲突，不为取得标签而改写原始条件。

## 执行入口

```sh
python run_faultaudit.py --help
python run_faultaudit.py trigger-workflow --help
python run_faultaudit.py xlsx-workflow --help
python scripts/install_opencode.py --help
python scripts/run_opencode_agent.py --help
```

实际Init输入、state、run_id和输入预算由本次任务显式指定。默认完整输入预算为48000字符；超限应阻塞，不能截断后提交。外部worker模板位于`.opencode/agents/fault-audit-worker.md`的integration源目录，安装器不会覆盖用户冲突配置。

新环境优先从本版原始输入建立可核验的新run；现场原run的恢复须满足[状态兼容要求](STATE_COMPATIBILITY.md)。本仓不携带历史现场SQLite，也不承诺旧结果可以跨profile继承。
