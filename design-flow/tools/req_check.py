#!/usr/bin/env python3
# req_check.py —— design-flow 阶段 0 / G1 机检（功能说明.md 需求清单章）
# 用法: python tools/req_check.py <功能说明.md>
# 检查项（对应 design-flow §2 G1 机检单）:
#   1. 每条 REQ 四要素齐全（id=REQ-\d{3}、需求/来源非空、优先级 P0|P1|P2）
#   2. 需求列无"等/若干/尽量"类模糊词（白名单: 等价/不等/等待/停等）
#   3. 假设清单存在且逐条有处置（含"确认"或 QUE-/REQ- 引用）
#   4. 树形结构: 每个 ### 大类有"功能全集定义"句；每个 #### 叶子有导读行、
#      编号 N.M 与大类一致、空类显式写"无"（无表格或表格无 REQ 行）；
#      REQ 行只出现在 #### 叶子表格中；REQ-id 全局唯一；全文引用的 REQ-id
#      均存在
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一 UTF-8 输出

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

    # ---- 收集结构：### 大类 / #### 叶子 / REQ 行 ----
    req_rows = []   # (行号, [cell, ...])
    l1secs = []     # [行号, 编号, 标题, 全集定义句|None]
    leaves = []     # [行号, N, M, 标题, 父编号|None, 导读|None, 有表格, REQ行数]
    cur_l1 = None
    cur_leaf = None
    for j, ln in enumerate(chap):
        lnno = start + 1 + j
        m1 = re.match(r"^###\s+(\d+)\.\s*(.*)", ln)
        m2 = re.match(r"^####\s+(\d+)\.(\d+)\s*(.*)", ln)
        if m1:
            cur_l1 = [lnno, m1.group(1), m1.group(2).strip(), None]
            l1secs.append(cur_l1)
            cur_leaf = None
            continue
        if m2:
            cur_leaf = [lnno, m2.group(1), m2.group(2), m2.group(3).strip(),
                        cur_l1[1] if cur_l1 else None, None, False, 0]
            leaves.append(cur_leaf)
            continue
        if ln.lstrip().startswith("| REQ-"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            req_rows.append((lnno, cells))
            if cur_leaf is None:
                fails.append(f"L{lnno}: REQ 行不在任何 #### 叶子内"
                             f"（每条 REQ 须恰好归属一个叶子）")
            else:
                cur_leaf[7] += 1
            continue
        if ln.strip().startswith("|"):
            if cur_leaf is not None:
                cur_leaf[6] = True
            continue
        if ln.strip() and not ln.startswith("#"):
            if cur_leaf is not None and cur_leaf[5] is None and not cur_leaf[6]:
                cur_leaf[5] = ln.strip()
            elif cur_leaf is None and cur_l1 is not None and cur_l1[3] is None:
                cur_l1[3] = ln.strip()

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

    # ---- 检查 4: 树结构与引用闭合 ----
    for lnno, num, title, guide in l1secs:
        if not guide:
            fails.append(f"L{lnno}: 大类『{num}. {title}』缺『功能全集定义』句")
    for lnno, n, m_, title, parent, guide, has_tbl, nreq in leaves:
        if parent is not None and n != parent:
            fails.append(f"L{lnno}: 叶子编号 {n}.{m_} 与大类 {parent} 不一致")
        if not guide:
            fails.append(f"L{lnno}: 叶子『{n}.{m_} {title}』缺导读行")
        if not has_tbl or nreq == 0:
            if "无" not in (guide or ""):
                fails.append(f"L{lnno}: 叶子『{n}.{m_} {title}』无 REQ 行且未显式写『无』")
    for i, ln in enumerate(lines):
        for rid in re.findall(r"REQ-\d{3}", ln):
            if rid not in defined:
                fails.append(f"L{i + 1}: 引用未定义 REQ-id: {rid}")

    for msg in fails:
        print("FAIL:", msg)
    print(f"req_check: {len(defined)} 条 REQ, {len(l1secs)} 个大类, {len(leaves)} 个叶子, "
          + ("全部通过" if not fails else f"{len(fails)} 项失败"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python tools/req_check.py <功能说明.md>")
        sys.exit(2)
    main(sys.argv[1])
