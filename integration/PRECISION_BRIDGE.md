# PrecisionTesting 规则适配

这是FaultAudit规则与测试合同的只读适配，不是DemonCATPFI注入器，也不执行GPU/NPU任务。0.1.21使用原V4和原42；接手前核对本仓原件清单，不能通过历史映射转换标签。

```sh
python run_faultaudit.py precision-bridge --help
```

已知模式验证与盲测分开。包含Baseline、机制、V4指导案例或历史链接的上下文不能称为盲测。设计、格式检查、来源确认和设备执行分别记录；缺证据保留NEEDS_FACTS/CONFLICT，未执行保持NOT_RUN。

目标PrecisionTesting仓库、提交及本地原生校验器由调用方显式提供并核对；Bridge不修改其规则、任务或运行文件，不自动排队执行。现场环境、接口可达性与设备能力需要另行验证。
