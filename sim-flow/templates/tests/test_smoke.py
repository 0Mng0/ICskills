# =============================================================================
# tests/test_smoke.py — 冒烟：端口核对 + 复位 + CSR 复位值/RW + 最小数据通路
#
# 目的（platform-build.md：smoke 不过后面一切都是空中楼阁）：
#   1) 全端口存在性与位宽核对（对照 spec.yaml interfaces，首抓连接/极性类）；
#   2) 复位后 CSR 复位值与预留区干净应答；
#   3) RW 寄存器写读回读（测后恢复复位值）；
#   4) 最小数据通路：全写→读回、W 先行→读回、部分写→读回——
#      打通 driver→DUT→monitor→refmodel→scoreboard 全链路。
# 适配点：EXPECTED_PORTS、RESET_EXPECT、数据通路激励，均按目标 spec 填。
# =============================================================================
import cocotb

from tb.env import SimEnv
from tb.axi import ArwTxn, BURST_INCR

# spec.yaml 全端口表：{端口名: 位宽}——先 `regress.py --build-only` 编译，
# 与 sim_build/Vtop.h 逐一对齐（接口三级第 2 级），不符先登记 question.yaml。
EXPECTED_PORTS = {
    # 时钟/复位
    "clk": 1, "rst_n": 1, "apb_clk": 1, "apb_rst_n": 1,
    # TODO: 按目标 spec 接口段补全全部端口
}

# CSR 复位值期望表：(名称, 地址, 期望值)——按 spec registers 段填；
# 无管理口的 DUT 留空并删除第 3/4 节。
RESET_EXPECT = [
    # ("VERSION", 0x0004, 0x00000000),
]


@cocotb.test()
async def smoke(dut):
    """端口核对 + 复位 + CSR 复位值/RW/预留区 + 最小数据通路。"""
    # ---------- 1) 端口存在性与位宽核对 ----------
    errors = []
    for name, width in EXPECTED_PORTS.items():
        handle = getattr(dut, name, None)
        if handle is None:
            errors.append(f"端口缺失: {name}")
        elif len(handle) != width:
            errors.append(f"端口位宽不符: {name} 期望 {width}b 实际 {len(handle)}b")
    assert not errors, "端口核对失败:\n" + "\n".join(errors)
    dut._log.info(f"端口核对通过（{len(EXPECTED_PORTS)} 个）")

    # ---------- 2) 启动（默认值 → 时钟 → 复位 → 监测协程） ----------
    env = SimEnv(dut, seed=1)
    await env.start()
    apb = env.apb

    # ---------- 3) CSR 复位值核对（spec registers 段） ----------
    for name, addr, exp in RESET_EXPECT:
        rdata, pslverr = await apb.read(addr)
        assert pslverr == 0, f"{name} 读 pslverr=1"
        assert rdata == exp, f"{name} 复位值: 期望 0x{exp:08X} 实际 0x{rdata:08X}"
    if RESET_EXPECT:
        dut._log.info("CSR 复位值核对通过")

    # ---------- 4) RW 寄存器读写回读（总线空闲时操作，测后恢复复位值） ----------
    # 示例（按目标 spec 的 RW/RO 寄存器改写）：
    # pslverr = await apb.write(REG_CFG, 2)
    # assert pslverr == 0, "CFG 写 pslverr=1"
    # rdata, _ = await apb.read(REG_CFG)
    # assert rdata == 2, f"CFG 回读: 0x{rdata:08X}"
    # await apb.write(REG_CFG, RESET_CFG)        # 恢复复位值

    # ---------- 5) 最小数据通路 ----------
    # 5a) 全写 → 读回（INCR 4 拍；宽度/地址按目标 spec 数据通路调整）
    txn_w = ArwTxn(id=0x11, addr=0x1000, size=6, length=4, burst=BURST_INCR,
                   user=0xA5, we=1)
    await env.do_txn(txn_w)
    await env.do_txn(ArwTxn(id=0x11, addr=0x1000, size=6, length=4,
                            burst=BURST_INCR, user=0xA5, we=0))
    dut._log.info("5a 全写→读回 完成")

    # 5b) W 先于 arw 到达 → 读回（契约允许 W 提前时保留；否则删除本节）
    txn_w2 = ArwTxn(id=0x22, addr=0x2000, size=6, length=2, burst=BURST_INCR,
                    user=0x5A, we=1)
    await env.do_txn(txn_w2, w_first=True)
    await env.do_txn(ArwTxn(id=0x22, addr=0x2000, size=6, length=2,
                            burst=BURST_INCR, user=0x5A, we=0))
    dut._log.info("5b W 先行→读回 完成")

    # ---------- 6) 收尾：排空 + 期望队列/比对错误汇总 ----------
    await env.finish()
    dut._log.info("smoke 全部通过")
