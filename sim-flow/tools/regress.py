#!/usr/bin/env python3
"""regress.py —— cocotb 回归执行器（sim-flow skill 自带，拷至工程 sim/run/ 适配）

把 references/regression.md 的回归纪律落成工具：
- 按 regress.yaml 逐用例跑 cocotb 仿真，随机用例 seed 进日志名；
- 判过看日志实质（不看进程退出码），四态分类 pass/fail/incomplete/interrupt；
- 每用例独立子进程执行，自带超时兜底（挂死 = incomplete，不挂死整轮回归）；
- 汇总回归产物（计数、未解释失败、环境指纹），更新 sim/status.yaml；
- 任一用例 fail → 进程非零退出。

依赖：Python ≥ 3.9、cocotb 2.x（cocotb_tools.runner）、仿真器在 PATH。
PyYAML 可选：缺失时 regress.yaml 可按 JSON 写（YAML 兼容 JSON），
status.yaml / vp_table / spec 相关更新整体跳过（只告警，不影响四态判定）。

本脚本只是执行手段：四态判定规则与失败处理纪律以 references/regression.md 为准。
"""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
import os
import platform
import random
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml  # PyYAML，可选
except ImportError:
    yaml = None

# ------------------------------------------------------------------ 四态判定
# cocotb 2.x 正常收尾在总结表打印：TESTS=<n> PASS=<n> FAIL=<n> SKIP=<n>
SUMMARY_RE = re.compile(r"TESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)\s+SKIP=(\d+)")

DEFAULT_FAIL_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"SCOREBOARD\s+RESIDUE",
    r"\bFATAL\b",
    r"%Error",          # Verilator 编译/elaboration 错误
    r"\berror:",        # iverilog/gcc 编译错误
]
DEFAULT_PASS_PATTERNS: list = []    # 项目可自行追加额外 pass 证据
DEFAULT_INTERRUPT_PATTERNS = [
    r"MemoryError",
    r"KeyboardInterrupt",
    r"out of memory",
]


def classify_log(text, fail_patterns, pass_patterns, interrupt_patterns):
    """四态分类。fail 优先于 incomplete；interrupt 仅用于外部中断证据。"""
    m = SUMMARY_RE.search(text)
    if m:
        _t, p, f, _s = (int(g) for g in m.groups())
        if f > 0:
            return "fail"
        if p > 0:
            return "pass"
    for pat in interrupt_patterns:
        if re.search(pat, text):
            return "interrupt"
    for pat in fail_patterns:
        if re.search(pat, text):
            return "fail"
    if m:  # 有总结但 PASS=0 FAIL=0（如全 SKIP）
        return "pass"
    for pat in pass_patterns:
        if re.search(pat, text):
            return "pass"
    return "incomplete"


# ------------------------------------------------------------------ 配置与路径
def load_config(cfg_path: Path) -> dict:
    text = cfg_path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    try:  # YAML 兼容 JSON：无 PyYAML 时配置可按 JSON 写
        return json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit("缺少 PyYAML 且配置不是 JSON：pip install pyyaml，"
                         "或将 regress.yaml 写成 JSON")


