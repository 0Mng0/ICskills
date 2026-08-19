---
name: sim-flow
description: cocotb 验证仿真平台搭建方法论。根据设计文档与 spec.yaml 搭建 cocotb 验证平台时使用：验证点表（VP 五要素）、平台固定搭建顺序（driver/monitor/参考模型/scoreboard）、checker 证伪、用例分层（定向/边界/随机）、回归纪律（seed 记录、日志实质判定、四态分类、失败先复现）、覆盖洞分类、status.yaml 状态追踪、B 层独立提取与 gap.yaml 对接（对照清单三态分流、gap 落地挂接 VP）。与 dv-collab 配套：输入是它的交接契约，输出是 bug.yaml。
whenToUse: 当任务涉及搭建或扩展 cocotb 验证平台、编写 driver/monitor/scoreboard/参考模型、组织验证用例与回归、记录验证状态时
---

# cocotb 验证平台搭建规范

适用于以 cocotb（Verilator/Icarus 后端）搭建模块级验证平台。核心原则：
**黑盒验证、先证伪后信任、证据落盘**。

与 `dv-collab` 的接口：**输入**是 `doc/yaml/spec.yaml` + `doc/md/`
设计文档（验证侧不读 RTL，例外与门禁见 dv-collab 第 1、3.1 节）；**输出**是
`doc/yaml/bug.yaml`（BUG 交接）和 `sim/status.yaml`（验证状态）。

## 主流程（固定顺序，不许跳步）

1. **消化输入**：通读 spec.yaml，先确认所验版本的 `doc.stage`（confirmed
   才是签版基线；若验 draft 版须明确记录并预期其会变化），过一遍其中的
   "验证侧验收清单"；
   文档缺口/歧义一律登记 `doc/yaml/question.yaml`，存在未关闭的
   `blocking: true` 假设时，不得编写受影响的 checker。
2. **建验证点表**：从 spec 的 functions/contract 逐条展开 VP，
   每个 VP 填齐五要素（激励/观测/期望/checker/testcase）才许动手写代码。
   规范见 `references/verification-points.md`。
3. **搭平台骨架**：固定顺序——interface 信号封装 → driver → monitor
   （握手拍采样）→ 参考模型 → scoreboard。各组件职责与纪律见
   `references/platform-build.md`；DUT 为 `#0.1` NBA 风格时采样相位纪律
   遵循 dv-collab 第 4 节，不在此重复。
4. **smoke**：最小用例打通全链路（驱动→DUT→monitor→scoreboard 比对），
   打通前不写正式用例。
5. **checker 证伪**：每个 checker 配至少一个"必然失败"的反向用例，确认它
   真的报警。checker 未证伪前，它判出的 PASS 不计入证据。规范见
   `references/stimulus-and-checker.md`。
6. **写正式用例**：定向（契约条款、边界、非法输入）→ 约束随机（组合空间、
   反压模式）。随机用例 seed 必须进日志名。规范见
   `references/stimulus-and-checker.md`。
7. **回归**：判过看日志实质（不看进程退出码），四态分类
   （pass/fail/incomplete/interrupt）；失败先固化现场、固定 seed 复现，
   再改任何东西；确认 DUT 问题按 `bug.yaml` 交接。规范见
   `references/regression.md`。
8. **覆盖率与状态**：覆盖洞先分类（缺激励/采样错/约束阻挡/不可达/…）再
   决定动作；每次回归后更新 `sim/status.yaml`。规范见
   `references/regression.md`、`references/status-tracking.md`。

## 工程结构

```
sim/
├── tb/             # cocotb 测试与组件（driver/monitor/refmodel/scoreboard）
├── run/            # 回归脚本、Makefile、logs/、waves/、cov/
├── vp_table.yaml   # 验证点表（五要素映射）
├── status.yaml     # 验证状态（VP 状态/最近回归/未解释失败）
└── templates/      # 可套用平台模板——【待补充】
```

## 模板（待补充）

`sim/templates/` 计划放置可套用的 cocotb 组件骨架（driver/monitor/
scoreboard/参考模型）与回归脚本。**当前为空，后续补充**；补充前按
`references/platform-build.md` 的职责说明手写。

## 红线

- 验证侧不读 RTL（例外见 dv-collab）；checker/参考模型只从
  spec + 设计文档推导。
- 不把"激励已生成"当"激励被接受"：覆盖率与配对以 monitor 在握手拍的
  采样为准。
- 不凭猜测实现文档没写清的行为：先登记假设、先提问。
- 不改 RTL。发现疑似 DUT 问题，走 `bug.yaml` 交接。


## gap.yaml 功能遗漏对接（B 层独立提取，验证侧维护）

> 本节为设计侧留置的交接说明，验证侧已承接（2026-08-19 补全 B 层执行
> 流程与挂接）；契约的完整字段与状态机以 dv-collab `references/gap.md`
> 为准。

### 为什么要做

