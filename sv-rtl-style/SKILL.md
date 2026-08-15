---
name: sv-rtl-style
description: SystemVerilog RTL 代码风格规范，生成或修改 RTL 代码时必须遵循；涵盖文件结构、时序 #0.1、always 块拆分、generate for 寄存器组、显式位宽、组合逻辑、例化对齐、命名习惯、注释风格等通用规则
whenToUse: 当用户要求编写、修改或 review SystemVerilog/Verilog RTL 代码时
---

# SystemVerilog RTL 代码风格规范

通用 RTL 编码风格，生成或修改 SystemVerilog 代码时遵循。

> 新增条目为既有实践的文档化整理，现有代码（hmc_v2/rtl_v3 等）已遵循，
> 新增内容不需要修改既有代码。

## 1. 文件结构

- **不在文件内写 `` `timescale ``**：由编译时统一指定（编译选项/filelist），避免编译顺序导致 timescale 不可控。
- 一个文件一个 module；文件名与模块名一致。
- 文件头注释块：`File / Module / Description` + 功能说明。
- **不使用 include guard**（`ifndef/`define），由 filelist 管理编译。
- 功能块用编号注释分区（如 F1/F2…、R1/R2…、L1~L7），块间 `//=====` 分隔线。

## 2. 时序逻辑

- **非阻塞赋值一律加 `#0.1`**：`q <= #0.1 next;`。
- **always_ff 拆分原则**：控制条件相同的寄存器归一组；控制逻辑不同的寄存器各用一个 always 块，块前注释该寄存器用途。拆分时必须保持原优先级（例：load 优先于 pop 时，else-if 链里 load 在前）。
- **逐表项/逐字节更新的寄存器组，用 generate for 展开为独立 always_ff，不用单进程 for 循环写子元素**：Verilator 5.050 `--timing` 下，单进程 for 循环内 `<= #0.1` 写向量子元素/位选择/非压缩数组元素，只有末次迭代生效（其余静默丢失，已玩具用例复现证实）；generate 展开后每进程每拍只调度一次常量索引的延迟赋值，绕开该缺陷，且对 DC/VCS/SpyGlass 均为标准可综合写法。always_comb 内的 for（阻塞赋值、无 `#0.1`）不受此限，可继续用。
  - 多个 generate 进程各写同一 packed 向量的不同 bit：Verilator 功能正确，但 lint 可能报多驱动——表项为向量时优先非压缩数组（每元素一个变量），bit 级标志向量可保持 packed。
  - genvar 常量索引可消解原循环内的下标选择逻辑（如按相位 mux 下标），改写时注意利用。
- 异步复位 `negedge rst_n`，复位值显式位宽。
- 状态机拆成"状态寄存器一块（完整 case，只管跳转）+ 数据寄存器各一块"。

## 3. 常量与位宽（禁止隐式位宽 `'0`/`'1`）

- 参数化位宽：`{ADDR_W{1'b0}}`、`{DATA_W{1'b0}}`；
- 固定小位宽：`1'b0`、`4'b0`、`8'b0`；
- 常量参与运算用显式 cast：`ADDR_W'(1)`、`ADDR_W'(32)`；
- 比较同样显式：`sig == {STRB_W{1'b0}}`，不写 `sig == '0`。

## 4. 组合逻辑

- `always_comb` 用阻塞赋值，先给默认值再 `case`（防 latch）。
- **always_comb 按功能拆分**：不同控制逻辑分不同块（与 always_ff 拆分同一原则）；只含简单表达式的信号直接 `assign`，不进 comb 块。
- `wire` 允许声明即赋值：`wire a = b & c;`（等价于先声明后 assign）。
- **禁止 `logic a = b & c;`**——那是 t=0 初值不是连续赋值，会藏 bug。

## 5. 例化格式

- 参数（`#(...)`）一行一个；端口连接一行一个；
- `.` / 端口名 / `(` / 连接信号 / `)` 按列对齐（列宽按实例最长名，约 20 字符）；
- 端口分组间加分区注释行（如 `//---- native 读命令 → router ----`）；
- 空接输出写 `.almost_full(  )` 形式，括号列保持对齐。

## 6. 命名

- **`_q`**：寄存器输出（flip-flop Q 端）——由 `always_ff` 驱动，综合出 FF，跳变对齐时钟沿；
- **`_c`**：组合逻辑信号（combinational）——由 `assign`/`always_comb` 驱动，周期内可能毛刺；
- **`_n`**：低有效信号（如 `rst_n`）；
- 用途：读代码/波形时立刻知道时序性质；名字与实现不符（`_q` 不是寄存器、`_c` 推出 latch）即为风格违例，review 必查。
- **存储结构一律叫 fifo**（rcmd_fifo / wcmd_fifo / rfifo / bfifo / rd_fifo / flag FIFO / b FIFO），不用 `*_buf`；深度参数 `*_FIFO_DEPTH`。
- 配置信号短缩写：`cfg_granu`（不用 granularity 全拼），同类缩写保持简短。
- 时钟复位：顶层 `clk`/`rst_n`；子时钟域 `<域>_clk`/`<域>_rst_n`（如 `smc_clk`/`smc_rst_n`）。
- 打拍/skid 功能直接例化 avr 单元（avr_rs/avr_frs），信号与实例不自称 skid。

## 7. 注释与文档风格

- 注释用中文，说明"为什么"而非复述代码；代码、信号名用原文。
- **模块头部注释块按序组织**：`File/Module/Description` → 【微架构】（一段话讲清数据通路与关键决策）→ 【功能块】编号列表 → 【连接关系】简图 → 【命名原则】（信号多的大模块才需要）→ 【接口格式 / 地址映射 / 行为假设】（按模块需要，假设用 ①②③ 编号）→ 【依赖】。
- **连接关系简图**：文字箭头即可，按通路分开画（如命令下行 / 读返回 / 写响应），不追求框图美观。
- **关键控制信号的注释放在定义/使用处**：逐行说明功能与所属功能块；**不做集中式信号速查表**（与实现两处维护易失步，已否决）。
- 待确认/占位事项在注释中明确留痕（"待厂商确认""占位"），并同步进设计文档的开放问题清单。

## 8. 其他通用建议

- `case` 必写 `default`；状态机状态用 `typedef enum logic [N-1:0] {...}`。
- 模块对外参数用 `parameter int`，模块内部派生常量用 `localparam int`。
- `always_comb` 内的 `for` 循环变量用 `int`（或块外 `integer`），函数一律 `automatic`；always_ff 内不写 for 循环——寄存器组按 §2 用 generate for 展开。
- `generate for` 的 begin 块命名（`begin : g_xxx`），便于层级引用与调试。
- 可综合代码不用 `initial`、不用 `#` 延迟（`#0.1` 赋值风格除外）、不用 `forever/while`。
- 复位只出现在时序块敏感表与复位分支，数据路径不混用同步/异步复位。
- 跨时钟域信号必须经过专用 CDC 单元（异步 FIFO/同步器），禁止直接跨域。
- FIFO/存储一律例化库单元，不手写环形缓冲。
- 常数除法（如 ÷5/mod 5）先用 `/`、`%` 表达，并注释"时序不收则换 magic multiply"。

## 9. 协作约定

- 代码修改只在用户明确要求时进行；讨论阶段不动代码。
- git 提交（及任何 git 变更）只在用户明确要求时执行。
