# skill 质量评分卡（v5.0）

> 由 `scripts/score_skills.py` 生成，**勿手改**；改 skill 后重跑，守门 **C27** 校验覆盖与一致性。
> 十维权重：frontmatter 5 / structure 8 / boundary 8 / checkpoints 8 / specificity 10 / resource 4 / fit 5 / trust 7 / evidence 15 / **depth 30**；总分 = Σ(分×权)/10；≥82 PASS，72~81 CONDITIONAL，<72 REWRITE。

## 人工基准（三档读分锚点，不参与计算）

| 基准 | skill | 本卡得分 | 人工定档 | 依据 |
|---|---|---|---|---|
| A | `fpb08-fallback-review` | 95.6 | 100 | 三载体（fallback/插件/fusion pass）× 属性透传，8 条实证，边界表最细 |
| B | `fpg01-hang-review` | 95.7 | 90 | 五子型 + 7 条实证 + 超时熔断与复现序列，检视面最深 |
| C | `fpa13-input-rounding-review` | 72.2 | 70 | 宽浅档 + 无确认实证 + 无扫描基线，仅一个检查面 |

读分方式：A 档为上限参照、C 档为下限参照；其余 skill 的分数按这三档相对解读，**不要拿绝对分跨库比较**（权重是本库定的）。

## 汇总

- PASS：21 / 54
- CONDITIONAL：32 / 54
- REWRITE：1 / 54
- 平均分：81.4 ｜ 区间：67.9~96.0 ｜ 中位：80.0
- 重写清单：FP-A22(67.9)
- 观察清单（72~73.9，虽达 CONDITIONAL 但仍是最薄一档）：FP-B13(72.7)、FP-B05(72.6)、FP-A13(72.2)

## 明细（按总分降序）

