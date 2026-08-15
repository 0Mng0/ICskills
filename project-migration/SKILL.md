---
name: project-migration
description: 长上下文耗尽前，把旧工程的工作成果迁移到新工程并完成对接。Use when the user asks to 迁移工程/旧工程搬到新工程/换工程继续开发/长上下文不够了要换工程对接/导出迁移包/在新工程接续旧工程成果. 与 session-handoff（同工程跨会话）互补：本 skill 处理跨工程迁移——文件映射、选择性搬迁、依赖与路径差异 reconciliation、迁移后验证。
---

# Project Migration 工程迁移对接

## Overview

两个模式，解决同一个问题：长上下文工程要搬家，旧工程与新工程之间必须靠落盘的"迁移包"对接，不能靠聊天记忆。

- **export（导出）**：在旧工程执行。盘点要迁移的内容，生成迁移包（迁移清单 + 文件映射 + 决策记录 + 验证标准）。
- **import（导入/对接）**：在新工程执行。读迁移包，按映射落地文件，处理路径/依赖/版本差异，验证迁移结果后再继续开发。

典型场景：旧工程上下文太长装不下、重构另起新工程、换个干净的目录/仓库继续开发。

## 选择模式

| 用户意图 | 模式 |
|---|---|
| "把旧工程的成果整理出来，准备搬到新工程" | export |
| "这是新工程，旧工程的迁移包在这里，对接上" | import |
| 两者都有（同一轮里先导出再导入） | 依次执行 export → import |

## 快速步骤

### export（旧工程导出）

读 [references/export.md](references/export.md) 并按其清单执行。产出物（迁移包，默认放在旧工程根的 `migration-package/` 或用户指定位置）：

1. `MIGRATION.md`（复制 [assets/templates/MIGRATION.md.tpl](assets/templates/MIGRATION.md.tpl) 填写）：迁移范围、决策、遗留问题、验证标准；
2. `migration-map.json`（复制 [assets/templates/migration-map.json.tpl](assets/templates/migration-map.json.tpl)）：每个迁移项的旧路径 → 新路径 → 状态 → 验证方式；
3. 待迁移文件的归档（tar/zip 或按映射复制的文件树），不含 build 产物、依赖目录、密钥；
4. 旧工程最终 `git status` / `git log --oneline -10` 快照（写进 MIGRATION.md）。

### import（新工程对接）

读 [references/import.md](references/import.md) 并按其仪式执行，**在向用户汇报前不写新代码**：

定位迁移包 → 读 `MIGRATION.md` → 读 `migration-map.json` → 逐项落地文件并处理路径/依赖差异 → 更新每项状态 → 跑验证标准里的基线验证 → 汇报迁移结果、未落地项、差异决策。

## 核心规则

- 迁移只认落盘的迁移包：旧会话的聊天记录、口头说明都不算迁移依据。
- 迁移清单用 JSON（`migration-map.json`）而非纯 Markdown：逐项有状态，防止"以为搬完了"。
- 默认全部 `status: pending`；只有在新工程里实际落地且验证通过的项才置 `verified`。
- 选择性搬迁：不是什么都要搬。build 产物、node_modules/.venv、密钥、历史垃圾不迁；不确定的先问用户。
- 路径/依赖/版本差异必须显式记录决策（写回 MIGRATION.md 的"差异与决策"节），不做静默修改。
- 先验证迁移基线（能构建、能跑、冒烟测试过）再开始新功能开发。
- import 完成后先汇报，经用户确认后再动手写新代码。
