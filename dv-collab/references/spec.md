# spec.yaml —— 设计→验证接口与功能契约

验证侧搭建环境的**唯一权威输入**。黑盒纪律下，验证只看本文件 + 设计叙事文档，
不看 RTL。本文件是结构化事实源；叙事文档（架构图、设计思路）仍是给人看的
必要补充，两者冲突时以本文件为准、并立即向设计侧提出澄清（写进
`question.yaml`）。

## 总规则

1. **版本纪律**：接口信号、协议契约、功能行为任何变化必须升 `version` 并填
   `change_summary`；验证侧按版本 re-baseline（决定哪些用例需要重跑）。
   不许"悄悄改"。
2. **可判定性**：每条契约/功能必须写成可判定的语句，并给出可观测点。
   "工作正常""尽量快"这类表述不合格，验证侧有权拒收并退回。
3. **原子接口四要素**：每个接口必须同时具备——信号表、时钟复位归属、
   协议契约、时序约定。缺一项视为文档缺口，转 `question.yaml`。
4. **非法输入必须定义**：越界/非法激励下 DUT 的约定行为（忽略/截断/报错/
   未定义）必须写明；"未定义"也是合法答案，但验证侧将不对其做功能判定。
5. 设计侧自己未定的点，直接列入 `open_questions`，由验证侧登记为假设。

## 字段规范

```yaml
schema_version: 1
doc:                          # 文档元信息
  id: SPEC-<模块名>           # 唯一 ID，bug/question 引用它
  title: <模块接口与功能说明>
  version: "0.3"              # 语义化版本：接口/契约/功能变化必须升版
  stage: draft | req_confirmed | arch_reviewed | confirmed
                          # 流程门位置（design-flow §2 阶段状态机），每次过门
                          # 更新；版本取代由 supersedes 链表达，不单设 status
  commit_id: "<最近一次过门独立提交的 git 哈希>"
  author: <设计侧署名>
  date: 2026-08-15
  source_docs:                # 叙事文档原件及其指纹（YAML 不替代文档）
    - { path: doc/md/xxx设计说明.md, sha256: "<可后补>" }
  supersedes: "SPEC-<模块名> v0.2"    # 版本链，首版省略
  change_summary:             # 相对上一版改了什么，逐条列；验证侧据此定回归范围
    - "IF-IN 增加 backpressure 契约第 3 条"

module:
  name: <模块名>
  top: <顶层模块名>
  parameters:                 # 影响行为的参数都要列
    - { name: DATA_W, default: 32, range: "8~64", desc: "数据位宽" }

clock_reset:                  # 时钟复位域，多时钟必须逐个列
  - { name: clk, freq: "100MHz", edge: posedge }
  - { name: rst_n, type: async_low, release: sync, min_cycles: 2 }

interfaces:                   # 原子接口列表
  - id: IF-IN                 # 接口 ID，被 functions/bug 引用
    role: slave               # DUT 视角：本接口 DUT 是 master 还是 slave
    clock: clk
    protocol: valid-ready     # 标准协议写名字；自定义写 custom 并在 contract 附完整时序
    signals:
      - { name: in_valid, dir: in,  width: 1,  desc: "输入有效" }
      - { name: in_ready, dir: out, width: 1,  desc: "输入就绪" }
      - { name: in_data,  dir: in,  width: 32, desc: "输入数据" }
    timing:
      sample_edge: posedge    # 采样沿
      nba_style: "#0.1"       # DUT 若用 <= #0.1 风格必须标明，
                              # 触发 SKILL.md 第 4 节的采样相位纪律
    contract:                 # 协议契约：可判定语句，逐条编号引用
      - "valid 拉高后，ready 为低期间 valid 与 data 必须保持不变"
      - "不允许 valid 依赖 ready 的组合路径（防死锁）"
    backpressure: "允许任意拍反压；最大连续反压不限"
    illegal_inputs:
      - { pattern: "valid 期间 data = X", behavior: "视为忽略，不锁存" }
      - { pattern: "复位期间拉高 valid", behavior: "未定义" }

functions:                    # 功能行为清单（验证点表的直接来源）
  - id: FUNC-001
    title: "非对齐请求在缓存行边界拆分"
    preconditions: "已复位，IF-IN 空闲"
    trigger: "IF-IN 收到 addr 非 64B 对齐且跨边界的请求"
    expected: "IF-OUT 依次发出两段，首段结束于边界，次段起始于边界"
    observable: "IF-OUT 的 addr/len 事务序列"
    priority: P0              # P0 基本功能 / P1 重要场景 / P2 边角

registers:                    # 无寄存器模块整节省略
  - name: CTRL
    offset: "0x00"
    access: RW
    reset: "0x0"
    fields:
      - { name: enable, bits: "[0]", desc: "全局使能" }

out_of_scope:                 # 明确本模块不负责的行为，防验证越界
  - "不检查输入数据的协议上层含义"

open_questions:               # 验证提问闭环台账：影响本 spec 且未关闭的 QUE-id
                              #（QUE 生命周期与闭环判据见 question.md；
                              #  设计侧假设走 doc/md 功能提问文档，不入此段）
  - "QUE-003：影响 IF-IN 间隔约定，待设计侧答复"
```

## 验证侧验收清单（收到后先过一遍再动手）

- [ ] version/stage/commit_id/change_summary 齐全，且与上版 diff 能对上
- [ ] 每个接口四要素齐全；`nba_style` 已确认
- [ ] 每条 contract / function 都是可判定语句且有可观测点
- [ ] illegal_inputs 无遗漏（至少显式写过"未定义"）
- [ ] open_questions 闭环对照：status=open 且影响 spec 的 QUE 均在台账；
      台账 QUE-id 在 `question.yaml` 中存在；已 confirmed 的 QUE 已从台账移除
