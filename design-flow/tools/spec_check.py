#!/usr/bin/env python3
# spec_check.py —— design-flow 阶段 2 / G3 机检（spec.yaml × 文档 × RTL）
# 用法（工程根目录下）: python tools/spec_check.py [--spec P] [--que P]
#   [--func P] [--arch P] [--rtl-top P] [--rtl-csr P]
# 路径默认值：spec/que 取 doc/yaml/ 下同名契约；func/arch/rtl 由 spec 的
#   module.name/top 派生（doc/md/<name>功能说明.md、doc/md/<name>架构设计.md、
#   rtl/design/<top>.sv、rtl/design/<去_top>_csr.sv）。
# 检查项（对应 design-flow §2 G3 机检单 a/c/d/e + 闭环对照 f）:
#   a. schema 校验: 必备字段齐全、FUNC/IF id 唯一、contract source 非空
#   c. A 层对照: source 锚点（REQ-id / §N）双向差集（无源 FAIL；遗漏须显式归
#      out_of_scope/open_questions）
#   d. REQ→FUNC 追溯: 每 REQ 有 FUNC 覆盖；每 FUNC 挂 REQ 或标"设计细化"
#   e. 接口事实机械对照: spec parameters/interfaces/registers ↔ RTL 提取
#      （参数默认值/端口名方向位宽/CSR 地址 FAIL；reset 提取不到 WARN——
#        语义级比对靠评审）
#   f. open_questions 闭环对照（question.yaml 存在时；规则见 dv-collab
#      question.md 总规则第 6 条）
import argparse
import pathlib
import re
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一 UTF-8 输出

fails, warns = [], []


def fail(m):
    fails.append(m)


def warn(m):
    warns.append(m)


