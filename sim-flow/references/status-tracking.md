# status.yaml —— 验证状态追踪

`sim/status.yaml` 是验证侧的状态账本：**当前验到什么程度，看文件，不靠记忆**。
每次回归后更新；跨会话、换班、过段时间回来，先读它和 vp_table.yaml。

## 字段规范

```yaml
schema_version: 1
module: <模块名>
spec_baseline: "SPEC-xxx v0.3 @<commit_id>"  # 当前验证依据的契约版本+过门
                                   # 提交（取自 spec doc.version/doc.commit_id，
                                   # doc.stage 应为 confirmed）
dut_baseline: "<rtl commit/哈希>"    # 当前被测 RTL 版本
updated_at: 2026-08-15

vp_summary:                          # 与 vp_table.yaml 一致的计数
  total: 12
  open: 3
  passing: 7
  closed: 1
  blocked: 1

last_regression:
  date: 2026-08-15
  command: "make regress"
  total: 9
  pass: 8
  fail: 1
  incomplete: 0
  coverage:                          # 有则填，没有整节省略
    functional: "62%"
    line: "78%"

unexplained_failures:                # 未解释失败列表：必须清零或全部转 BUG/ASM
  - { testcase: tc_rand_bp, seed: 777, log: "logs/tc_rand_bp_seed777.log",
      note: "反压下偶发丢拍，定位中" }

open_issues:                         # 进行中的交接事项
  bugs: [BUG-002]                    # 引用 doc/yaml/bug.yaml
  question_blocking: [QUE-003]    # 引用 doc/yaml/question.yaml

next_actions:                        # 下一步打算，供会话恢复时接续
  - "补 IF-OUT 边界定向用例"
```

## 规则

1. **每次回归后必更新**：last_regression、vp_summary、unexplained_failures。
2. `unexplained_failures` 是硬性清单：里面的条目要么在定位中（写明进展），
   要么已转 BUG-*/QUE-* 并从清单移除；不允许无限期挂着没有下文的条目。
3. `spec_baseline` 与 spec 版本绑定：契约升版后先更新它，
   并按 change_summary 重审受影响 VP（vp_table 状态回退 open）。
4. 本文件只记状态，不记结论细节；细节去 vp_table.yaml / bug.yaml /
   回归日志里查。
