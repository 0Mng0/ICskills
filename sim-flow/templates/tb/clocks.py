# =============================================================================
# tb/clocks.py — 时钟与复位（示例为双域：数据面 clk + 管理面 apb_clk；
# 时钟名/周期/复位信号名/域数按目标 spec.yaml clock_reset 段适配）
# 示例约定：复位均为低有效异步复位、同步释放；TB 同时拉低/释放（无顺序要求）。
# =============================================================================
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge

CLK_NS = 2.5        # clk      400MHz（示例值，按 spec 改）
APB_CLK_NS = 4.0    # apb_clk  250MHz（示例值，按 spec 改）

# 适用于 DUT 全链路 `<= #0.1` NBA 风格（spec timing.nba_style）：输出在时钟沿后
# 0.1ns 才更新。TB 驱动必须在沿后 +0.1ns 落地（此刻 DUT 新输出已就位，且距
# 下一沿采样足够远）；cocotb 2.0.1 禁止 ReadOnly→ReadWrite 转换，故用 Timer
# 而非 ReadWrite 触发器。依据：dv-collab §4 + #0.1 NBA 风格 DUT 实测。
NBA_PS = 100        # 0.1ns = 100ps（timescale 1ns/1ps 可表达）


async def drive_slot(clk):
    """等到最近的"沿后 +0.1ns"驱动时刻（先等到下一上升沿，再 +100ps）。

    在此刻驱动 DUT 输入：该值在下一沿被 DUT 采样；ReadOnly 采样侧看到的
    TB 自驱动信号也恒为"刚结束那拍"的值，两侧天然同拍。
    """
    await RisingEdge(clk)
    await Timer(NBA_PS, unit="ps")


async def start_clocks(dut):
    """启动双域自由运行时钟（各占一个协程）。"""
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    cocotb.start_soon(Clock(dut.apb_clk, APB_CLK_NS, unit="ns").start())


async def reset_all(dut, hold_ns: int = 32):
    """双域复位同时拉低 hold_ns 再同时释放，随后等 4 个慢拍让同步释放稳定。"""
    dut.rst_n.value = 0
    dut.apb_rst_n.value = 0
    await Timer(hold_ns, unit="ns")
    dut.rst_n.value = 1
    dut.apb_rst_n.value = 1
    await Timer(4 * APB_CLK_NS, unit="ns")