def collect_sources(obj, out):
    """递归收集 dict/list 树中所有 source 字段文本。"""
    if isinstance(obj, dict):
        if "source" in obj:
            out.append(str(obj["source"]))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                collect_sources(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_sources(v, out)


def rtl_width(bracket, params):
    """由端口位宽声明文本计算位宽；无法解析返回 None。"""
    if not bracket:
        return 1
    inner = bracket.strip("[] ")
    if ":" not in inner:
        return None
    left, right = inner.rsplit(":", 1)
    if not right.strip().isdigit():
        return None
    right = int(right)
    m = re.fullmatch(r"(\w+)-1", left.strip())
    if m:  # [X-1:0] 形式，X 为数字或参数名
        base = m.group(1)
        if base.isdigit():
            return int(base) - right
        if base in params:
            return int(params[base]) - right
        return None
    if left.strip().isdigit():
        return int(left) - right + 1
    return None


def main():
    ap = argparse.ArgumentParser(description="design-flow G3 机检")
    ap.add_argument("--spec", default="doc/yaml/spec.yaml")
    ap.add_argument("--que", default="doc/yaml/question.yaml")
    ap.add_argument("--func")
    ap.add_argument("--arch")
    ap.add_argument("--rtl-top", dest="rtl_top")
    ap.add_argument("--rtl-csr", dest="rtl_csr")
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    if not spec_path.exists():
        print(f"FAIL: {spec_path} 不存在（阶段 2 未开始）")
        sys.exit(1)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    mod = spec.get("module") or {}
    name = mod.get("name", "")
    top = mod.get("top", "")
    func_path = pathlib.Path(args.func or f"doc/md/{name}功能说明.md")
    arch_path = pathlib.Path(args.arch or f"doc/md/{name}架构设计.md")
    rtl_top = pathlib.Path(args.rtl_top or f"rtl/design/{top}.sv")
    rtl_csr = pathlib.Path(args.rtl_csr
                           or f"rtl/design/{top.removesuffix('_top')}_csr.sv")

    # ---------------- a. schema 校验 ----------------
    for k in ("schema_version", "doc", "module", "clock_reset", "interfaces", "functions"):
        if k not in spec:
            fail(f"spec 缺顶层键: {k}")
    doc = spec.get("doc", {}) or {}
    for k in ("id", "title", "version", "stage", "commit_id",
              "author", "date", "source_docs", "change_summary"):
        if k not in doc:
            fail(f"doc 缺字段: {k}")
    params = mod.get("parameters") or []
    for p in params:
        if "name" not in p or "default" not in p:
            fail(f"parameter 缺 name/default: {p}")
    if_ids, fn_ids = set(), set()
    ifaces = spec.get("interfaces") or []
    for itf in ifaces:
        iid = itf.get("id", "?")
        for k in ("id", "role", "clock", "protocol", "signals"):
            if k not in itf:
                fail(f"interface {iid} 缺字段: {k}")
        if iid in if_ids:
            fail(f"IF id 重复: {iid}")
        if_ids.add(iid)
        for s in itf.get("signals") or []:
            for k in ("name", "dir", "width"):
                if k not in s:
                    fail(f"接口 {iid} 信号缺 {k}: {s}")
    funcs = spec.get("functions") or []
    for f in funcs:
        fid = f.get("id", "?")
        for k in ("id", "text", "source"):
            if k not in f:
                fail(f"function {fid} 缺字段: {k}")
        if fid in fn_ids:
            fail(f"FUNC id 重复: {fid}")
        fn_ids.add(fid)

    # ---------------- 锚点集合（REQ-id ∪ §N） ----------------
    for pth, tag in ((func_path, "功能说明"), (arch_path, "架构设计")):
        if not pth.exists():
            fail(f"{tag}文档不存在: {pth}（A 层对照需要）")
    if fails:
        for m in fails:
            print("FAIL:", m)
        sys.exit(1)
    ftext = func_path.read_text(encoding="utf-8")
    atext = arch_path.read_text(encoding="utf-8")
    req_ids = set(re.findall(r"REQ-\d{3}", "\n".join(
        l for l in ftext.splitlines() if l.lstrip().startswith("| REQ-"))))
    anchors = set(req_ids)
    for txt in (ftext, atext):
        for m in re.finditer(r"^#{2,3}\s+(\d+(?:\.\d+)?)", txt, re.M):
            anchors.add("§" + m.group(1))

    # ---------------- c/d. source 对照 ----------------
    srcs = []
    collect_sources(spec.get("functions"), srcs)
    collect_sources(spec.get("out_of_scope"), srcs)
    for itf in ifaces:
        collect_sources(itf.get("contract"), srcs)
    referenced = set()
    for s in srcs:
        refs = set(re.findall(r"REQ-\d{3}", s)) | set(re.findall(r"§\d+(?:\.\d+)?", s))
        for r in refs:
            if r not in anchors:
                fail(f"source 指向不存在锚点: {r}（出自 {s[:40]}...）")
        referenced |= refs & set(req_ids)
    scope_txt = str(spec.get("out_of_scope", "")) + str(spec.get("open_questions", ""))
    for rid in sorted(req_ids - referenced):
        if rid in scope_txt:
            continue  # 显式归 out_of_scope/open_questions
        fail(f"REQ 未被任何 FUNC 覆盖: {rid}")
    for f in funcs:
        s = str(f.get("source", ""))
        if not re.search(r"REQ-\d{3}", s) and "设计细化" not in s:
            fail(f"FUNC {f.get('id', '?')} 未挂 REQ 也未标『设计细化』")

    # ---------------- e. RTL 机械对照 ----------------
    if rtl_top.exists():
        sv = rtl_top.read_text(encoding="utf-8")
        rtl_params = {}
        for m in re.finditer(r"parameter\s+int\s+(\w+)\s*=\s*([^,\n\)]+)", sv):
            pname, expr = m.group(1), re.sub(r"//.*", "", m.group(2)).strip()
            if expr.isdigit():
                rtl_params[pname] = int(expr)
            else:  # 简单表达式求值（如 STRB_W = DATA_W/8）
                mm = re.fullmatch(r"(\w+)\s*/\s*(\d+)", expr)
                if mm and mm.group(1) in rtl_params:
                    rtl_params[pname] = rtl_params[mm.group(1)] // int(mm.group(2))
        for p in params:
            pname, dft = str(p["name"]), int(str(p["default"]), 0)
            if pname not in rtl_params:
                fail(f"参数 {pname} 在 RTL 中不存在或默认值未能解析")
            elif rtl_params[pname] != dft:
                fail(f"参数 {pname} 默认值: spec={dft} RTL={rtl_params[pname]}")
        rtl_ports = {}
        for m in re.finditer(r"\b(input|output)\s+logic\s+(\[[^\]]*\])?\s*(\w+)", sv):
            d, br, pname = m.groups()
            rtl_ports[pname] = (d, rtl_width(br, rtl_params))
        for itf in ifaces:
            for s in itf.get("signals") or []:
                sname = str(s["name"])
                if sname not in rtl_ports:
                    warn(f"接口 {itf.get('id')} 信号 {sname} 在顶层端口未找到")
                    continue
                d, w = rtl_ports[sname]
                if d != ("input" if s["dir"] == "in" else "output"):
                    fail(f"端口 {sname} 方向: spec={s['dir']} RTL={d}")
                if w is None:
                    warn(f"端口 {sname} RTL 位宽表达式未能解析，人工复核")
                elif int(s["width"]) != w:
                    fail(f"端口 {sname} 位宽: spec={s['width']} RTL={w}")
    else:
        warn(f"{rtl_top} 不存在，跳过端口/参数对照（G3 要求 RTL 已存在时此项为必查）")

    if rtl_csr.exists():
        csv = rtl_csr.read_text(encoding="utf-8")
        rtl_addrs = {int(h, 16) for h in re.findall(r"\d+'h([0-9a-fA-F]{1,4})", csv)}
        reset_vals = {}
        in_rst = False
        for ln in csv.splitlines():
            if re.search(r"if\s*\(\s*!\w*rst_n\)", ln):
                in_rst = True
            elif in_rst and re.search(r"^\s*(end\s+)?else\b", ln):
                in_rst = False
            if in_rst:
                for m2 in re.finditer(
                        r"(\w+)\s*<=\s*#0\.1\s*(\d+)'([bdh])([0-9a-fA-Fxz]+)\s*;", ln):
                    reset_vals[m2.group(1)] = int(
                        m2.group(4).replace("x", "0").replace("z", "0"),
                        {"b": 2, "d": 10, "h": 16}[m2.group(3)])
        for reg in spec.get("registers") or []:
            off = reg.get("offset")
            if off is None:
                fail(f"register {reg.get('name', '?')} 缺 offset")
                continue
            if int(str(off), 16) not in rtl_addrs:
                fail(f"寄存器 {reg.get('name')} 地址 {off} 在 CSR RTL 译码中未找到")
            if "reset" in reg:
                sig = str(reg.get("name", "")).lower() + "_q"
                rv_int = int(str(reg["reset"]), 0)
                if sig not in reset_vals:
                    warn(f"寄存器 {reg.get('name')} 的 reset 值未能从 RTL 提取"
                         f"（{sig}），人工复核")
                elif reset_vals[sig] != rv_int:
                    fail(f"寄存器 {reg.get('name')} reset 值: "
                         f"spec={reg['reset']} RTL=0x{reset_vals[sig]:X}")
    else:
        warn(f"{rtl_csr} 不存在，跳过 CSR 对照")

    # ---------------- f. open_questions 闭环对照 ----------------
    oq_ids = set()
    for s in spec.get("open_questions") or []:
        oq_ids.update(re.findall(r"QUE-\d{3}", str(s)))
    que_path = pathlib.Path(args.que)
    if que_path.exists():
        que = yaml.safe_load(que_path.read_text(encoding="utf-8")) or {}
        q_all = {q["id"]: q.get("status", "") for q in que.get("questions") or []}
        open_ids = {i for i, st in q_all.items() if st in ("open", "question_sent", "answered")}
        closed_ids = {i for i, st in q_all.items() if st in ("confirmed", "obsolete")}
        for i in sorted(open_ids - oq_ids):
            fail(f"开放 QUE 未列入 open_questions 台账: {i}")
        for i in sorted(oq_ids - set(q_all)):
            fail(f"open_questions 台账 QUE-id 在 question.yaml 不存在: {i}")
        for i in sorted(closed_ids & oq_ids):
            fail(f"已关闭 QUE 仍在 open_questions 台账: {i}")
    else:
        if oq_ids:
            fail("question.yaml 不存在但 open_questions 非空")
        else:
            print("INFO: question.yaml 不存在，闭环对照跳过（无开放提问）")

    # ---------------- 汇总 ----------------
    for m in warns:
        print("WARN:", m)
    for m in fails:
        print("FAIL:", m)
    print(f"spec_check: {len(fn_ids)} FUNC, {len(if_ids)} IF, {len(params)} 参数, "
          + ("全部通过" if not fails else f"{len(fails)} 项失败")
          + (f"（{len(warns)} 项 WARN）" if warns else ""))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
