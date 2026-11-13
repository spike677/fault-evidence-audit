# FaultAudit

FaultAudit 0.1.21 是可审计的故障证据核验核心。当前公开交付包含程序、原始规则、555／128输入和四项续作入口。模型判断和网站采集由外部 OpenCode/Codex 执行器完成；核心保存任务、原文、引用、状态及报告。

本项目不包含 DemonCATPFI 的故障注入、模型效果评价或 NPU 运行工具。`precision-bridge` 是规则及测试合同的只读适配，不是注入器。

## 安装与离线检查

需要 Python 3.10+；当前验证环境见 [VALIDATION.md](VALIDATION.md)。在独立虚拟环境中执行：

```sh
python -m pip install -e ".[excel,precision]"
python run_faultaudit.py doctor
python inputs/verify.py
python -m unittest discover -s tests -v
```

核心依赖 Pydantic 2；Excel 导入使用 openpyxl，PrecisionTesting 适配使用 PyYAML。可选 XLSX 作者另需 `@oai/artifact-tool`，不随本仓库捆绑；JSON、HTML、TSV不依赖它。

## 四项续作

1. **搜索优化分类**：[研究项目链接](research/README.md)。窗口为上海时间2026-06-01 00:00至2026-11-13 20:09:36。现成先验与案例归纳分别验证，保留原V4／原42作为候选；不预设O/D优于原体系。本仓只提供项目链接和任务边界，不包含此前研究快照或搜索结果。
2. **V4与42整体流程优化**：[执行交接](integration/OPENCODE_HANDOFF.md)。保持A1定义整理→独立A2 V4→独立A3原42→A4执行方法与证据→横向审查→显式冻结。未执行、未知和来源缺口分别记录。
3. **验证555案例**：[输入包](inputs/README.md)。先逐案语义与证据复核，再为具备条件的案例建设设备验证。555不是555份可运行设备测试；输入投影不携带旧机制标签或验证答案。
4. **用128条扩展基础30库**：从原始 `inputs/rc128_original.jsonl` 与 `inputs/cann30_original.txt` 开始。先核对来源、事件和机制，再形成待审扩展；不自动修改原库或接受旧结论。

四项任务尚未因此次整理而完成。历史报告、修订规则、映射、状态库、旧工程及研究原始下载只在本地archive保留，不随Git或Release发布。

## 原始规则与输入

- [原V4](knowledge/precision_trigger_knowledge_v4.md)：6主题、31条件类、55唯一构造、64挂载、195指导案例及E1–E5；这些计数与555历史案例不同。
- [原42](knowledge/trigger_library.md)：按原始字节保存42个ID、定义和适用条件。
- [原件校验清单](knowledge/originals.json)与[输入校验清单](inputs/manifest.json)。

0.1.21直接解析原始条件，不覆盖Requires/Skip、不生成修订42或crosswalk、不加入跨流补充规程。原文存在张力时保留待解释项。旧修订profile不能静默转换为本版有效状态，详见[状态兼容边界](integration/STATE_COMPATIBILITY.md)。

## 代码与交付目录

| 目录 | 内容 |
| --- | --- |
| `faultaudit/` | 通用证据、任务、工作流、状态及报告核心 |
| `schemas/`、`integration/` | 输入输出合同和外部执行器薄适配 |
| `tests/`、`examples/` | 通用合成回归与明确标记的合成输入 |
| `knowledge/`、`inputs/` | 原始规则、原始输入和中性555投影 |
| `research/` | 项目链接及检索边界，不含研究数据 |
| `scripts/` | 安装、打包、外部Agent和离线验证工具 |

本地运行可生成 `work/`、`reports/`、`dist/`，均不属于公开源码输入。提交清单由Git界定；打包白名单与输入哈希会再次检查。禁止将令牌、Cookie或浏览器profile放入输入目录。