| 编号 | skill | front | struct | bound | check | spec | res | fit | trust | evid | depth | 总分 | 评级 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FP-B16 | `fpb16-output-stride-review` | 10 | 10 | 10 | 10 | 10 | 6.7 | 7 | 10 | 10 | 9.6 | **96.0** | PASS |
| FP-G01 | `fpg01-hang-review` | 10 | 10 | 10 | 10 | 10 | 3.0 | 7 | 10 | 10 | 10 | **95.7** | PASS |
| FP-B08 | `fpb08-fallback-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 7 | 10 | 10 | 10 | **95.6** | PASS |
| FP-G02 | `fpg02-sync-review` | 10 | 10 | 10 | 10 | 10 | 3.0 | 4 | 10 | 10 | 10 | **94.2** | PASS |
| FP-B09 | `fpb09-dynamic-shape-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 7 | 10 | 10 | 9.4 | **93.8** | PASS |
| FP-B10 | `fpb10-hccl-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 7 | 10 | 10 | 8.9 | **92.3** | PASS |
| FP-B07 | `fpb07-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 4 | 10 | 10 | 9.2 | **91.7** | PASS |
| FP-C01 | `fpc01-aclnn-review` | 10 | 10 | 9.0 | 6.8 | 10 | 2.7 | 7 | 10 | 10 | 9.8 | **91.6** | PASS |
| FP-F01 | `fpf01-build-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 8.4 | **91.3** | PASS |
| FP-F02 | `fpf02-observability-review` | 10 | 10 | 10 | 10 | 10 | 2.3 | 7 | 10 | 10 | 7.9 | **89.1** | PASS |
| FP-B12 | `fpb12-early-exit-review` | 10 | 10 | 10 | 10 | 10 | 3.0 | 7 | 10 | 10 | 7.6 | **88.5** | PASS |
| FP-F04 | `fpf04-delivery-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 10 | 10 | 10 | 7.0 | **88.1** | PASS |
| FP-A20 | `fpa20-determinism-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 4 | 10 | 10 | 7.9 | **87.8** | PASS |
| FP-B04 | `fpb04-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.3 | 4 | 10 | 10 | 7.9 | **87.6** | PASS |
| FP-B06 | `fpb06-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.3 | 4 | 10 | 10 | 7.5 | **86.4** | PASS |
| FP-B14 | `fpb14-graph-path-review` | 10 | 10 | 10 | 10 | 10 | 3.3 | 10 | 10 | 10 | 6.1 | **85.6** | PASS |
| FP-B11 | `fpb11-validation-review` | 10 | 10 | 10 | 10 | 10 | 3.7 | 7 | 10 | 10 | 6.5 | **85.5** | PASS |
| FP-F03 | `fpf03-doc-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 6.3 | **85.0** | PASS |
| FP-A19 | `fpa19-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 7 | 6 | 10 | 6.8 | **83.2** | PASS |
| FP-A08 | `fpa08-kernel-review` | 10 | 10 | 10 | 9.2 | 10 | 2.7 | 10 | 10 | 10 | 5.5 | **82.9** | PASS |
| FP-A05 | `fpa05-aclnn-review` | 10 | 10 | 9.0 | 9.2 | 10 | 3.7 | 10 | 10 | 10 | 5.5 | **82.5** | PASS |
| FP-A02 | `fpa02-kernel-review` | 10 | 10 | 10 | 9.2 | 10 | 2.7 | 7 | 10 | 10 | 5.3 | **80.8** | CONDITIONAL |
| FP-C06 | `fpc06-soc-generation-perf-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 4.9 | **80.8** | CONDITIONAL |
| FP-E02 | `fpe02-benchmark-review` | 10 | 10 | 9.0 | 10 | 10 | 2.0 | 10 | 10 | 10 | 4.9 | **80.7** | CONDITIONAL |
| FP-B15 | `fpb15-capacity-review` | 10 | 10 | 10 | 10 | 10 | 4.3 | 10 | 10 | 10 | 4.3 | **80.6** | CONDITIONAL |
| FP-A06 | `fpa06-kernel-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 10 | 10 | 10 | 4.3 | **80.0** | CONDITIONAL |
| FP-A14 | `fpa14-mmad-review` | 10 | 10 | 10 | 9.2 | 10 | 4.3 | 4 | 10 | 10 | 5.3 | **80.0** | CONDITIONAL |
| FP-A04 | `fpa04-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 10 | 10 | 10 | 4.2 | **79.7** | CONDITIONAL |
| FP-A01 | `fpa01-kernel-review` | 10 | 10 | 10 | 9.2 | 10 | 2.7 | 4 | 10 | 10 | 5.3 | **79.3** | CONDITIONAL |
| FP-C05 | `fpc05-deterministic-perf-review` | 10 | 10 | 9.0 | 10 | 10 | 3.3 | 10 | 10 | 10 | 4.2 | **79.1** | CONDITIONAL |
| FP-A11 | `fpa11-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 10 | 10 | 10 | 3.7 | **78.2** | CONDITIONAL |
| FP-B02 | `fpb02-corenum-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 3.9 | **77.8** | CONDITIONAL |
| FP-C04 | `fpc04-board-variant-perf-review` | 10 | 10 | 10 | 10 | 10 | 4.0 | 10 | 10 | 10 | 3.4 | **77.8** | CONDITIONAL |
| FP-A15 | `fpa15-kernel-review` | 10 | 10 | 10 | 9.2 | 10 | 4.0 | 7 | 10 | 10 | 3.9 | **77.2** | CONDITIONAL |
| FP-A10 | `fpa10-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.3 | 10 | 10 | 10 | 3.4 | **77.1** | CONDITIONAL |
| FP-A09 | `fpa09-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 4.3 | 10 | 6 | 10 | 3.8 | **76.3** | CONDITIONAL |
| FP-C02 | `fpc02-dtype-perf-review` | 10 | 10 | 9.0 | 10 | 10 | 2.7 | 10 | 10 | 10 | 3.2 | **75.9** | CONDITIONAL |
| FP-C03 | `fpc03-dtype-specialization-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 3.2 | **75.7** | CONDITIONAL |
| FP-A07 | `fpa07-aclnn-review` | 10 | 10 | 10 | 10 | 10 | 2.7 | 10 | 10 | 10 | 2.8 | **75.5** | CONDITIONAL |
| FP-D02 | `fpd02-aclnn-review` | 10 | 10 | 10 | 9.2 | 10 | 3.7 | 10 | 10 | 10 | 2.9 | **75.5** | CONDITIONAL |
| FP-A18 | `fpa18-int32float-review` | 10 | 10 | 10 | 9.2 | 10 | 2.7 | 10 | 10 | 10 | 3.0 | **75.4** | CONDITIONAL |
| FP-A03 | `fpa03-kernel-review` | 10 | 10 | 10 | 9.2 | 10 | 3.0 | 10 | 10 | 10 | 2.9 | **75.3** | CONDITIONAL |
| FP-E01 | `fpe01-golden-review` | 10 | 10 | 10 | 6.8 | 10 | 4.0 | 10 | 10 | 10 | 3.4 | **75.2** | CONDITIONAL |
| FP-A17 | `fpa17-socgen-review` | 10 | 10 | 10 | 8.0 | 10 | 4.3 | 10 | 10 | 10 | 2.9 | **74.8** | CONDITIONAL |
| FP-B03 | `fpb03-migration-review` | 10 | 10 | 9.0 | 10 | 10 | 2.3 | 10 | 10 | 10 | 2.9 | **74.8** | CONDITIONAL |
| FP-A12 | `fpa12-intfloat-review` | 10 | 10 | 10 | 8.0 | 10 | 3.7 | 10 | 10 | 10 | 2.9 | **74.6** | CONDITIONAL |
| FP-B01 | `fpb01-checker-review` | 10 | 10 | 9.0 | 10 | 10 | 2.0 | 10 | 10 | 10 | 2.8 | **74.4** | CONDITIONAL |
| FP-D01 | `fpd01-aclnn-review` | 10 | 10 | 10 | 6.8 | 10 | 3.3 | 10 | 10 | 10 | 3.2 | **74.4** | CONDITIONAL |
| FP-A16 | `fpa16-aclop-aclnn-review` | 10 | 10 | 10 | 9.2 | 10 | 2.7 | 10 | 10 | 10 | 2.6 | **74.2** | CONDITIONAL |
| FP-A21 | `fpa21-tiling-state-review` | 10 | 10 | 8.0 | 3.2 | 10 | 2.0 | 10 | 10 | 10 | 4.8 | **74.2** | CONDITIONAL |
| FP-B13 | `fpb13-narrowing-review` | 10 | 10 | 10 | 9.2 | 10 | 3.3 | 7 | 10 | 10 | 2.5 | **72.7** | CONDITIONAL |
| FP-B05 | `fpb05-coverage-review` | 10 | 10 | 9.0 | 10 | 10 | 3.0 | 10 | 6 | 10 | 3.0 | **72.6** | CONDITIONAL |
| FP-A13 | `fpa13-input-rounding-review` | 10 | 10 | 10 | 10 | 10 | 5.3 | 10 | 6 | 10 | 2.3 | **72.2** | CONDITIONAL |
| FP-A22 | `fpa22-dtype-dispatch-review` | 10 | 10 | 9.0 | 3.2 | 10 | 3.0 | 10 | 10 | 10 | 2.3 | **67.9** | REWRITE |

> 评分是**结构 + 内容厚度启发式**，不评价技术判断的对错；它回答「这份 skill 是否够厚、可执行」，不回答「它判得准不准」——后者由 `evals/` 与 `run_eval.py` 度量。
