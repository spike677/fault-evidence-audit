# 伪上限清单：哪些「看起来是上限」的常量其实不是上限

> **这是什么**：一份**反例排除表**，专治「看到一个 `MAX_*` 常量就判成容量上限」这类误报。
> **谁该读**：做 FP-B15（定长容器容量）、FP-F03-7（文档未披露上限）、FP-B11（入参校验）、FP-B05（校验覆盖度）检视的人。
> **怎么用**：在把某个常量写成「上限未校验」之前，先在本表里查它——命中即说明它只用于模板选型/路径选择/死常量，**不构成本型载体**。
> **为什么单列一份**：2026-11-06 一轮实测，同一批候选里有 **6 类常量被反复误判**，每次都要重新论证一遍。集中一处维护，比给 52 张卡片各抄一遍更省事（也避免副本互相漂移）。

## 一、伪上限清单（命中即排除）

| 常量 / 形态 | 真实作用 | 为什么不是上限 | 出处 |
|---|---|---|---|
| `MUL_NC_MAX_DIM` / `MUL_NC_PAYLOAD_MIN` | **只用于模板选型**（选 NC 切分模板还是大包模板） | 不参与合法性判定，不拒绝任何输入；超了只会走另一条模板 | 2026-11-06 五仓 25 案，ops-math/ops-nn mul 族 |
| `MAX_V4_REDUCE_AXIS` / `MAX_GRAD_REDUCE_AXIS` | 只选模板；后者是**死常量**（仅声明、全仓无引用） | 同上；死常量连编译期影响都没有 | 同上，reduce 族 |
| `CUMSUM_CUBE_MAX_SUPPORT_SIZE` | 只决定走 **cube 还是非 cube** 路径 | 两条路径都合法，超限不报错 | 同上，cumsum 族 |
| `INT32_MAX_NUM` / `MAX_TENSOR_NUM=64`（非 foreach 场景） | 只做**分批**或路径选择 | 分批后继续算，不是拒绝条件 | 同上 |
| `MAX_EXACT_FLOAT` / `INT32_MAX_VAL` | 只选 **int64 计数**分支 | 换分支继续算 | 同上 |
| `HCCL_GROUP_NAME_LENGTH_MAX` | **死常量** | 全仓无引用 | 同上，hccl 相关 |
| `RANK_LIMIT=8`（编译框架里出现的） | **编译框架**对 rank 的限制 | 不代表算子能力上限；拿它当算子契约会得出「8 维是最优上限」的错误结论 | aclnn-bug-hunt K1356（`aclnnSelu` 实证） |
| `*_MAX_SUPPORT_SIZE` 类且只出现在 **注释**里 | 注释残留 | 无代码路径依赖 | 2026-11-06 一轮 |

**判据一句话**：常量要成为本型载体，必须满足「**它的越界会发生拒绝或越界访问**」——只改变走哪条路径、走哪个模板、进不进 int64 分支的，一律不算。

## 二、真上限清单（命中须查是否校验）

与上表相反，以下形态**是**容量上限，越界即产生后果，必须核「超限时是否明确拒绝」：

| 形态 | 必查点 | 越界后果（实测） |
|---|---|---|
| `Type name[N]` / `constexpr int MAX_... = N` **且被入参索引** | 索引变量（`tensorNum` / `listSize` / `groupNum` / `tensorCount`）是否有上界校验 | host 结构体越界写 + kernel fault（507035）+ 超限部分静默不写（ops-nn#8254 `aclnnForeachExpm1`，n=257 起） |
| `for (i = 0; i < tensorNum; i++) tiling->arr[i] = ...` | 同一处循环是否有 `OP_CHECK_IF(tensorNum > N)` | 同上 |
| 维度硬上限（`dim > 8` / `rank > 8` 直接返回 161002） | 文档是否写了该数值（转 FP-F03-7） | 合法形态被拒 / 用户按文档用超限输入 → 体验崩塌 |
| `headDim > N` 的显式拒绝 | 报错文案里的数字与常量是否一致 | 文案写 512、实际 768 ⇒ 自相矛盾（ops-transformer#7171） |
| `padding > kernel/2` 类比例约束 | 兄弟接口资料是否已写 | 报错信息不可解释（ops-nn#8285/#8286） |

## 三、兄弟对拍：零成本强证据

判「这里该有校验但没有」最省力的写法，**不是**论证上限合理性，而是找同族兄弟：

