# 验证点表 vp_table.yaml

验证点是"要验什么"的最小单位。**每个 VP 五要素填齐才许动手写代码**；
填不齐的列暴露的正是没想清的地方，回去补 spec 或登记假设。

## 五要素

| 要素 | 含义 | 不合格示例 |
|---|---|---|
| stimulus 激励 | 怎么构造输入（定向序列/随机约束/非法图案） | "给点数据" |
| observation 观测 | 在哪个接口、哪个时刻看什么 | "看输出" |
| expected 期望 | 可判定的期望行为，引用契约条款号 | "结果正确" |
| checkers 检查器 | 由哪个 checker 判定（CHK-* ID） | 空 |
| tests 用例 | 由哪个 testcase 执行（TC-* ID） | 空 |

## 字段规范

```yaml
schema_version: 1
feature_groups:             # 按 spec 的功能/接口分组
  - { id: FG-INPUT, title: "输入接口" }
verification_points:
  - id: VP-IN-BACKPRESSURE  # VP-<组>-<名>
    feature_group: FG-INPUT
    priority: P0            # 沿用 spec 里 function 的优先级
    source: SPEC-xxx v0.3 #IF-IN contract[1]   # 出处：契约条款号必填
    title: "反压期间 valid/data 保持"
    stimulus: "driver 发数据，随机拉低 ready 制造反压"
    observation: "IF-IN 握手拍，monitor 采样 valid/data"
    expected: "反压期间 valid 与 data 不变（contract[1]）"
    checkers: [CHK-IN-HOLD]
    tests: [TC-IN-BP-RAND]
    status: open            # open → implemented → passing → closed | blocked
    blocked_by: []          # 引用 BUG-*/QUE-*，阻塞原因可追踪
```

## 规则

1. VP 必须有出处（`source` 引用契约条款）；自己加的风险类 VP，
   `source: verification_risk` 并写明理由。
2. 一个 VP 可挂多个 checker/testcase；一个 testcase 可覆盖多个 VP，
   但每个 VP 至少要有一个 testcase。
3. `status: closed` 的前提：对应 checker 已证伪验证（反向用例能抓错）、
   用例在最近回归中 pass。
4. blocked 的 VP 不许静默搁置：`blocked_by` 必须引用具体 BUG-*/QUE-*。
5. 接口升版（spec version 变化）后，按 change_summary 重审
   受影响 VP，状态回退到 open。
