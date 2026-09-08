# =============================================================================
# tb/axi.py — host 侧 arw/W/R/B 通道：事务定义、驱动、采样、激励生成
#
# 协议假设（示例 DUT 契约，拷入新工程后逐条对照目标 spec.yaml 接口段适配）：
#   - arw = AXI AR 字段全集 + we + lock，**单在飞**（仅约束地址通道）：
#     driver 置 valid 后等 ready 握手；写 burst 完成拍 = 末拍 W 被消费，
#     读 burst 完成拍 = 末条读命令被接受；完成拍同拍 arw_ready 可拉高
#     锁存新 arw（背靠背无气泡）；R 返回不受此限（可积压）；
#   - W 可先于 arw 到达（提前量无上限，arw 受理前 wready 恒 0），
#     拍数=len+1，zero-mask 拍合法计入拍数；
#   - R 严格按 arw 受理序返回；B posted 经 B FIFO 无同拍 bypass（末拍 W 消费拍
#     压入，bvalid 最早下一拍拉高），不代表已落存储。
#
# 采样纪律（适配 DUT 的 `<= #0.1` NBA 风格——输出在沿后 0.1ns 才更新）：
#   - **驱动**：一律在"沿后 +0.1ns"时刻改写 DUT 输入（`drive_slot(clk)` =
#     等下一上升沿再 `Timer(100ps)`；cocotb 2.0.1 禁止 ReadOnly→ReadWrite，
#     故不用 ReadWrite 触发器），该值在下一时钟沿被 DUT 采样；
#   - **采样**：一律 `await RisingEdge(clk); await ReadOnly()` 后读——
#     ReadOnly(T) 读到的是刚结束那拍 [T-1,T) 的值（DUT 新输出 T+0.1 才落地，
#     TB 自驱动信号上次改写是 (T-1)+0.1），两侧天然同拍：
#     **vld & rdy 同高 = 沿 T 成交**。
#   - driver 等 ready：驱动后 `RisingEdge + ReadOnly` 再查 DUT ready，
#     ready=1 = 刚过的沿成交；成交后 `Timer(100ps)`（到 T+0.1）再换拍/撤销。
#   依据：dv-collab §4 + #0.1 NBA 风格 DUT 实测（不按此纪律会在 ready
#   跳变沿产生幻影拍/丢拍）。
# =============================================================================
import random
from dataclasses import dataclass

from cocotb.triggers import RisingEdge, ReadOnly, Timer

from tb.clocks import NBA_PS, drive_slot

# ---- burst 类型（s_arw_burst） ----
BURST_FIXED = 0
BURST_INCR = 1
BURST_WRAP = 2

# ---- R/B resp 编码 ----
RESP_OKAY = 0
RESP_EXOKAY = 1
RESP_SLVERR = 2

BUS_BYTES = 64          # 数据总线宽度 512b = 64B（W/R 通道）
ID_W = 8
USER_W = 8


@dataclass
class ArwTxn:
    """一笔 arw 事务（读/写由 we 区分）。"""
    id: int
    addr: int           # 首拍字节地址
    size: int           # 每拍字节数 log2（AXI axsize）
    length: int         # burst 拍数（= axlen+1）
    burst: int          # BURST_FIXED/INCR/WRAP
    user: int
    we: int             # 1=写 / 0=读
    lock: int = 0       # 独占访问

    @property
    def beat_bytes(self) -> int:
        return 1 << self.size

    def beat_addrs(self) -> list[int]:
        """逐拍字节地址序列（AXI 规则）。"""
        nb = self.beat_bytes
        if self.burst == BURST_FIXED:
            return [self.addr] * self.length
        if self.burst == BURST_INCR:
            return [self.addr + i * nb for i in range(self.length)]
        # WRAP：回卷区 = length*nb（2 的幂），首地址 size 对齐
        region = nb * self.length
        base = self.addr - (self.addr % region)
        return [base + (self.addr - base + i * nb) % region for i in range(self.length)]

    def desc(self) -> str:
        bname = {0: "FIXED", 1: "INCR", 2: "WRAP"}[self.burst]
        return (f"{'WR' if self.we else 'RD'} id={self.id:#04x} addr={self.addr:#011x} "
                f"size=2^{self.size} len={self.length} {bname} user={self.user:#04x}"
                f"{' LOCK' if self.lock else ''}")


