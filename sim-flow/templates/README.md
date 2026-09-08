# sim-flow 平台模板（示例工程 smoke 全绿后固化的通用骨架）

来源：一个真实工程 smoke 全绿的工作平台（cocotb 2.0.1 + Verilator 5.050 +
Windows/MinGW，#0.1 NBA 风格 DUT），已剥离工程专属内容。本目录是**可套用的
文件集**，由 `tools/init_sim.py` 拷入新工程 `sim/` 并渲染工程名，人工再按
目标工程 spec 适配下列各点。

## 搭建步骤（新工程）

```bash
python <skill>/tools/init_sim.py <工程根> [--module M] [--toplevel T] [--venv]
cd <工程根>/sim && source env.sh        # --venv 已自动建环境则跳过下一步
# 否则手动：python -m venv .venv && pip install cocotb==2.0.1 pyyaml \
#   && COCOTB_SRC=<cocotb 源码树>/src/cocotb bash tools/build_native_mingw.sh
cd run && python regress.py --build-only   # 先编译，核对 Vtop.h 顶层端口
python regress.py --case smoke
```

## 各文件适配点（拷入后必查）

| 文件 | 通用部分（免改） | 适配点（按目标 spec 改） |
|---|---|---|
| `env.sh` | 结构（自定位 venv） | 标 ★ 的本机路径（Python/MSYS2 安装目录） |
| `tools/build_native_mingw.sh` | 全通用（自定位 venv/Python 版本） | 运行时传 `COCOTB_SRC` 环境变量 |
| `run/regress.yaml` | 结构/构建参数 | init_sim 已渲染 module/toplevel；build_args 视工程增减 |
| `tb/clocks.py` | NBA_PS=100 相位纪律、drive_slot | 时钟名/周期、复位信号名与域数 |
| `tb/axi.py` | arw/W/R/B driver/monitor/ReadyCtrl/TxnGen 全套 | 信号名（s_arw_*/s_axi_*）、头注协议假设逐条对照目标 spec、TxnGen 约束（granu/addr_max/独占规则） |
| `tb/apb.py` | ApbDriver（标准两拍 APB） | 寄存器地址表/区域划分（按 spec registers 段定义） |
| `tb/ref_model.py` | 字节级存储 + 期望队列 + ExclMon 框架 | 保序/独占/resp 语义逐条对照目标 spec 推导（参考模型红线：只从 spec） |
| `tb/scoreboard.py` | R/B 逐拍比对、错误收集制 | 一般免改 |
| `tb/env.py` | SimEnv 装配/drain/finish 模式 | drive_input_defaults 端口表、组件增减（有下游从机模型时在此装配） |
| `tests/test_smoke.py` | smoke 结构（端口→复位→CSR→最小数据通路） | EXPECTED_PORTS 表（先 `--build-only` 对齐 Vtop.h）、CSR 复位值、数据通路激励 |

下游从机行为模型（如 PHY/存储模型）属工程专属组件，模板不提供——按
`references/platform-build.md` 的采样纪律自行编写，在 `tb/env.py` 装配。

## 纪律提醒（套用不豁免）

- 黑盒：拷入后只按 spec.yaml 接口段适配信号名；不对齐就先编译看 Vtop.h
  （接口三级第 2 级），仍不一致登记 question.yaml；
- 采样相位：驱动一律 `drive_slot`（沿后 +0.1ns），采样一律
  `RisingEdge + ReadOnly`——改驱动方式必须重推配对（见 tb/axi.py 头注）；
- monitor 采样才是"实际接受"，driver 意图不算数；
- smoke 不过不写正式用例；smoke 首 bug 先查配对相位与信号名。
