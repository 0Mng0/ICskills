---
name: dv-collab
description: 设计与验证（RTL/DV）协作规范，双方共同维护。职责边界（绝对隔离：设计不改 sim 验证平台、验证不读不改 RTL；rtl/sim/ 仿真模型豁免归验证侧）、工程结构示例（rtl/{design,sim,ref}+sim+doc+migration+work）、只通过文档沟通且文档不清先提问补充、四份 YAML 交接契约（spec/bug/gap/question，严谨字段规范见 references/）、#0.1 风格下 TB 采样相位纪律、bug 交接流程（reproduced 门槛、设计独立定根因、修复回执、状态归属与四段复验）。只定义交接规则；design-flow 产设计侧文件、sim-flow 产验证侧文件
whenToUse: 当任务涉及 RTL 设计与仿真验证两侧的分工、bug 归属判定、TB 与 DUT 交互约定、设计/验证文档交接时
---

# 设计-验证协作规范

适用于 RTL 设计与仿真验证（DV）由不同角色/工程承担的项目。核心原则：
**绝对隔离、文档沟通、证据交接**。

## 1. 职责边界（绝对隔离）

- 设计侧：只修改 RTL 与设计文档；**不允许修改 sim/ 验证平台的任何文件**
  （TB、参考模型、用例、脚本、回归配置）。
- 验证侧：**不允许阅读 RTL 源码内容，不允许修改 RTL**；以黑盒方式、仅依据
  接口与功能文档搭建验证环境。验证侧**不做 RTL 分析**：RTL 分析本质是设计
  侧职责（设计文档应是其文字化）。
  - **唯一例外**：无设计文档且无设计角色可问时（如单人项目），验证侧允许
    读 RTL，但所得结论一律标注为"推断"，逐条登记进 `question.yaml`
    （`source: rtl_inference`，默认 blocking=true），待设计口径确认后关闭。
- **唯一豁免目录——`rtl/sim/`（验证专用仿真模型）**：该路径下的 RTL 级
  文件（行为模型、黑盒替代物，如 p380_model.sv）仅供验证使用，**验证侧
  可以查看与修改**；可综合设计代码不放此目录。
- 跨侧访问唯一许可：**用户显式指定的文件，且只读不改**；读后结论落入文档，
  不在对方侧留任何改动。

## 2. 工程结构（定稿，后续工程一律按此）

```
<proj>/
├── rtl/        # RTL 相关统一收此目录，内部三段分角色：
│   ├── design/ # 可综合设计代码（设计侧独占）
│   ├── sim/    # 验证专用仿真模型（行为模型/黑盒，验证侧可查看可修改）
│   └── ref/    # 复用库单元 / vendor IP（工程自有库单元入库；vendor IP 通常 gitignore）
├── sim/        # 验证平台（TB/参考模型/用例/flist，验证侧独占）
├── doc/        # 全部设计文档与验证文档——双方沟通的唯一媒介
│   ├── md/     # 叙事文档（功能说明/架构设计/功能提问、bug 分析、报告），给人看
│   └── yaml/   # 四份交接契约（唯一事实源）：
│               #   spec.yaml / bug.yaml / gap.yaml / question.yaml
├── tools/      # 机检脚本（init 时拷入 / 工程自建）
├── migration/  # 工程迁移包专区（MIGRATION.md/migration-map.json/files/）
└── work/       # scratch/临时产物（gitignore）
```

新工程骨架用 `tools/init_project.py <工程根>`（本 skill 自带）创建：
幂等（已存在跳过，哪侧流程先触发都行），生成目录树 + .gitignore，
`--git` 可选建仓库。设计侧视角无缺失目录；图文件（drawio 等）放
doc/md 同目录，不单独设目录。

要点：文档全部集中 `doc/`（含架构图，不散放根目录）；仿真模型统一收
`rtl/sim/`、不放 `rtl/design/` 下，避免设计/验证文件混放；flist 中按
"rtl/design + rtl/ref + rtl/sim"三段组织
并注释各自角色；**工程迁移（导出/导入迁移包）一律调用 project-migration
skill**，迁移包固定放 `migration/`（gitignore），与 `work/` 的临时产物
分开；**流程规范类 skill 不放工程目录**，统一在用户级 skill 目录
（`~/.kimi-code/skills/`）维护，工程内不留副本。

## 3. 沟通方式（只通过文档）

- 设计 → 验证：《接口与功能说明》（端口信号、时序约定、行为假设、寄存器
  映射）。验证据此即可搭建环境，不看代码。
- 验证 → 设计：《bug 报告》——现象、复现用例、波形观察点、日志关键行。
- 设计回结论须带波形级证据；"疑似 TB 问题"同样要给完整证据链，不空口
  甩锅。
