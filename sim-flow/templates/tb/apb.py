# =============================================================================
# tb/apb.py — APB 主设备驱动（s_apb_*，独立 apb_clk 域，标准两拍 APB 时序）
#
# 采样纪律（与 tb/axi.py 头部说明一致）：驱动在沿后 +0.1ns（drive_slot /
# Timer(100ps)），采样在 ReadOnly（读到刚结束那拍的值）；access 拍逐拍查 pready。
#
# 适配点：寄存器地址表/区域划分按目标 spec.yaml registers 段在此定义——
# 以下为示例格式，拷入新工程后整体替换：
#   REG_VERSION = 0x0004       # RO 版本号常量
#   VERSION_VALUE = 0x00000000 # 期望值按 spec
# =============================================================================
from cocotb.triggers import RisingEdge, ReadOnly, Timer

from tb.clocks import NBA_PS, drive_slot


class ApbDriver:
    """上游 APB 主驱动。read/write 均返回 pslverr，read 另返回 rdata。"""

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.apb_clk
        self.last_waits = 0        # 上一次传输 access 阶段插入的等待拍数
        self.idle()

    def idle(self):
        d = self.dut
        d.s_apb_psel.value = 0
        d.s_apb_penable.value = 0
        d.s_apb_pwrite.value = 0
        d.s_apb_paddr.value = 0
        d.s_apb_pwdata.value = 0

    async def _xfer(self, write: bool, addr: int, data: int = 0):
        """一次 APB 传输：setup 拍 → access 拍（按 pready 插 wait 状态）。"""
        d = self.dut
        self.last_waits = 0
        # setup 拍：psel=1, penable=0（+0.1ns 驱动时刻）
        await drive_slot(self.clk)
        d.s_apb_psel.value = 1
        d.s_apb_penable.value = 0
        d.s_apb_pwrite.value = 1 if write else 0
        d.s_apb_paddr.value = addr
        d.s_apb_pwdata.value = data
        # access 拍：penable=1，逐拍（ReadOnly）检查 pready
        await drive_slot(self.clk)
        d.s_apb_penable.value = 1
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()                       # 刚结束那拍的 pready
            if int(d.s_apb_pready.value) == 1:
                rdata = int(d.s_apb_prdata.value)
                pslverr = int(d.s_apb_pslverr.value)
                break                              # 刚过的沿完成
            self.last_waits += 1
        # 完成沿 +0.1ns 撤销 sel/enable 回 idle
        await Timer(NBA_PS, unit="ps")
        self.idle()
        return rdata, pslverr

    async def write(self, addr: int, data: int) -> int:
        """APB 写，返回 pslverr。"""
        _, pslverr = await self._xfer(True, addr, data)
        return pslverr

    async def read(self, addr: int):
        """APB 读，返回 (rdata, pslverr)。"""
        return await self._xfer(False, addr)