class TxnGen:
    """按 spec IF-ARW illegal_inputs / FUNC-026 约束生成合法 arw 事务。

    约束落实：
      - burst 不跨 4KB（granu=12）；
      - 任何 beat 不跨 64B 边界 → 多拍 burst 首地址 size 对齐；
      - WRAP：length ∈ {2,4,8,16}，首地址 size 对齐；
      - FIXED/WRAP ≤16 拍，INCR 1~256 拍；
      - 独占（A7.2.4）：总字节数 2 的幂 ≤128B、len≤16、地址对齐 size×len。
    """

    def __init__(self, rnd: random.Random, granu: int = 12, addr_max: int = 0x10000):
        self.rnd = rnd
        self.granu = granu            # 颗粒度 log2（4KB 页）
        self.addr_max = addr_max      # 激励地址窗口上限（字节）

    def _fit_addr(self, size: int, length: int, burst: int) -> int:
        """在窗口内选一个满足 granu 边界约束的首地址（size 对齐）。"""
        nb = 1 << size
        g = 1 << self.granu
        span = nb * length if burst != BURST_FIXED else nb
        for _ in range(1000):
            a = self.rnd.randrange(0, max(1, (self.addr_max - span) // nb)) * nb
            if a // g == (a + span - 1) // g:
                return a
        raise RuntimeError("TxnGen: 窗口内找不到合法地址")

    def gen(self, we=None, lock: int = 0, burst=None, size=None, length=None,
            addr=None, id=None, user=None) -> ArwTxn:
        """生成一笔合法事务；未指定的字段随机。"""
        r = self.rnd
        if lock:
            # 独占：总字节数 2 的幂 ≤128B、len≤16、地址对齐总字节数
            total = r.choice([1, 2, 4, 8, 16, 32, 64, 128])
            size = r.randint(0, 3) if size is None else size   # 拍字节 ≤8B
            nb = 1 << size
            length = total // nb
            if length == 0 or length > 16:
                size, nb, length = 0, 1, min(total, 16)
            burst = BURST_INCR
            nb = 1 << size
            length = max(1, min(16, (nb * length) // nb))
            total = nb * length
            g = 1 << self.granu
            addr = r.randrange(0, max(1, (self.addr_max - total) // total)) * total
            assert addr // g == (addr + total - 1) // g
        else:
            burst = r.choice([BURST_INCR, BURST_INCR, BURST_FIXED, BURST_WRAP]) \
                if burst is None else burst
            size = r.randint(0, 6) if size is None else size   # ≤64B/拍
            max_len = max(1, (1 << self.granu) >> size)
            hi_len = 256 if burst == BURST_INCR else 16
            if burst == BURST_WRAP and max_len < 2:
                burst = BURST_INCR                          # 页内放不下 WRAP 回卷区
                hi_len = 256
            if length is None:
                length = r.randint(1, min(hi_len, max_len))
            length = min(length, hi_len, max_len)
            if burst == BURST_WRAP:
                length = 1 << (length.bit_length() - 1)
                length = max(2, min(length, 16, max_len))
            addr = self._fit_addr(size, length, burst) if addr is None else addr
        return ArwTxn(
            id=r.randint(0, (1 << ID_W) - 1) if id is None else id,
            addr=addr, size=size, length=length, burst=burst,
            user=r.randint(0, (1 << USER_W) - 1) if user is None else user,
            we=r.randint(0, 1) if we is None else we,
            lock=lock,
        )


class ArwDriver:
    """arw 通道驱动（单在飞：置 valid 后等 ready 握手，握上才撤）。"""

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk
        self.max_wait = 20000     # 等 ready 的最大拍数，超时判 DUT 死锁

    async def send(self, txn: ArwTxn):
        d = self.dut
        await drive_slot(self.clk)        # 到下一沿的 +0.1ns 驱动时刻
        d.s_arw_id.value = txn.id
        d.s_arw_addr.value = txn.addr
        d.s_arw_len.value = txn.length - 1    # AXI axlen 语义
        d.s_arw_size.value = txn.size
        d.s_arw_burst.value = txn.burst
        d.s_arw_user.value = txn.user
        d.s_arw_we.value = txn.we
        d.s_arw_lock.value = txn.lock
        d.s_arw_valid.value = 1
        for _ in range(self.max_wait):
            await RisingEdge(self.clk)
            await ReadOnly()              # 刚结束那拍的 ready
            if int(d.s_arw_ready.value) == 1:
                break                     # 刚过的沿成交
        else:
            raise TimeoutError(f"arw 握手超时（疑似 DUT 死锁）: {txn.desc()}")
        await Timer(NBA_PS, unit="ps")    # 到成交沿 +0.1ns：成交已发生才撤销
        d.s_arw_valid.value = 0
        d.s_arw_lock.value = 0

    async def send_chain(self, txns: list[ArwTxn]):
        """零气泡连发：前一笔握手后的 +0.1ns 立即驱动下一笔（valid 不撤），
        相邻 arw 可在连续时钟沿握手——用于覆盖完成拍同拍受理下一笔的时序边界。
        """
        d = self.dut
        await drive_slot(self.clk)
        for txn in txns:
            d.s_arw_id.value = txn.id
            d.s_arw_addr.value = txn.addr
            d.s_arw_len.value = txn.length - 1
            d.s_arw_size.value = txn.size
            d.s_arw_burst.value = txn.burst
            d.s_arw_user.value = txn.user
            d.s_arw_we.value = txn.we
            d.s_arw_lock.value = txn.lock
            d.s_arw_valid.value = 1
            for _ in range(self.max_wait):
                await RisingEdge(self.clk)
                await ReadOnly()
                if int(d.s_arw_ready.value) == 1:
                    break                 # 刚过的沿成交；不撤 valid 直接换下一笔
            else:
                raise TimeoutError(f"arw 链式握手超时（疑似 DUT 死锁）: {txn.desc()}")
            await Timer(NBA_PS, unit="ps")   # 成交沿 +0.1ns 换下一笔
        d.s_arw_valid.value = 0
        d.s_arw_lock.value = 0


class WDriver:
    """W 通道驱动：逐拍驱动 (data, strb)，末拍带 wlast；支持拍间气泡。"""

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk
        self.gap = 0          # 拍间附加气泡拍数（0=背靠背满速）
        self.max_wait = 20000  # 等 wready 的最大拍数，超时判 DUT 死锁
        self._pending = 0     # 未完成 burst 计数（供测试同步用）

    async def send_burst(self, beats: list[tuple[int, int]]):
        """发送一个完整 burst 的 W 拍；beats=[(wdata512b, wstrb64b), ...]。"""
        d = self.dut
        self._pending += 1
        try:
            await drive_slot(self.clk)    # 到下一沿的 +0.1ns 驱动时刻
            n = len(beats)
            for i, (data, strb) in enumerate(beats):
                d.s_axi_wdata.value = data
                d.s_axi_wstrb.value = strb
                d.s_axi_wlast.value = 1 if i == n - 1 else 0
                d.s_axi_wvalid.value = 1
                for _ in range(self.max_wait):
                    await RisingEdge(self.clk)
                    await ReadOnly()      # 刚结束那拍的 wready
                    if int(d.s_axi_wready.value) == 1:
                        break             # 刚过的沿成交
                else:
                    raise TimeoutError(
                        f"W 拍 {i}/{n-1} 等 wready 超时（疑似 DUT 死锁）")
                await Timer(NBA_PS, unit="ps")   # 到成交沿 +0.1ns 再换拍
                for _ in range(self.gap):
                    d.s_axi_wvalid.value = 0
                    await RisingEdge(self.clk)
                    await Timer(NBA_PS, unit="ps")   # 气泡间保持 +0.1 驱动
            d.s_axi_wvalid.value = 0
            d.s_axi_wlast.value = 0
        finally:
            self._pending -= 1


def gen_write_beats(rnd: random.Random, txn: ArwTxn,
                    zero_mask: set[int] | None = None) -> list[tuple[int, int]]:
    """按 txn 生成 W 拍列表：strb 覆盖该拍有效字节车道，数据随机填充有效车道。

    zero_mask: 需置 zero-mask（strb=0）的拍号集合（IF-W：合法且计入拍数）。
    """
    beats = []
    for i, a in enumerate(txn.beat_addrs()):
        if zero_mask and i in zero_mask:
            beats.append((0, 0))
            continue
        off = a % BUS_BYTES
        nb = txn.beat_bytes
        strb = ((1 << nb) - 1) << off
        data = 0
        for b in range(off, off + nb):
            data |= rnd.randrange(256) << (8 * b)
        beats.append((data, strb))
    return beats


class ReadyCtrl:
    """R/B 通道 ready 控制：'always'（恒 1）/ 'random'（随机反压）/ 'manual'。

    manual 模式：测试写 self.value，由本协程在沿后 +0.1ns 驱动——**禁止绕过
    本协程直接写 DUT 引脚**（任意时刻的直写会被 ReadOnly 监测器提前一拍看到，
    在 ready 跳变沿产生幻影成交）。
    """

    def __init__(self, sig, clk, mode="always", rnd=None, high_pct=70):
        self.sig = sig
        self.clk = clk
        self.mode = mode
        self.value = 1            # manual 模式下的驱动值
        self.rnd = rnd or random.Random(0)
        self.high_pct = high_pct
        self._task = None

    def start(self):
        import cocotb
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        """停掉驱动协程（之后 ready 保持最后驱动值）。"""
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self):
        while True:
            await drive_slot(self.clk)    # 沿后 +0.1ns 驱动本拍 ready
            if self.mode == "always":
                self.sig.value = 1
            elif self.mode == "manual":
                self.sig.value = self.value
            else:  # random
                self.sig.value = 1 if self.rnd.randrange(100) < self.high_pct else 0


class StreamMonitor:
    """arw+W 合并采样器（每 clk 拍一个协程，ReadOnly 采样）。

    采样内容均为"刚结束那拍"的值：DUT 输出（arw_ready/wready）直接读；
    TB 驱动的信号（arw_valid/W 载荷等）上次改写发生在上一拍 +0.1，此刻读到的
    仍是拍在总线那一拍的值——两侧天然同拍，无需打拍缓存。

    顺序约定（关键）：同一拍内**先处理 W 成交、后处理 arw 成交**——
    对应 spec"写 burst 末拍 W 被消费的同拍，下一笔 arw 可握手"：该拍若读
    arw 与写的末拍 W 同沿成交，参考模型须先把这拍 W 落入存储，再做读快照。
    """

    def __init__(self, dut, on_arw, on_wbeat):
        self.dut = dut
        self.on_arw = on_arw      # 回调 ArwTxn
        self.on_wbeat = on_wbeat  # 回调 (data, strb, last)

    async def run(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            # 1) W 拍成交
            if int(d.s_axi_wvalid.value) and int(d.s_axi_wready.value):
                self.on_wbeat(int(d.s_axi_wdata.value),
                              int(d.s_axi_wstrb.value),
                              int(d.s_axi_wlast.value))
            # 2) arw 成交
            if int(d.s_arw_valid.value) and int(d.s_arw_ready.value):
                self.on_arw(ArwTxn(
                    id=int(d.s_arw_id.value), addr=int(d.s_arw_addr.value),
                    size=int(d.s_arw_size.value), length=int(d.s_arw_len.value) + 1,
                    burst=int(d.s_arw_burst.value), user=int(d.s_arw_user.value),
                    we=int(d.s_arw_we.value), lock=int(d.s_arw_lock.value),
                ))


class RMonitor:
    """R 通道采样：rvalid&rready 同高 → 回调一拍 {rid,rdata,rresp,rlast,ruser}。"""

    def __init__(self, dut, on_beat):
        self.dut = dut
        self.on_beat = on_beat

    async def run(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            if int(d.s_axi_rvalid.value) and int(d.s_axi_rready.value):
                self.on_beat(dict(
                    rid=int(d.s_axi_rid.value), rdata=int(d.s_axi_rdata.value),
                    rresp=int(d.s_axi_rresp.value), rlast=int(d.s_axi_rlast.value),
                    ruser=int(d.s_axi_ruser.value),
                ))


class BMonitor:
    """B 通道采样：bvalid&bready 同高 → 回调 {bid,bresp,buser}。"""

    def __init__(self, dut, on_beat):
        self.dut = dut
        self.on_beat = on_beat

    async def run(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            if int(d.s_axi_bvalid.value) and int(d.s_axi_bready.value):
                self.on_beat(dict(
                    bid=int(d.s_axi_bid.value), bresp=int(d.s_axi_bresp.value),
                    buser=int(d.s_axi_buser.value),
                ))
