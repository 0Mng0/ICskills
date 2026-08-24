#!/usr/bin/env python3
# req_check.py —— design-flow 阶段 0 / G1 机检（功能说明.md 需求清单章）
# 用法: python tools/req_check.py <功能说明.md>
# 检查项（对应 design-flow §2 G1 机检单）:
#   1. 每条 REQ 四要素齐全（id=REQ-\d{3}、需求/来源非空、优先级 P0|P1|P2）
#   2. 需求列无"等/若干/尽量"类模糊词（白名单: 等价/不等/等待/停等）
#   3. 假设清单存在且逐条有处置（含"确认"或 QUE- 引用或 REQ- 回指）
#   4. 结构: 每个分类小节有导读行（无表格时须显式写"无"）；REQ-id 全局唯一；
#      全文引用的 REQ-id 均存在
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一按 UTF-8 输出

FUZZY = ("若干", "尽量")
ALLOW_PREV = ("不", "停")   # 不等、停等
ALLOW_NEXT = ("价", "待")   # 等价、等待


def main(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    fails = []

    # ---- 定位需求清单章（## 需求清单 到下一个 ## 或 EOF） ----
    start = end = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and "需求清单" in ln:
            start = i
        elif start is not None and ln.startswith("## "):
            end = i
            break
    if start is None:
        print("FAIL: 未找到『## 需求清单』章")
        sys.exit(1)
    chap = lines[start:end] if end else lines[start:]

    # ---- 收集 REQ 表格行与分类小节 ----
    req_rows = []   # (行号, [cell, ...])
    sections = []   # [行号, 标题, [(行号, 行)]]
    cur = None
    for j, ln in enumerate(chap):
        lnno = start + 1 + j
        m = re.match(r"^###\s+\d+\.\s*(.*)", ln)
        if m:
            cur = [lnno, m.group(1).strip(), []]
            sections.append(cur)
            continue
        if cur is not None:
            cur[2].append((lnno, ln))
        if ln.lstrip().startswith("| REQ-"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            req_rows.append((lnno, cells))

    # ---- 检查 1: 四要素齐全 + id 唯一 ----
    defined = {}
    for lnno, cells in req_rows:
        if len(cells) != 4:
            fails.append(f"L{lnno}: REQ 行列数={len(cells)}（应为 4: id/需求/来源/优先级）")
            continue
        rid, need, src, pri = cells
        if not re.fullmatch(r"REQ-\d{3}", rid):
            fails.append(f"L{lnno}: id 非法: {rid!r}")
        if not need:
            fails.append(f"L{lnno}: {rid} 需求列为空")
        if not src:
            fails.append(f"L{lnno}: {rid} 来源列为空")
        if pri not in ("P0", "P1", "P2"):
            fails.append(f"L{lnno}: {rid} 优先级非法: {pri!r}")
        if rid in defined:
            fails.append(f"L{lnno}: REQ-id 重复: {rid}（首次定义于 L{defined[rid]}）")
        defined[rid] = lnno
    if not req_rows:
        fails.append("需求清单章内无 REQ 表格行")

    # ---- 检查 2: 模糊词 ----
    for lnno, cells in req_rows:
        if len(cells) != 4:
            continue
        text = cells[1]
        for w in FUZZY:
            if w in text:
                fails.append(f"L{lnno}: 模糊词 {w!r}（{cells[0]}）")
        for m in re.finditer("等", text):
            prev_c = text[m.start() - 1:m.start()]
            next_c = text[m.start() + 1:m.start() + 2]
            if prev_c in ALLOW_PREV or next_c in ALLOW_NEXT:
                continue
            ctx = text[max(0, m.start() - 3):m.start() + 4]
            fails.append(f"L{lnno}: 模糊词『等』 @ ...{ctx}...（{cells[0]}）")

    # ---- 检查 3: 假设清单 ----
    asm = None
    for j, ln in enumerate(chap):
        if ln.startswith("###") and "假设清单" in ln:
            asm = j
            break
    if asm is None:
        fails.append("未找到『### 假设清单』小节")
    else:
        items = 0
        for k, ln in enumerate(chap[asm + 1:]):
            lnno = start + asm + 2 + k
            if ln.startswith("## "):
                break
            if re.match(r"^\d+\.", ln.strip()):
                items += 1
                if not any(t in ln for t in ("确认", "QUE-", "REQ-")):
                    fails.append(f"L{lnno}: 假设条目无处置（缺『确认』/QUE-/REQ- 引用）: "
                                 f"{ln.strip()[:30]}...")
        if items == 0:
            fails.append("假设清单无编号条目")

    # ---- 检查 4: 结构与引用闭合 ----
    for lnno, title, body in sections:
        guide = [l for _, l in body if l.strip() and not l.strip().startswith("|")]
        has_table = any(l.strip().startswith("|") for _, l in body)
        if not guide and has_table:
            fails.append(f"L{lnno}: 小节『{title}』缺导读行")
        if not has_table and not any("无" in l for l in guide):
            fails.append(f"L{lnno}: 小节『{title}』无表格且未显式写『无』")
    for i, ln in enumerate(lines):
        for rid in re.findall(r"REQ-\d{3}", ln):
            if rid not in defined:
                fails.append(f"L{i + 1}: 引用未定义 REQ-id: {rid}")

    for msg in fails:
        print("FAIL:", msg)
    print(f"req_check: {len(defined)} 条 REQ, {len(sections)} 个分类小节, "
          + ("全部通过" if not fails else f"{len(fails)} 项失败"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python tools/req_check.py <功能说明.md>")
        sys.exit(2)
    main(sys.argv[1])
