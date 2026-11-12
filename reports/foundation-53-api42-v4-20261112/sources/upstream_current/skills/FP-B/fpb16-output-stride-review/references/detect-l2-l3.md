# FP-B16 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / content（内容取值） |
| 观测手段 `oracle` | `golden-canary` |
| 信号类型 `signal` | `canary` |
| 执行线 `lines` | `memory` / `valid-fuzz` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 出参传带空洞 stride 的合法 view（view=[B,H]、stride={H*2,2}、storage=[B,H*2]；或中间维空洞 stride={64,8,2}、storage=[8,8,8]），先断言 max_offset = Σ(shape[i]-1)*stride[i] < numel(storage) 才算合法；出参 buffer 预填哨兵（FLOAT -777000 / FP16 0xFBFF / INT8 -128）；同时跑一条出参全连续的基线。一次只改一个出参的 stride，多出参同改无法定位失效路径。 |
| 判据 `judge` | 连续基线的哨兵必须为 0——非 0 说明构造错，或该出参在当前 attr/mode 下本就不输出（如 quantMode="static" 的 scaleOut、资料明示"暂不支持"的 zloss）；非连续用例须按 stride 读回后与基线逐元素一致才算通过。禁止只断言返回码。 |
| 判别力 `kill` | 若出参 stride 未参与寻址，算子会把 numel(view) 个正确结果写到 storage 基址起的连续位置；按 stride 读回时 1/stride比 的偏移落在未写区、读到哨兵；物理 dump 显示前 numel(view) 个与基线全等、其后全哨兵。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `golden-canary`（共 5 条）

- `K128`（假 PASS）随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS
- `K129`（假 PASS）金丝雀图案不能与合法输出重合：掩码类 0xFF 就是 prob=0 的正确输出
- `K427`（假阳）mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 5 条 L3 判据。 <!-- END DETECT-SECTION -->