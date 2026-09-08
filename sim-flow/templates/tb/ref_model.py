# =============================================================================
# tb/ref_model.py — 参考模型：字节级存储 + 保序期望队列 + 独占监测表仿真
#
# 参考模型红线：语义只从目标 spec.yaml + 叙事文档推导。下列建模规则是
# 示例 DUT 的契约（保序/独占/resp 语义），拷入新工程后须逐条对照目标
# spec 重推导，不可直接沿用。
#
# 建模规则（示例）：
#   - 严格保序：arw 受理序即全系统唯一顺序；R 期望按受理序生成，B posted 同序；
#   - 读快照时机：arw 受理拍——此前所有写已按序落入 ref 存储（StreamMonitor
#     同拍先 W 后 arw 的顺序约定保证"末拍 W 与下一笔 arw 同拍成交"时读见新数据）；
#   - R 数据：DUT 返回该拍所在 64B 对齐字的完整 512b（narrow 读未请求车道也是
#     存储内容），scoreboard 按全字比对；
#   - rresp：逐拍独立；无错/CE→普通读 OKAY、独占读 EXOKAY；UE→SLVERR（P1 注入）；
#   - 写落存储：按拍 wstrb 应用；zero-mask 拍跳过（不落存储、不构成侵入）；
#   - 独占写判决（arw 受理时刻即可完成：单 arw 在飞，此后无其他事务改变表项；
#     示例契约中表项于末拍 W 消费后失效——单在飞下两时点等价）：
#     表项有效（未被侵入）且同 ID → 成功（EXOKAY，数据正常下发）；
#     否则失败（OKAY，整 burst 丢弃：不落存储、不构成侵入）；判决后表项失效；
#   - 侵入判定：写 beat 字节区间 [起始, 起始+2^size-1] 与在监 [lo,hi] 有交即侵入；
#     本表项同 ID 独占写自身豁免（实现上：verdict 时已把本表项移除，天然豁免）；
#     同 ID 普通写不豁免。
# =============================================================================
from collections import deque

from tb.axi import ArwTxn, RESP_OKAY, RESP_EXOKAY, BUS_BYTES


class ExclMon:
    """独占监测表仿真（示例容量 4：同 ID 复用 > 首个空项 > 满不分配）。

    示例契约语义（拷入后按目标 spec 重推导）：字节级区间 [lo,hi]；同 ID
    重复独占读复用并刷新区间；表满不分配（不顶掉在监表项）；任意字节重叠
    即侵入；对应独占写完成后表项失效（成败皆然）。
    """

    def __init__(self, num: int = 4):
        self.num = num
        self.entries: list[dict | None] = [None] * num   # None 或 {"id","lo","hi"}
        self.n_arm = 0          # 统计：成功 arm 次数
        self.n_full = 0         # 统计：满不分配次数

    def arm(self, txn: ArwTxn):
        """独占读 arm：监测区间 [lo, hi] = [首拍起始, 末拍末字节]。"""
        beats = txn.beat_addrs()
        lo = beats[0]
        hi = beats[-1] + txn.beat_bytes - 1
        for e in self.entries:                       # 同 ID 复用
            if e is not None and e["id"] == txn.id:
                e["lo"], e["hi"] = lo, hi
                self.n_arm += 1
                return
        for i, e in enumerate(self.entries):         # 首个空项
            if e is None:
                self.entries[i] = {"id": txn.id, "lo": lo, "hi": hi}
                self.n_arm += 1
                return
        self.n_full += 1                             # 满：不分配

    def verdict(self, txn: ArwTxn) -> bool:
        """独占写判决：同 ID 表项仍存在（有效且未被侵入）→ 成功；判决后表项失效。"""
        for i, e in enumerate(self.entries):
            if e is not None and e["id"] == txn.id:
                self.entries[i] = None               # 完成后失效（无论成败）
                return True
        return False

    def intrude(self, lo: int, hi: int):
        """写 beat 字节区间 [lo,hi] 与在监区间有交 → 对应表项失效（侵入）。"""
        for i, e in enumerate(self.entries):
            if e is not None and not (hi < e["lo"] or lo > e["hi"]):
                self.entries[i] = None