- **文档不清先提问**：文档描述可能不全或产生歧义，任一侧一旦认为文档不
  清楚/有缺口，**先提出问题、推动补充文档，再动手**；不允许按自己的猜测
  直接实现。

### 3.1 四份 YAML 交接契约（唯一事实源）

上述沟通的结构化载体固定为 `doc/yaml/` 下四份 YAML，Markdown 文档统一放
`doc/md/`、只是给人看的渲染层；两者冲突时以 YAML 为准并立即澄清。字段规范、状态机与反模式：

- **`spec.yaml`**（设计→验证）：接口/时序/契约/功能的权威输入，
  见 `references/spec.md`。版本纪律：任何接口变化必须升版并填
  change_summary，验证侧按版本 re-baseline。
- **`bug.yaml`**（验证→设计）：实现偏离规格。含环境指纹、复现
  case+seed、首个分歧点、波形观察点、有序证据链、TB 责任排除记录、
  四段复验，见 `references/bug.md`。
- **`gap.yaml`**（验证→设计）：规格本身缺失（功能遗漏）。含发现
  来源、缺失描述、设计 verdict 与落地回填（landed_func），见
  `references/gap.md`。
- **`question.yaml`**（双向）：待澄清假设逐条登记、逐条关闭，见
  `references/question.md`。

**缺失与歧义的分流**：规格"根本没写"→ `gap.yaml`；"写了但不清楚"
→ `question.yaml`；"实现不符合规格"→ `bug.yaml`。

**与两侧 skill 的分工**：本 skill 只定义交接规则与契约格式；
`design-flow` 负责设计侧文件（spec 等）的产出与自检；
`sim-flow`（验证侧维护）负责验证侧文件的产出。

**阻塞门禁**：`question.yaml` 中存在 `blocking: true` 且未关闭的条目时，
验证侧不得编写受其影响的 checker——先把问题发给设计侧。

## 4. TB↔DUT 采样相位纪律（#0.1 风格）

DUT 采用 `<= #0.1` NBA 风格时，输出在时钟沿后 0.1ns 才更新，由此产生
TB 与 DUT 之间固定的**一拍相位差**：

- 仿真器在沿后采样时刻（如 cocotb 的 `ReadOnly(T)`）读到的 DUT 输出是
  **刚结束那拍 [T-1,T)** 的值；而 TB 在沿后驱动的输入属于**本拍
  [T,T+1)**——两者相差一拍，直接配对判握手会在 ready 跳变沿产生幻影拍
  /丢拍（实测教训见 doc/bug定位与修复说明_20260814.md，Bug 1/2/4）。
- 判"沿 T 成交"的统一做法：DUT 输出（vld/ready/data）直接读即是该拍值；
  **TB 自驱动信号（valid/ready/载荷）须缓存一拍（`*_d1`）再配对**。
- driver 等 ready 的纪律：驱动一拍后等下一沿再采样 DUT ready——此时读到
  的才是"拍在总线上那一拍"的值；确认成交后再换下一拍/撤销。
- 参考模型（如存储模型）自身既驱动又采样时，同样遵守"自驱动量缓存一拍"
  原则。

## 5. bug 定位交接流程

契约字段与状态机见 `references/bug.md`，流程要点：

1. 验证侧达到 `reproduced` 门槛（固定 case+seed 稳定复现、`tb_exclusions`
   填完、`first_divergence` 定位到最早分歧）才允许提交；验证侧附的根因
   分析**仅作参考**；
2. 设计先看波形建立**物理总线事实**，**独立定根因**（不直接采信验证侧
   结论），再沿命令/数据通路逐级比对；
3. 判定归属写回 `design_response.verdict`（confirmed_dut / tb_issue /
   spec_ambiguity / cannot_reproduce），双侧问题各自改各自侧；判为文档
   口径的转 `question.yaml`；
4. DUT 修复：最小修复 + 编译级自验（lint/结构检查）；回执填
   `design_response`（根因/修改文件/影响范围/建议回归范围）——git 工程
   的提交号兼任 `backup_ref` 与 diff 记录（改动必入提交）。**设计侧自验
   不替代验证复验**；
5. 状态归属：设计侧**不宣布 bug 关闭**——fixed / regression_passed /
   closed 由验证侧按四段复验（原始复现→边界反向→相关回归→全回归）
   逐级推进填写。

## 6. 共同维护约定

- 本规范由设计与验证共同维护：任一侧发现协作问题（相位坑、文档缺项、
  口径冲突）都在此增补；
- 修改本规范需双侧（或用户）确认后生效。
