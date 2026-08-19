# 平台搭建：组件职责与固定顺序

cocotb 平台的组件划分借鉴 UVM 的角色分工，但保持 Python 的轻量：
不搞 factory/phase 那套重机制，每个组件就是一个 Python 类/协程。

## 固定搭建顺序

```
interface 封装 → driver → monitor → 参考模型 → scoreboard → smoke
```

每步跑通再进下一步；不一次写完全部再调。

## 各组件职责

**1. interface 封装**
- 把 DUT 信号按 spec 的原子接口分组，封装成对象（信号引用 +
  时钟沿助手），driver/monitor 只跟它打交道，不直接碰 `dut.xxx`。
- 信号名、位宽、方向必须与 spec.yaml 的 signals 表一致；
  发现文档与实物不符，登记假设并提问，不擅自对齐。

**2. driver**
- 职责：把事务（transaction）按协议契约驱动到接口上。
- 纪律：驱动一拍后等下一沿再采样握手信号（相位纪律见 dv-collab 第 4 节）；
  自驱动信号需要配对判定时，缓存一拍（`*_d1`）。
- 只负责"按契约发"，不负责判断对错——对错是 checker 的事。

**3. monitor（最重要，最先写对）**
- 职责：在**握手成交拍**采样，把总线上实际发生的事还原成事务。
- 纪律：**"实际接受"以 monitor 采样为准**，driver 侧的发送意图不算数
  （反压会丢弃意图）。覆盖率采样、scoreboard 配对、协议检查全部基于
  monitor 输出。
- monitor 是被动的：只采样，不驱动。

**4. 参考模型（refmodel）**
- 职责：吃 monitor 采到的输入事务，按 spec 的功能条款算出
  期望输出。行为级描述，不关心 DUT 内部实现（验证侧也看不到 RTL）。
- 纪律：只从契约推导；契约没写的，登记假设，不自由发挥。

**5. scoreboard**
- 职责：配对比较——refmodel 的期望队列 vs monitor 采到的实际输出。
- 必备功能：顺序/ID 配对规则明确；仿真结束时检查**队列残留**
  （有期望没出来的、有实际没期望的，都算失败）；比较失败时打印
  事务全文与仿真时间。

**6. smoke 用例**
- 最小激励打通"driver → DUT → monitor → refmodel → scoreboard 比对"
  全链路。smoke 不过，后面一切都是空中楼阁。

## 目录与日志纪律

- 每个用例日志带用例名；随机用例日志名带 seed：`logs/<case>_seed<N>.log`。
- 波形默认不 dump，调试时开，输出 `waves/<case>_seed<N>.fst`。
- 任何协程的等待必须有超时兜底，死等 = incomplete，不许挂死整轮回归。
