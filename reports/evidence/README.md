# 证据、审读与验证

- case_review_notes.jsonl：128条逐条审读，可信资料一致性、公开代码主张和原30条关系分开。
- component_reviews.jsonl：153个原先未审组件的处理结论；范围审读、hunk共享、完整响应重复和适用性排除分别登记，不代表153份全文逐行审读。
- supplemental_read_sessions.jsonl：实际补读的文件范围和选段哈希。HTTP文本使用已保存可读文本的字符偏移；GitHub文本保留原CRLF。
- followup_http/、followup_github/：按原根因定向补证的查询、正文、Diff和固定版本源码回执。抓取成功不等于全文审读。
- layout_migration.json：迁移前后路径、跟踪状态和原字节SHA；含本地实验的路径清单，实验内容未发布。
- current_manifest.json：当前HTML、JSONL、输入、证据及本报告所需旧原始响应的哈希。
- rc128-trusted-review.zip：完整离线包，解压后打开reports/current/report.html。

复现入口：python scripts/rc128_actual_report.py build / verify / package。不会访问现场state、启动drive或调用设备。整请求预算仍为160000；本次整理不创建新的模型请求。现有核心门禁回归不因本报告而放宽。

来源中的内部事件资料为交接摘要，公开PR不自动取得客户事件身份。未合并PR、作者的测试声明与本轮设备验证分别记录；本轮设备执行为0。当前原始响应也可从 ../archive/rc128-actual-rework-20261113/ 查阅，均由本报告引用，未复制后改写。

NOT_FOUND表示有限检索和已读范围内没有采用为该原根因补证的代码，不表示全仓不存在修复。已排除的PR、读取受阻回执和未命中的具体查询仍分别保留。SUPPORTED/PARTIAL限定到说明中的技术主张，不是客户事件身份确认。

本阶段只对不对应的旧候选按原根因做定向补查，没有重新对128条无差别扩搜。补证中新增的较强线索包括RC-094的a3a3d38固定提交、RC-030的ops-nn #5083/#9119，以及RC-062的vllm-ascend #17217未合并提案；它们的代码事实、版本和同事件缺口在当前HTML对应条目说明。

验证：实际实现提交1263ba8独立检出，完整回归1013项通过（222.464秒），HTML交互11项通过。Python 3.12.14、pydantic 2.14.3、openpyxl 3.1.5；未验证Python 3.14.3或浏览器渲染。详见publication_validation.json、full_regression.txt、interaction_validation.json。后续提交仅补验证附件和更新包，不改变已验收代码与128条结果。