class RefModel:
    """参考模型主类。on_arw/on_wbeat 由 StreamMonitor 按成交序回调。"""

    def __init__(self, cov=None):
        self.mem: dict[int, int] = {}              # host 字节地址 -> 字节
        self.exp_r: deque = deque()                # 期望 R 拍队列（保序）
        self.exp_b: deque = deque()                # 期望 B 队列（posted 序）
        self.cur_wr: dict | None = None            # 当前在飞写 burst（单 arw 在飞）
        self.excl = ExclMon()
        self.cov = cov
        self.errors: list[str] = []
        # P1 预留：按读请求序号注入的期望 SLVERR beat（当前恒无错）

    # ---------------- 内部：64B 字读 ----------------
    def _read_word(self, base: int) -> int:
        """读 64B 对齐字（base 需 64B 对齐），返回 512b int；未写字节为 0。"""
        v = 0
        for b in range(BUS_BYTES):
            v |= self.mem.get(base + b, 0) << (8 * b)
        return v

    # ---------------- arw 成交回调 ----------------
    def on_arw(self, txn: ArwTxn):
        if self.cov:
            self.cov.on_arw(txn)
        if txn.we == 0:
            self._on_read(txn)
        else:
            self._on_write_arw(txn)

    def _on_read(self, txn: ArwTxn):
        if txn.lock:
            self.excl.arm(txn)                     # 独占读：arm 监测表项
        beats = txn.beat_addrs()
        for i, a in enumerate(beats):
            self.exp_r.append({
                "rid": txn.id, "ruser": txn.user,
                "rresp": RESP_EXOKAY if txn.lock else RESP_OKAY,
                "data": self._read_word(a & ~(BUS_BYTES - 1)),
                "last": 1 if i == len(beats) - 1 else 0,
                "ctx": f"{txn.desc()} beat{i}/{len(beats)-1}",
            })

    def _on_write_arw(self, txn: ArwTxn):
        apply = True
        bresp = RESP_OKAY
        if txn.lock:
            ok = self.excl.verdict(txn)            # 独占写判决（此后表项已失效）
            bresp = RESP_EXOKAY if ok else RESP_OKAY
            apply = ok                             # 失败：整 burst 丢弃
            if self.cov:
                self.cov.on_excl_wr(ok)
        self.exp_b.append({
            "bid": txn.id, "buser": txn.user, "bresp": bresp,
            "ctx": txn.desc(),
        })
        if self.cur_wr is not None:
            self.errors.append(f"写 arw 受理时上一写 burst 未结束: {txn.desc()}")
        self.cur_wr = {"txn": txn, "beat": 0, "apply": apply}

    # ---------------- W 拍成交回调 ----------------
    def on_wbeat(self, data: int, strb: int, last: int):
        ctx = self.cur_wr
        if ctx is None:
            self.errors.append("W 拍成交但无在飞写 burst（wready 异常？）")
            return
        txn: ArwTxn = ctx["txn"]
        beats = txn.beat_addrs()
        i = ctx["beat"]
        if i >= len(beats):
            self.errors.append(f"W 拍数超过 len+1: {txn.desc()}")
            return
        a = beats[i]
        if self.cov:
            self.cov.on_wbeat(strb)
        # zero-mask 拍 / 失败独占写：不落存储、不构成侵入
        if ctx["apply"] and strb != 0:
            base = a & ~(BUS_BYTES - 1)
            for b in range(BUS_BYTES):
                if (strb >> b) & 1:
                    self.mem[base + b] = (data >> (8 * b)) & 0xFF
            self.excl.intrude(a, a + txn.beat_bytes - 1)
        ctx["beat"] += 1
        if last:
            if ctx["beat"] != len(beats):
                self.errors.append(
                    f"wlast 提前: {txn.desc()} 拍到 {i}/{len(beats)-1}")
            self.cur_wr = None

    # ---------------- 收尾 ----------------
    def pending(self) -> int:
        return len(self.exp_r) + len(self.exp_b)
