# gap.yaml —— 验证→设计 功能遗漏交接契约

验证侧报告"规格缺了内容"的**唯一格式**。与 bug 的分工：

- **bug**：实现偏离了规格（修 RTL）；
- **gap**：规格本身缺失（改规格）——典型来源是验证侧独立提取
  功能点时发现"文档/契约全篇没有某需求行为"（B 层反向提取）。

与 question.yaml 的边界：**"根本没写"→ 本文件（缺失）；
"写了但不清楚"→ question.yaml（歧义）**。

## 状态机与权限

```
验证侧:  open → proposed（补齐证据后提交设计）
设计侧:  verdict: accepted / rejected / deferred / duplicate
          accepted  → 承诺纳入 spec 某版本
                    → 落地后回填 landed_func/landed_version → closed
          rejected  → 写明理由 → 验证 acknowledged → closed
          deferred  → 写明再议时机（挂起，不算关闭）
          duplicate → 指向已有 FUNC-id / GAP-id → closed
```

- **状态修改权限**：open/proposed 由验证侧写；verdict/rationale/target_version/
  landed_* 由设计侧写；closed 按路径分：accepted 路径设计侧落地后关，
  rejected 路径需验证侧 acknowledged 后关，deferred 挂起不关。
- **闭环门禁**：verdict=accepted 必须填 `target_version`；工具到期检查
  该版本 spec 是否存在 `landed_func` 对应条目——**承诺未兑现
  自动报警**。rejected 未获 acknowledged 不得 closed（防单方面关门）。

## 字段规范

```yaml
schema_version: 1
gaps:
  - id: GAP-001
    title: "缺：复位中途来交易的行为定义"
    status: proposed
    opened_by: <验证侧署名>
    opened_at: 2026-08-19

    source:                        # 怎么发现的——可追溯起点
      kind: independent_extract    # independent_extract(B层独立提取) |
                                   # requirement(需求新增) | review(评审) |
                                   # test_escape(验证发现规格外行为)
      req_ref: "需求文档 §3.2"      # kind=requirement 时必填
      note: "独立提取功能点时，文档全篇无复位中途交易的描述"

    description:
      missing: "期望规格定义的行为（可判定语句，可观测）"
      why_needed: "系统/协议/需求依据；没有它验证无法判定什么"
      suggested_func: "建议的 FUNC 草案（供设计参考，非强制）"

    impact:
      blocks_verification: true    # 是否阻塞相关 checker 编写
      affected_area: "复位/异常路径"

    design_response:               # ↓↓↓ 设计侧填写 ↓↓↓
      verdict: accepted            # accepted|rejected|deferred|duplicate
      rationale: "采纳/拒绝/挂起理由"
      target_version: "SPEC-hmc v0.4"   # accepted 必填：承诺纳入的版本
      landed_func: ["FUNC-051"]          # 落地后回填：spec 中的条目
      landed_version: "SPEC-hmc v0.4"
      duplicate_of: ""                   # duplicate 时指向 FUNC-id 或 GAP-id

    discussion:                    # 往返记录，谁写谁署名
      - { date: 2026-08-19, who: 验证侧, note: "提交遗漏" }
```

## 反模式（双方都不得做）

- 验证侧：把"实现 bug"当遗漏提（实现偏离规格走 bug.yaml）；把歧义
  当缺失提（写得不清楚走 question.yaml）；不提 blocks_verification
  就要求设计优先处理。
- 设计侧：accepted 不填 target_version；升版后不回填 landed_func；
  rejected 不给可复查的理由。
