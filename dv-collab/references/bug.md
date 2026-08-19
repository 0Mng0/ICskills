# bug.yaml —— 验证→设计 BUG 交接契约

验证侧提交 BUG 的**唯一格式**。设计侧依据它定位，验证侧依据它复验关闭。
核心纪律：**证据交接**——每条结论后面必须挂可复查的证据（日志行号、波形
位置、契约条款号），空口结论设计侧有权退回。

## 状态机与权限

```
验证侧:  open → reproduced ──提交──▶ 设计侧
设计侧:  判 verdict: confirmed_dut / tb_issue / spec_ambiguity / cannot_reproduce
              │ confirmed_dut → 修复（必须先备份）
验证侧:  fixed → regression_passed → closed   （四段复验逐级推进）
任意态:  rejected / not_a_bug / deferred      （必须带证据，不许空判）
```

- **状态修改权限**：open/reproduced 由验证侧写；verdict/root_cause 由设计侧
  写；fixed 之后的四段复验结果与 closed 由验证侧写。互不越权。
- **提交门槛**：达到 `reproduced` 才允许提交设计侧——即已用固定
  case+seed 稳定复现，并填完 `tb_exclusions`（排除 TB 责任）。
- **首个分歧原则**：`first_divergence` 必须是最早偏离契约的点，不是最后
  的级联错误。找不到最早分歧 = 还没定位完，不许提交。
- **spec_ambiguity 分流**：判定为文档歧义时不算 BUG，转 `question.yaml`
  推动文档补充，本单以 `deferred` 挂起。

## 字段规范

```yaml
schema_version: 1
bugs:
  - id: BUG-001
    title: "相邻任务尾拍元数据未保持"
    severity: blocker | major | minor | trivial
    status: reproduced
    confidence: reproduced          # suspected → reproduced → confirmed_dut
    opened_by: <验证侧署名>
    opened_at: 2026-08-15

    environment:                    # 复现环境，缺一项都可能复现不了
      rtl_revision: "<git commit 或 sha256>"
      tb_revision: "<git commit 或说明>"
      tool: { sim: "verilator 5.x", cocotb: "2.0.1" }
      spec_ref: "SPEC-<模块名> v0.3"   # 判定依据的契约版本

    reproduce:
      testcase: tc_idma_tail
      seed: 12345                   # 随机用例必填真实 seed；定向用例写 fixed
      run_command: "make tc_idma_tail SEED=12345"
      log: "logs/tc_idma_tail_seed12345.log"
      frequency: always             # always | "intermittent: 约 1/20"
      waveform: "waves/tc_idma_tail_seed12345.fst"   # 无波形必须说明原因

    first_divergence:               # 最早分歧点
      sim_time: "1250 ns"
      point: "IF-OUT 第 3 个事务"
      expected: "依据 SPEC v0.3 FUNC-007：尾拍应携带上一任务元数据"
      actual: "尾拍元数据被清零"
      spec_clause: "FUNC-007"       # 必须引用契约条款号，不许自由发挥

    waveform_evidence:
      window: [1100, 1400]          # ns，观察窗口
      watch_signals:                # 波形观察点：设计侧按此清单看波形
        - "tb.dut.if_out.valid"
        - "tb.dut.if_out.payload.meta"

    evidence_chain:                 # 有序证据，每条可独立复查
      - { type: log_line, ref: "logs/tc_idma_tail_seed12345.log:87",
          note: "scoreboard 首个 mismatch" }
      - { type: waveform, ref: "waves/...fst @1250ns",
          note: "meta 在尾拍清零" }
      - { type: spec_clause, ref: "SPEC v0.3 FUNC-007",
          note: "期望行为出处" }

    tb_exclusions:                  # 排除 TB 责任的检查记录（防甩锅也防背锅）
      - "driver 发送内容已与日志核对一致（log:45-60）"
      - "相位纪律已按 SKILL.md 第4节检查，配对使用 *_d1 缓存"
      - "同激励下参考模型输出与契约条款一致"

    impact:
      blocked_items: [VP-IDMA-TAIL, TC-IDMA-TAIL]   # 被本 BUG 阻塞的验证点/用例
      note: "仅阻塞尾拍相关 VP，其余回归照常"

    design_response:                # ↓↓↓ 设计侧填写 ↓↓↓
      verdict: confirmed_dut        # confirmed_dut|tb_issue|spec_ambiguity|cannot_reproduce
      root_cause: "<根因，含 RTL 位置>"
      analysis_evidence:            # 设计侧分析证据（波形级事实优先）
        - "waves/...fst @1250ns：状态机停留在 S_HOLD"
      fix:
        files: ["rtl/xxx.sv"]
        backup_ref: "<git commit / 备份目录>"   # 修复前必须先备份
        diff: "<统一 diff 或文件路径>"
        sha256_before: "..."
        sha256_after: "..."
      note: |

    verification:                   # ↓↓↓ 验证侧四段复验，逐级填 ↓↓↓
      original_case: pass           # 原始用例 + 原 seed 复现通过
      boundary_negative: pass       # 边界/反向场景
      related_regression: pass      # 相关用例回归
      full_regression: pass         # 全回归
      note:

    discussion:                     # 往返记录，谁写谁署名
      - { date: 2026-08-15, who: 验证侧, note: "提交复现" }
```

## 反模式（双方都不得做）

- 验证侧：只给"过不了"不给首个分歧；不记 seed；不填 tb_exclusions 就提交。
- 设计侧：不看波形直接猜根因；修复不备份不留 diff；把 bug 降级成
  not_a_bug 但不给证据。
- 双方：用即时消息/口头交接代替本文件——谈完也必须回填 `discussion`。
