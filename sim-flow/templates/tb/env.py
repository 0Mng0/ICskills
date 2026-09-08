# =============================================================================
# tb/env.py — 环境装配：DUT 输入默认值、标准启动序列、SimEnv 完整环境类
#
# SimEnv 组件数据流：
#   激励:  ArwDriver / WDriver / ApbDriver / ReadyCtrl(R/B ready)
#   采样:  StreamMonitor(arw+W，同拍先 W 后 arw) / RMonitor / BMonitor
#   模型:  RefModel（期望队列）
#   检查:  Scoreboard（逐拍比对）
# 有下游从机行为模型（PHY/存储等）时：在此装配，驱动其输入默认值，
# drain/finish 中纳入其安静判定与协议检查（见 drain/finish 注释）。
#
# 使用模式（每个 cocotb 测试）：
#   env = SimEnv(dut, seed=...)
#   await env.start()
#   await env.do_txn(txn, beats) ...
#   await env.finish()          # 排空 + 检查 + 错误汇总断言
# =============================================================================
import random

import cocotb
from cocotb.triggers import RisingEdge

from tb.clocks import start_clocks, reset_all
from tb.apb import ApbDriver
from tb.axi import (
    ArwTxn, ArwDriver, WDriver, ReadyCtrl, StreamMonitor, RMonitor, BMonitor,
    gen_write_beats,
)
from tb.ref_model import RefModel
from tb.scoreboard import Scoreboard


def drive_input_defaults(dut):
    """给所有 DUT 输入赋复位默认值（防止 X 传播）。
    端口表按目标 spec 接口段增减；下游从机模型的响应侧输入也在此给默认值。"""
    # ---- host arw 地址通道 ----
    dut.s_arw_id.value = 0
    dut.s_arw_addr.value = 0
    dut.s_arw_len.value = 0
    dut.s_arw_size.value = 0
    dut.s_arw_burst.value = 0
    dut.s_arw_user.value = 0
    dut.s_arw_we.value = 0
    dut.s_arw_lock.value = 0
    dut.s_arw_valid.value = 0
    # ---- host W 通道 ----
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_wlast.value = 0
    dut.s_axi_wvalid.value = 0
    # ---- host R/B ready ----
    dut.s_axi_rready.value = 1
    dut.s_axi_bready.value = 1
    # ---- 上游 APB ----
    dut.s_apb_psel.value = 0
    dut.s_apb_penable.value = 0
    dut.s_apb_pwrite.value = 0
    dut.s_apb_paddr.value = 0
    dut.s_apb_pwdata.value = 0
    # ---- 下游接口输入侧：按目标 spec 补默认值（模型外置时为顶层端口） ----
    # 例：getattr 守卫生成（内部结构无此端口时跳过）——
    # for name, val in (("ds_rdy", 1), ("ds_resp_vld", 0)):
    #     h = getattr(dut, name, None)
    #     if h is not None:
    #         h.value = val


async def tb_start(dut, hold_ns: int = 32):
    """轻量启动序列（冒烟测试用）：输入默认值 → 时钟 → 复位。"""
    drive_input_defaults(dut)
    await start_clocks(dut)
    await reset_all(dut, hold_ns)


class SimEnv:
    """完整验证环境（见模块 docstring 的使用模式）。"""

    def __init__(self, dut, seed: int = 1):
        self.dut = dut
        self.log = dut._log
        self.rnd = random.Random(seed)
        # 检查与模型
        self.ref = RefModel()
        self.sb = Scoreboard(self.ref, log=self.log)
        # 激励
        self.apb = ApbDriver(dut)
        self.arw = ArwDriver(dut)
        self.wdrv = WDriver(dut)
        self.rready = ReadyCtrl(dut.s_axi_rready, dut.clk, "always", self.rnd)
        self.bready = ReadyCtrl(dut.s_axi_bready, dut.clk, "always", self.rnd)
        # 采样
        self.stream_mon = StreamMonitor(dut, self.ref.on_arw, self.ref.on_wbeat)
        self.r_mon = RMonitor(dut, self.sb.check_r)
        self.b_mon = BMonitor(dut, self.sb.check_b)
        # 下游从机行为模型：有则在此实例化（如 self.slave = XxxModel(dut)）
        self._tasks = []

    async def start(self, hold_ns: int = 32):
        """默认值 → 时钟 → 复位 → 拉起全部监测协程。"""
        drive_input_defaults(self.dut)
        await start_clocks(self.dut)
        await reset_all(self.dut, hold_ns)
        for coro in (self.stream_mon.run, self.r_mon.run, self.b_mon.run):
            self._tasks.append(cocotb.start_soon(coro()))
        # 下游模型的 run 协程一并加入上面的元组
        self.rready.start()
        self.bready.start()

    async def do_txn(self, txn: ArwTxn, beats=None, w_first: bool = False):
        """发一笔事务。写：beats 可指定（含 strb 图案）否则随机生成；
        w_first=True 时让 W 先于 arw 到达（被 wready=0 挡住直到 arw 受理）。
        读：只发 arw，R 由 scoreboard 自动比对。"""
        if txn.we:
            if beats is None:
                beats = gen_write_beats(self.rnd, txn)
            if w_first:
                t = cocotb.start_soon(self.wdrv.send_burst(beats))
                await self.arw.send(txn)
                await t
            else:
                await self.arw.send(txn)
                await self.wdrv.send_burst(beats)
        else:
            await self.arw.send(txn)

    async def drain(self, max_cycles: int = 20000, settle: int = 50):
        """等期望队列排空（全部 R/B 返回比对完），再 settle 拍确认无新成交。

        注意：若有下游从机模型且 B posted 先于数据到达下游（posted 语义），
        仅等期望队列会在下游尚有在途请求时误判收尾——应同时等下游安静
        （无在组请求/待返回/在途拍），把其安静条件并入下面的 if 判定。
        """
        for _ in range(max_cycles):
            if self.ref.pending() == 0:
                break
            await RisingEdge(self.dut.clk)
        else:
            raise TimeoutError(
                f"drain 超时：剩 exp_r={len(self.ref.exp_r)} exp_b={len(self.ref.exp_b)}")
        for _ in range(settle):
            await RisingEdge(self.dut.clk)

    async def finish(self, drain_cycles: int = 20000):
        """测试收尾：排空 → 写 burst 收尾检查 → 错误汇总断言。
        有下游模型时，其 finish() 协议检查一并汇入 errors。"""
        errors = []
        try:
            await self.drain(drain_cycles)
        except TimeoutError as e:
            errors.append(str(e))
        if self.ref.cur_wr is not None:
            errors.append(f"写 burst 未收尾（缺 wlast？）: "
                          f"{self.ref.cur_wr['txn'].desc()}")
        errors += self.sb.drain_errors()
        errors += self.ref.errors
        errors += self.sb.errors
        assert not errors, "测试失败:\n" + "\n".join(errors[:50])
