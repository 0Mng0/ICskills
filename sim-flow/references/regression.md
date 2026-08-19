# 回归与覆盖率

## 回归判定：看日志实质，不看退出码

进程退出 0 ≠ 通过。每条用例的日志按四态分类：

| 状态 | 判定 |
|---|---|
| pass | 有正常结束标记（cocotb 打印测试总结/Shutting down），且无失败模式 |
| fail | 日志出现 assert 失败、Traceback、checker 报警、scoreboard 残留 |
| incomplete | 无失败模式但也无结束标记（挂死/被杀/超时兜底触发） |
| interrupt | 外部中断（OOM、手动 kill） |

fail 优先于 incomplete（先查错再查全）。任一用例 fail，回归整体非零退出。

## 失败处理纪律

1. **先固化现场**：保留日志、波形、seed、环境信息，再动任何东西；
2. **先复现**：用原 case + 原 seed 重跑，复现不了先查环境（工具版本、
   参数差异），不许在不可复现的失败上猜；
3. **定位最早分歧**：从第一个 mismatch 往前追，不在级联错误里打转；
4. **归属判定**：TB 问题自己改；疑似 DUT 问题按 `doc/yaml/bug.yaml`
   交接（填齐复现、首个分歧、证据链、TB 排除记录）；文档口径问题转
   `question.yaml`；
5. **修复后复验**：TB 修复重跑原 case + 回归；DUT 修复走 bug.yaml 的
   四段复验（原 case → 边界/反向 → 相关回归 → 全回归）。

## 覆盖率

- 功能覆盖率采在 **monitor（实际接受的事务）**，不采 driver（生成意图）。
- Verilator 行/翻转覆盖率：`--coverage` 编译，每用例归档 coverage.dat，
  回归后 `verilator_coverage` 合并。
- **覆盖洞先分类，再行动**：

  | 分类 | 动作 |
  |---|---|
  | 缺激励 | 补定向用例或加随机约束 |
  | 采样错 | 修 monitor/coverage 采样点 |
  | 约束阻挡 | 检查随机约束是否过严 |
  | 被 BUG 阻塞 | 关联 BUG-*，等修复 |
  | 不可达/超范围 | 写 waiver：原因 + 风险 + 依据，留痕 |

- waiver 必须写明理由，不许为了数字好看删 bin、削 checker。

## 回归产物清单（每轮回归必须留下）

- 每用例：日志（名带 seed）、（调试时）波形；
- 汇总：通过/失败/未完成计数，未解释失败列表（必须清零或全部转
  BUG/假设）；
- 环境指纹：DUT 版本（commit/哈希）、TB 版本、工具版本；
- 以上摘要更新进 `sim/status.yaml`（见 status-tracking.md）。