def parse_flist(flist: Path):
    """解析设计侧 flist 的受支持子集：空行、# 与 // 注释、源码路径、+incdir+<path>。

    相对路径按 flist 所在目录解析为绝对路径。其余语法不猜、直接报错，
    提示改用 regress.yaml 的 extra_sources / build_args 显式给出。
    """
    sources, includes = [], []
    for lineno, raw in enumerate(flist.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("+incdir+"):
            includes.append(str((flist.parent / line[len("+incdir+"):]).resolve()))
        elif line.startswith(("-", "+")):
            raise SystemExit(f"{flist}:{lineno}: 不支持的 flist 语法 {line!r}；"
                             f"请改在 regress.yaml 的 extra_sources/build_args 显式给出")
        else:
            sources.append(str((flist.parent / line).resolve()))
    return sources, includes


# ------------------------------------------------------------------ 环境指纹
def _run_text(cmd, timeout=10):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def tool_version(cmd):
    first = _run_text(cmd).splitlines()
    return first[0].strip() if first else "unknown"


def git_baseline(root: Path, subdir: str):
    head = _run_text(["git", "-C", str(root), "rev-parse", "--short", "HEAD"])
    if not head:
        return "unknown"
    dirty = _run_text(["git", "-C", str(root), "status", "--porcelain", "--", subdir])
    return head.splitlines()[0] + ("-dirty" if dirty else "")


def env_fingerprint(sim: str) -> dict:
    try:
        cocotb_ver = importlib.metadata.version("cocotb")
    except importlib.metadata.PackageNotFoundError:
        cocotb_ver = "unknown"
    ver_cmd = {"icarus": ["iverilog", "-V"], "verilator": ["verilator", "--version"]}.get(sim)
    return {
        "sim": sim,
        "sim_version": tool_version(ver_cmd) if ver_cmd else "unknown",
        "cocotb": cocotb_ver,
        "python": platform.python_version(),
    }


# ------------------------------------------------------------------ worker
def run_worker(cfg_path: Path, case_name: str, seed_tag: str, seed_value,
               log_path: Path, waves: bool):
    """单用例执行体（子进程内运行）：build（增量）+ test，日志写 log_path。"""
    cfg = load_config(cfg_path)
    base = cfg_path.parent
    case = next(c for c in cfg["cases"] if c["name"] == case_name)

    for p in cfg.get("pythonpath", []):
        abs_p = str((base / p).resolve())
        sys.path.insert(0, abs_p)
        os.environ["PYTHONPATH"] = abs_p + os.pathsep + os.environ.get("PYTHONPATH", "")

    from cocotb_tools.runner import get_runner
    runner = get_runner(cfg["sim"])

    # cocotb 2.x 的 runner 只向 DUT 进程传 COCOTB_RANDOM_SEED；显式同步旧变量
    # RANDOM_SEED，兼容仍读旧变量的用例（防激励 seed 静默恒 1、复现失效）。
    os.environ["RANDOM_SEED"] = str(seed_value)

    sources, includes = parse_flist((base / cfg["rtl_flist"]).resolve())
    sources += [str((base / s).resolve()) for s in cfg.get("extra_sources", [])]
    includes += [str((base / d).resolve()) for d in cfg.get("includes", [])]

    build_dir = (base / cfg.get("build_dir", "sim_build")).resolve()
    test_dir = (base / cfg.get("test_root", "run") / f"{case_name}_{seed_tag}").resolve()
    test_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        runner.build(
            sources=sources,
            includes=includes,
            defines=cfg.get("defines", {}),
            parameters=cfg.get("parameters", {}),
            build_args=cfg.get("build_args", []),
            hdl_toplevel=cfg["toplevel"],
            build_dir=build_dir,
            timescale=tuple(cfg.get("timescale", ["1ns", "1ps"])),
            waves=waves,
        )
        runner.test(
            test_module=case.get("module", cfg["test_module"]),
            hdl_toplevel=cfg["toplevel"],
            testcase=case.get("testcase"),
            seed=seed_value,
            waves=waves,
            build_dir=build_dir,
            test_dir=test_dir,
            log_file=log_path,
        )
    except SystemExit:
        raise
    except Exception:
        # worker 自身异常也落进用例日志（Traceback 会被四态分类判 fail）
        import traceback
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n[regress worker] exception:\n")
            traceback.print_exc(file=f)
        raise


# ------------------------------------------------------------------ status.yaml
def update_status(cfg_path: Path, cfg: dict, results: list, argv: list):
    if yaml is None:
        print("[regress] 警告：无 PyYAML，跳过 status.yaml 更新（pip install pyyaml）")
        return
    base = cfg_path.parent
    status_path = (base / cfg.get("status", "../status.yaml")).resolve()
    root = (base / cfg.get("project_root", "../..")).resolve()

    status = {}
    if status_path.exists():
        status = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}

    # spec 基线（digest 自 spec.yaml 头部字段）
    spec_base = None
    spec_rel = cfg.get("spec")
    if spec_rel:
        spec_path = (base / spec_rel).resolve()
        if spec_path.exists():
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
            doc = spec.get("doc", {})
            spec_base = (f"{doc.get('id', 'SPEC-?')} v{doc.get('version', '?')} "
                         f"@{doc.get('commit_id', '?')} (stage={doc.get('stage', '?')})")

    # VP 计数（vp_table.yaml 存在才填）
    vp_summary = None
    vp_rel = cfg.get("vp_table")
    if vp_rel:
        vp_path = (base / vp_rel).resolve()
        if vp_path.exists():
            vp = yaml.safe_load(vp_path.read_text(encoding="utf-8")) or {}
            counts = {}
            for v in vp.get("verification_points", []):
                s = v.get("status", "open")
                counts[s] = counts.get(s, 0) + 1
            vp_summary = {"total": len(vp.get("verification_points", [])), **counts}

    counts = {"pass": 0, "fail": 0, "incomplete": 0, "interrupt": 0}
    for r in results:
        counts[r["state"]] += 1

    status.update({
        "schema_version": 1,
        "module": cfg.get("module", status.get("module", "?")),
        "updated_at": datetime.date.today().isoformat(),
    })
    if spec_base:
        status["spec_baseline"] = spec_base
    status["dut_baseline"] = git_baseline(root, "rtl")
    if vp_summary is not None:
        status["vp_summary"] = vp_summary
    status["last_regression"] = {
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "command": " ".join(argv),
        "total": len(results),
        **counts,
        "cases": [{"name": r["name"], "seed": r["seed_tag"],
                   "state": r["state"], "log": r["log"]} for r in results],
        "env": env_fingerprint(cfg["sim"]),
    }

    # open_issues 自 question.yaml 派生（regress.yaml 配置 question: 才启用）：
    # closed_at 缺失 = 未闭环，按 blocking 分桶；bugs 段保留既有内容不派生。
    q_rel = cfg.get("question")
    if q_rel:
        q_path = (base / q_rel).resolve()
        if q_path.exists():
            qdoc = yaml.safe_load(q_path.read_text(encoding="utf-8")) or {}
            open_q = [q for q in qdoc.get("questions", []) if not q.get("closed_at")]
            old_oi = status.get("open_issues")
            bugs = old_oi.get("bugs", []) if isinstance(old_oi, dict) else []
            status["open_issues"] = {
                "bugs": bugs or [],
                "question_blocking": sorted(q["id"] for q in open_q if q.get("blocking")),
                "question_open_nonblocking": sorted(
                    q["id"] for q in open_q if not q.get("blocking")),
            }

    # 未解释失败：按 (testcase, seed) 合并旧条目备注，已恢复 pass 的自动移出
    prev = {}
    for e in status.get("unexplained_failures", []) or []:
        if isinstance(e, dict):
            prev[(e.get("testcase"), str(e.get("seed")))] = e
    unexplained = []
    for r in results:
        if r["state"] in ("fail", "incomplete"):
            old = prev.get((r["name"], str(r["seed_tag"])), {})
            unexplained.append({"testcase": r["name"], "seed": r["seed_tag"],
                                "log": r["log"], "repro": r.get("repro", ""),
                                "note": old.get("note", "待定位")})
    status["unexplained_failures"] = unexplained

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        yaml.dump(status, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[regress] status.yaml 已更新：{status_path}")


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description="cocotb 回归执行器（sim-flow）")
    ap.add_argument("-c", "--config", default=str(Path(__file__).parent / "regress.yaml"))
    ap.add_argument("--case", help="只跑指定用例，逗号分隔")
    ap.add_argument("--seed", type=int, help="覆盖随机用例 seed（配合 --case 单用例复现）")
    ap.add_argument("--repeat", type=int, help="覆盖随机用例重复次数")
    ap.add_argument("--waves", action="store_true", help="所有用例开波形")
    ap.add_argument("--timeout", type=int, help="覆盖每用例超时秒数")
    ap.add_argument("--no-status", action="store_true", help="不更新 status.yaml")
    ap.add_argument("--build-only", action="store_true", help="只编译 DUT，不跑用例")
    # worker 内部参数（子进程模式，人不直接用）
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--case-name", help=argparse.SUPPRESS)
    ap.add_argument("--seed-tag", help=argparse.SUPPRESS)
    ap.add_argument("--seed-value", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--log", help=argparse.SUPPRESS)
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()

    if args.worker:
        run_worker(cfg_path, args.case_name, args.seed_tag, args.seed_value,
                   Path(args.log), args.waves)
        return

    cfg = load_config(cfg_path)
    base = cfg_path.parent
    logs_dir = (base / cfg.get("logs_dir", "logs")).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    timeout_default = args.timeout or cfg.get("timeout", 300)

    # 用例展开：repeat 只对随机用例有意义；定向用例 seed=fixed 只跑一次
    runs = []
    for case in cfg["cases"]:
        if args.case and case["name"] not in args.case.split(","):
            continue
        seed_cfg = case.get("seed", "fixed")
        if args.seed is not None:
            runs.append((case, f"seed{args.seed}", args.seed))
        elif seed_cfg == "fixed":
            runs.append((case, "fixed", 0))
        elif isinstance(seed_cfg, int):
            runs.append((case, f"seed{seed_cfg}", seed_cfg))
        else:  # random
            for _ in range(args.repeat or case.get("repeat", 1)):
                runs.append((case, None, None))  # seed 运行时现取并落名
    if not runs:
        raise SystemExit("没有匹配的执行项（检查 --case 过滤与 regress.yaml）")

    expanded = []
    for case, tag, seed in runs:
        if tag is None:
            seed = random.randrange(1, 2**31)
            tag = f"seed{seed}"
        expanded.append((case, tag, seed))

    if args.build_only:
        # 借第一个执行项的 worker 做编译验证（build 后 test 前由超时/错误暴露）
        print("[regress] --build-only：仅编译，不跑用例")
        # 直接在本进程 build 一次
        sources, includes = parse_flist((base / cfg["rtl_flist"]).resolve())
        sources += [str((base / s).resolve()) for s in cfg.get("extra_sources", [])]
        includes += [str((base / d).resolve()) for d in cfg.get("includes", [])]
        from cocotb_tools.runner import get_runner
        get_runner(cfg["sim"]).build(
            sources=sources, includes=includes,
            defines=cfg.get("defines", {}), parameters=cfg.get("parameters", {}),
            build_args=cfg.get("build_args", []), hdl_toplevel=cfg["toplevel"],
            build_dir=(base / cfg.get("build_dir", "sim_build")).resolve(),
            timescale=tuple(cfg.get("timescale", ["1ns", "1ps"])),
            waves=bool(args.waves or cfg.get("waves_default", False)))
        print("[regress] 编译通过")
        return

    fail_patterns = cfg.get("fail_patterns", DEFAULT_FAIL_PATTERNS)
    pass_patterns = cfg.get("pass_patterns", DEFAULT_PASS_PATTERNS)
    interrupt_patterns = cfg.get("interrupt_patterns", DEFAULT_INTERRUPT_PATTERNS)

    results = []
    for case, tag, seed in expanded:
        name = case["name"]
        log_path = logs_dir / f"{name}_{tag}.log"
        waves = bool(args.waves or case.get("waves", cfg.get("waves_default", False)))
        timeout = args.timeout or case.get("timeout", timeout_default)
        cmd = [sys.executable, str(Path(__file__).resolve()),
               "--worker", "-c", str(cfg_path),
               "--case-name", name, "--seed-tag", tag, "--seed-value", str(seed),
               "--log", str(log_path)] + (["--waves"] if waves else [])
        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
            worker_out = (proc.stdout or "") + (proc.stderr or "")
            if worker_out.strip():
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write("\n[regress worker stdout]\n" + worker_out)
        except subprocess.TimeoutExpired:
            state = "incomplete"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[regress] timeout after {timeout}s → incomplete\n")
            proc = None
        elapsed = time.monotonic() - t0

        if proc is not None:
            text = log_path.read_text(encoding="utf-8", errors="replace") \
                if log_path.exists() else ""
            if not text.strip():
                text = "(worker 无输出，疑似启动失败)"
            state = classify_log(text, fail_patterns, pass_patterns, interrupt_patterns)

        rel_log = os.path.relpath(log_path, base)
        repro = f"python regress.py --case {name}" + (
            f" --seed {seed}" if tag != "fixed" else "")
        results.append({"name": name, "seed_tag": tag, "state": state,
                        "log": rel_log, "repro": repro})
        print(f"{state.upper():11s} {name} ({tag})  {rel_log}  {elapsed:.1f}s")
        if state in ("fail", "incomplete"):
            print(f"{'':11s} ↳ 复现: {repro}")

    counts = {"pass": 0, "fail": 0, "incomplete": 0, "interrupt": 0}
    for r in results:
        counts[r["state"]] += 1
    print(f"[regress] total={len(results)} pass={counts['pass']} fail={counts['fail']} "
          f"incomplete={counts['incomplete']} interrupt={counts['interrupt']}")

    if not args.no_status:
        update_status(cfg_path, cfg, results, sys.argv)

    # 纪律：任一用例 fail → 非零退出（incomplete/interrupt 不改变退出码，但已落清单）
    sys.exit(1 if counts["fail"] > 0 else 0)


if __name__ == "__main__":
    main()