功能覆盖完整性靠三层互查保证（A/B/C，见 design-flow §3），其中 **B 层
（验证侧独立提取功能点）是唯一
能抓"设计者盲区"的机制**——设计自己写的叙事文档和功能 yaml 共享同一个
盲区，设计自查（A 层正向映射）永远发现不了"文档本身就没写"的缺失。
因此需要一条正式通道，把验证侧独立提取发现的"规格缺失"回流给设计：

- 让"根本没写"有正式上报格式（不散落在聊天记录或假设池里）；
- 让设计对缺失的处置（采纳/拒绝/挂起）有**承诺与兑现检查**；
- 让每条遗漏从发现、裁决到落地进规格全程可追溯。

### 做了什么

`gap.yaml` 定义"功能遗漏报告"的状态机与字段分工：

- **验证侧提交**（open→proposed）：发现来源 `source.kind`
  （independent_extract/requirement/review/test_escape）、缺失描述
  （可判定语句）、建议 FUNC 草案、是否阻塞验证；
- **设计裁决**（verdict）：accepted = 承诺纳入 spec 指定版本，
  落地后回填 `landed_func/landed_version`；rejected = 给出可复查理由且需
  验证 acknowledged；deferred = 挂起注明再议时机；duplicate = 指向已有
  FUNC/GAP 条目；
- **闭环门禁**：accepted 必填 `target_version`，到期未回填 `landed_func`
  由工具报警；rejected 未获 acknowledged 不得 closed（防单方面关门）。
- **边界**：实现偏离规格 → `bug.yaml`；写了但不清楚 →
  `question.yaml`；规格根本没写 → 本文件。

### 怎么通过 yaml 实现

验证侧职责（配合 dv-collab §3.1 契约）：

1. **独立提取（B 层纪律）**：收到 spec 新版本后，先只看叙事
   文档独立提取一遍功能点，再与 yaml 的 functions 对比——差异中"根本没
   写"的写成 gap 条目（填 open/proposed 各字段），"写得不清楚"的转
   question.yaml；
2. **对设计 verdict 的 acknowledged**：rejected 条目需验证侧确认理由
   成立才允许 closed，有异议走 `discussion` 往返；
3. **工具校验**：`landed_func` 引用闭合（新版本 spec 必须存在
   对应 FUNC）、`target_version` 兑现检查（到期未回填报警）。

### B 层独立提取：执行流程

**时机**：

- 首次收到某模块 spec.yaml（stage=confirmed）：**全量**提取；
- 此后每次 spec 升版 re-baseline：按 change_summary 波及章节**裁剪**
  提取，未波及章节抽查；裁剪范围与理由记进对照清单头部（防裁剪过度）。

**步骤**：

1. 只看叙事文档（不看 spec.yaml），以 design-flow §4 十维正交检查单
   为向导逐维提取功能点——粒度与设计侧一致（一条可判定行为 = 一条
   功能点），保证 B 层与设计覆盖口径相同；
2. 提取结果与 spec.yaml 的 functions 逐条对照，形成对照清单（B 层
   留痕证据，无清单 = B 层没做）：

```yaml
# sim/b_extract_<模块>.yaml——验证侧工作文件，随 sim/ 归档
baseline: "SPEC-xxx v0.4 @<commit_id>"
mode: full                # full=首次全量；partial=升版裁剪（须记范围与理由）
items:
  - extract: "复位中途来交易的行为"
    match: null           # 对应上的 FUNC-id；null = 未覆盖
    verdict: missing      # covered | missing | ambiguous | inconsistent
    note: "文档 §2.7 有描述，spec 全篇无对应 FUNC"
```

**差异三分类（逐条分流，不许搁置）**：

- `missing`（文档有、yaml 无）→ `gap.yaml`（source.kind:
  independent_extract）；
- `ambiguous`（写了但不清楚、两种读法）→ `question.yaml`；
- `inconsistent`（文档写了且清楚，但 yaml 条目与之对不上：无源条目、
  曲解条款语义）→ `question.yaml`，要求设计澄清并改正 spec。

### gap 落地与 VP/回归挂接

spec 升版 re-baseline 时（主流程步骤 1 之后）：

1. 扫 `gap.yaml` 中 `design_response.landed_version` = 本版的条目；
2. 其 `landed_func` 列出的每个新 FUNC 必须展开成新 VP（vp_table 加
   条目，status=open），按五要素流程推进；
3. 无 VP 的 landed_func = 挂接断链，计入当轮 `status.yaml` 的
   unexplained 清单，必须清零。

### 校验脚本（待实现）

- `landed_func` 引用闭合：扫 gap.yaml 全部 landed_func，检查对应版本
  spec 中存在该 FUNC-id；
- `target_version` 兑现检查：verdict=accepted 且 spec 已到
  target_version 而 landed_func 为空 → 报警；
- 设计侧 A 层双向差集脚本与本批同期实现（见 design-flow §8）。