```bash
# 同一族目录下，谁有校验、谁没有（实测命令）
cd <repo>/foreach
for d in */; do
  a=$(ls $d/op_kernel/arch35/*tiling_data.h 2>/dev/null | head -1)
  [ -n "$a" ] && echo "$d arr=$(grep -c '\[256\]' $a) check=$(grep -rl MAX_TENSOR_NUM $d/op_host 2>/dev/null | wc -l)"
done
```

2026-11-06 实测（**权威源 `ops-nn` @ `b27fda2`**，`foreach/` 下 19 个带 `int64_t tensorElements[256]` 的接口）：

| 接口 | `int64_t tensorElements[256]` | `MAX_TENSOR_NUM` 校验 | 结论 |
|---|---|---|---|
| `foreach_atan` | 有 | **有**（`op_host/arch35/foreach_atan_tiling.cpp:32` 定义，`:74` `OP_CHECK_IF(tensorNum > MAX_TENSOR_NUM, ...)`） | 已护栏，拿它当**对照组** |
| `foreach_neg` | 有 | **有**（`op_host/arch35/foreach_neg_tiling.cpp:32` 定义 `MAX_TENSOR_NUM_FOREACH_NEG`，`:60` 拦截） | 已护栏 |
| `foreach_expm1` | 有 | **无**（整份 `op_host/` 零命中） | **缺陷**（ops-nn#8254 已提） |
| 其余 16 个 | 有 | **有** | 已护栏 |

**族内分布：18/19 有校验，唯一缺口是 `foreach_expm1`。**

> **两次写错、两次更正的过程，本身就是这条判据的价值说明**：
>
> 1. 第一版笔记写「ForeachNeg 有护栏、Expm1 无」——**方向反了**（当时只 grep 了一个文件名，漏了 `arch35/` 分叉）；
> 2. 第二版改成「两者都没有、真正有护栏的是 atan」——**只对 `9.3.0-beta.1` 旧快照成立**；在正式检出 `b27fda2` 上复核，`foreach_neg` 的 `:32`/`:60` **已经有护栏**。
>
> 教训两条：① 结论必须绑定**具体 commit**（同一路径在不同快照上代码不同，行号也不同——`foreach_expm1` 的越界写在旧快照是 `:83`、在 `b27fda2` 是 `:79`）；② 「这个目录没有校验」必须用 `grep -rn` 全目录取证并贴出来，不能靠印象。
>
> 命令模板：`grep -rn "MAX_TENSOR\|NUM_MAX\|> *256" <op>/op_host/ <op>/op_api/`（**全目录**，不要只查 `*.cpp`）。
> 交叉核对一行：`for d in foreach/foreach_*/; do a=$(grep -rl "tensorElements\[256\]" $d/op_kernel|wc -l); c=$(grep -rl "MAX_TENSOR_NUM" $d/op_host|wc -l); [ "$a" != 0 ] && echo "$(basename $d) arr=$a check=$c"; done`

## 四、口径纪律

1. **上限必须有 `[文件]:[行号]`**：写不出就别写「上限未校验」，改记「未核实」。
2. **族内上限值可能不同**：`aclnnForeachLog1p` 是 **128**，其它 foreach 是 **256**（ops-nn#8269）——按族内一例推广到全族是错的。
3. **同目录多份实现要全查**：`arch22/` 与 `arch35/` 常只有一侧加了校验，另一侧没有；只查一侧会得出「有护栏」的假结论。
4. **`experimental/` 副本单独核**：与正式目录的校验常不同步，不得互相当证据。
5. **本表新增条目须附出处**：格式为「日期 + 一轮语料 + 代表接口」，禁止无实证臆测（同库 C1 实证准入）。

## 五、消费方

| 消费方 | 用法 |
|---|---|
| [FP-B15](../patterns/FP-B/FP-B15.md) | 第三节的兄弟对拍命令与「真上限清单」是它的判据主入口 |
| [FP-F03](../patterns/FP-F/FP-F03.md)（F03-7） | 第一节的伪上限先排除，再判「文档未披露」 |
| [FP-B11](../patterns/FP-B/FP-B11.md) | 「真上限清单」里的维度/比例约束，若实现也没校验，则归 B11 而非 B15 |
| [FP-B05](../patterns/FP-B/FP-B05.md) | 同上，文件级参差场景 |

---

> 维护：新增/修改条目直接改本文件（无生成器）；`check_fault_patterns.py` 的 **C29** 会校验本页全部相对链接可达。
> 版本：v1.0（2026-11-06 建立，随 FP-B15 一同引入）
