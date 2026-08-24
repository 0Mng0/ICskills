#!/usr/bin/env python3
# arch_check.py —— design-flow 阶段 1 / G2 机检（架构设计.md）
# 用法: python tools/arch_check.py <架构设计.md> [功能说明.md]
# 检查项（对应 design-flow §2 G2 机检单）:
#   1. 章节骨架 §1~§7 齐全
#   2. §4 十二项检查单无静默跳过（清单内置，与 design-flow §6 同步维护）
#   3. §4 每行三态齐全（非空 / "不适用"带原因 / "待确认"收集对照 §7）
#   4. 引用闭合: 全文 REQ-id 在功能说明中存在（给定功能说明才查）；
#      待确认项与 §7 开放问题对照输出（半机械，供人复核）
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一按 UTF-8 输出

SECTIONS = [  # (节号, 标题关键词)
    (1, "需求与性能指标"), (2, "候选方案对比"), (3, "数据流"), (4, "定量分析"),
    (5, "模块划分与接口定义"), (6, "资源"), (7, "风险"),
]
# 与 design-flow §6 分析检查单同步维护（skill 改动此处必须同步）
CHECKLIST = ["事务间气泡", "握手体制", "速率差缓冲", "跨时钟信用", "保序/重排",
             "计数器健康", "串行化点", "状态机边界", "仲裁位置", "慢事件摊薄",
             "反压路径", "流水级数"]


def main(arch_path, func_path=None):
    lines = open(arch_path, encoding="utf-8").read().splitlines()
    fails, warns = [], []

    # ---- 1. 章节骨架 ----
    found = {}
    for i, ln in enumerate(lines):
        m = re.match(r"^##\s+(\d+)\.\s*(.*)", ln)
        if m:
            found[int(m.group(1))] = (i, m.group(2))
    for no, kw in SECTIONS:
        if no not in found:
            fails.append(f"缺章节 ## {no}.（{kw}）")
        elif kw not in found[no][1]:
            fails.append(f"## {no}. 标题不含『{kw}』: L{found[no][0] + 1} {found[no][1]}")

    def span(no):
        if no not in found:
            return []
        s = found[no][0]
        nxt = [found[k][0] for k in found if k > no]
        e = min(nxt) if nxt else len(lines)
        return lines[s:e]

    s4, s7 = span(4), span(7)

    # ---- §4 第一张表格（定量分析表） ----
    rows = []  # (项, 结论)
    in_tbl = False
    for ln in s4:
        is_row = ln.strip().startswith("|")
        if is_row and "---" in ln:
            continue
        if is_row:
            in_tbl = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and cells[0] and cells[0] != "项":
                rows.append((cells[0], cells[1] if len(cells) > 1 else ""))
        elif in_tbl:
            break
    names = [r[0] for r in rows]

    # ---- 2. 十二项差集 ----
    for it in CHECKLIST:
        if it not in names:
            fails.append(f"§4 检查单缺行（静默跳过）: {it}")
    for n in names:
        if n not in CHECKLIST:
            warns.append(f"§4 多出非清单行: {n}")

    # ---- 3. 三态齐全 ----
    pending = []
    for name, concl in rows:
        if not concl:
            fails.append(f"§4 行『{name}』结论为空")
            continue
        if "不适用" in concl:
            rest = re.sub(r"不适用", "", concl).strip(" ，。：:—-")
            if len(rest) < 2:
                fails.append(f"§4 行『{name}』: 『不适用』未给原因")
        if "待确认" in concl:
            pending.append(name)

    # ---- 4. 引用闭合 ----
    if func_path:
        ftext = open(func_path, encoding="utf-8").read()
        defined = set(re.findall(r"REQ-\d{3}", "\n".join(
            l for l in ftext.splitlines() if l.lstrip().startswith("| REQ-"))))
        for i, ln in enumerate(lines):
            for rid in re.findall(r"REQ-\d{3}", ln):
                if rid not in defined:
                    fails.append(f"L{i + 1}: 引用未定义 REQ-id: {rid}")
    # 待确认 ↔ §7 对照（半机械：项名在 §7 出现则判对上）
    t7 = "\n".join(s7)
    print("---- 待确认项 ↔ §7 开放问题 对照 ----")
    if not pending:
        print("  （§4 无待确认项）")
    for name in pending:
        hit = name in t7
        print(f"  {'对上' if hit else '未对上'}: {name}")
        if not hit:
            warns.append(f"待确认项未在 §7 找到: {name}")

    for m in warns:
        print("WARN:", m)
    for m in fails:
        print("FAIL:", m)
    print(f"arch_check: §4 检查行数 {len(rows)}, 待确认 {len(pending)} 项, "
          + ("全部通过" if not fails else f"{len(fails)} 项失败")
          + (f"（{len(warns)} 项 WARN）" if warns else ""))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("用法: python tools/arch_check.py <架构设计.md> [功能说明.md]")
        sys.exit(2)
    main(*sys.argv[1:])
