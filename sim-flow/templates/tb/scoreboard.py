# =============================================================================
# tb/scoreboard.py — R/B 通道逐拍比对
#
# 比对规则：
#   - R 拍：rid/ruser/rresp/rlast 精确比对；rdata 按 64B 对齐字全字比对
#     （DUT 返回完整对齐字，narrow 读未请求车道同样是存储内容，可全比）；
#   - B：bid/buser/bresp 精确比对（posted 序 = arw 受理序）；
#   - 错误收集制：记录全部错误（封顶 50 条防刷屏），测试收尾统一断言。
# =============================================================================


class Scoreboard:
    def __init__(self, ref, log=None):
        self.ref = ref
        self.log = log
        self.cov = None           # 可选：Coverage 挂钩（resp 分布统计）
        self.errors: list[str] = []
        self.n_err = 0            # 含截断的总错误数
        self.n_r = 0              # 已比对 R 拍数
        self.n_b = 0              # 已比对 B 数

    def _err(self, msg: str):
        self.n_err += 1
        if len(self.errors) < 50:
            self.errors.append(msg)
        if self.log:
            self.log.error(msg)

    # ---------------- R 通道 ----------------
    def check_r(self, beat: dict):
        if self.cov:
            self.cov.on_rresp(beat["rresp"])
        if not self.ref.exp_r:
            self._err(f"意外 R 拍（期望队列空）: rid={beat['rid']:#x} "
                      f"rresp={beat['rresp']} rlast={beat['rlast']}")
            return
        exp = self.ref.exp_r.popleft()
        self.n_r += 1
        ctx = exp["ctx"]
        if beat["rid"] != exp["rid"]:
            self._err(f"R rid 不符: 期望 {exp['rid']:#x} 实际 {beat['rid']:#x} | {ctx}")
        if beat["ruser"] != exp["ruser"]:
            self._err(f"R ruser 不符: 期望 {exp['ruser']:#x} 实际 {beat['ruser']:#x} | {ctx}")
        if beat["rresp"] != exp["rresp"]:
            self._err(f"R rresp 不符: 期望 {exp['rresp']} 实际 {beat['rresp']} | {ctx}")
        if beat["rlast"] != exp["last"]:
            self._err(f"R rlast 不符: 期望 {exp['last']} 实际 {beat['rlast']} | {ctx}")
        if beat["rdata"] != exp["data"]:
            diff = beat["rdata"] ^ exp["data"]
            lo = (diff & -diff).bit_length() - 1     # 首个差异 bit
            self._err(f"R rdata 不符: 首差异 byte@{lo // 8} | {ctx}\n"
                      f"  期望 …{exp['data'] >> (8 * (lo // 8)) & 0xFF:02x} "
                      f"实际 …{beat['rdata'] >> (8 * (lo // 8)) & 0xFF:02x} (byte@{lo//8})")

    # ---------------- B 通道 ----------------
    def check_b(self, beat: dict):
        if self.cov:
            self.cov.on_bresp(beat["bresp"])
        if not self.ref.exp_b:
            self._err(f"意外 B（期望队列空）: bid={beat['bid']:#x} bresp={beat['bresp']}")
            return
        exp = self.ref.exp_b.popleft()
        self.n_b += 1
        ctx = exp["ctx"]
        if beat["bid"] != exp["bid"]:
            self._err(f"B bid 不符: 期望 {exp['bid']:#x} 实际 {beat['bid']:#x} | {ctx}")
        if beat["buser"] != exp["buser"]:
            self._err(f"B buser 不符: 期望 {exp['buser']:#x} 实际 {beat['buser']:#x} | {ctx}")
        if beat["bresp"] != exp["bresp"]:
            self._err(f"B bresp 不符: 期望 {exp['bresp']} 实际 {beat['bresp']} | {ctx}")

    # ---------------- 收尾 ----------------
    def drain_errors(self) -> list[str]:
        """期望队列未排空的遗留项（测试结束时调用）。"""
        left = []
        if self.ref.exp_r:
            left.append(f"R 期望队列残留 {len(self.ref.exp_r)} 拍未返回，"
                        f"队首: {self.ref.exp_r[0]['ctx']}")
        if self.ref.exp_b:
            left.append(f"B 期望队列残留 {len(self.ref.exp_b)} 笔未返回，"
                        f"队首: {self.ref.exp_b[0]['ctx']}")
        return left
