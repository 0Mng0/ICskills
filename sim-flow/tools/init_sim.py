#!/usr/bin/env python3
# init_sim.py —— sim-flow 验证平台脚手架：把 templates/ 平台文件集固化进新工程
# 用法: python init_sim.py <工程根路径> [--module M] [--toplevel T]
#          [--sim verilator|icarus] [--force] [--venv]
#   --module    模块名（默认取工程根目录名），渲染进 regress.yaml
#   --toplevel  DUT 顶层名（默认 <module>_top）
#   --sim       仿真器（默认 verilator；#0.1 NBA 风格 DUT 需 verilator --timing）
#   --force     已存在的文件也覆盖（默认幂等跳过）
#   --venv      顺带建 sim/.venv（cocotb==2.0.1 + pyyaml）并重编 native 库
#               （耗时数分钟；需 Git Bash 环境与 MSYS2 工具链在 PATH）
# 幂等：目录/文件已存在则跳过（--force 除外），重复运行无差异。
import argparse
import pathlib
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一 UTF-8 输出

SKILL_TOOLS = pathlib.Path(__file__).resolve().parent
TEMPLATES = SKILL_TOOLS.parent / "templates"

# templates/ 内的文件 → 工程内的落位（相对 sim/）
FILE_MAP = [
    ("env.sh", "env.sh"),
    ("tb/__init__.py", "tb/__init__.py"),
    ("tb/clocks.py", "tb/clocks.py"),
    ("tb/axi.py", "tb/axi.py"),
    ("tb/apb.py", "tb/apb.py"),
    ("tb/ref_model.py", "tb/ref_model.py"),
    ("tb/scoreboard.py", "tb/scoreboard.py"),
    ("tb/env.py", "tb/env.py"),
    ("tests/__init__.py", "tests/__init__.py"),
    ("tests/test_smoke.py", "tests/test_smoke.py"),
    ("tools/build_native_mingw.sh", "tools/build_native_mingw.sh"),
]

NEXT_STEPS = """\
后续适配清单（详见 sim/templates 来源：sim-flow skill templates/README.md）：
  1) 按目标工程 spec.yaml 适配 tb/ 信号名与寄存器表（各文件头注有适配点）；
  2) source sim/env.sh 后 cd sim/run && python regress.py --build-only 编译，
     核对 sim_build/Vtop.h 顶层端口（接口三级第 2 级），与 spec 不符先登记
     question.yaml，不擅自对齐；
  3) 改 tests/test_smoke.py 的 EXPECTED_PORTS/CSR 复位值/最小数据通路；
  4) python regress.py --case smoke 打通全链路——不过先查配对相位与信号名。
"""


def install_file(src: pathlib.Path, dst: pathlib.Path, force: bool,
                 render: dict | None = None):
    if dst.exists() and not force:
        print(f"跳过（已存在）: {dst.relative_to(dst.parents[1])}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if render:
        text = src.read_text(encoding="utf-8")
        for k, v in render.items():
            text = text.replace(k, v)
        dst.write_text(text, encoding="utf-8")
    else:
        shutil.copyfile(src, dst)
    print(f"生成: {dst.relative_to(dst.parents[1])}")


def main():
    ap = argparse.ArgumentParser(description="sim-flow 验证平台脚手架")
    ap.add_argument("root", help="工程根路径")
    ap.add_argument("--module", help="模块名（默认取工程根目录名）")
    ap.add_argument("--toplevel", help="DUT 顶层名（默认 <module>_top）")
    ap.add_argument("--sim", default="verilator", choices=["verilator", "icarus"])
    ap.add_argument("--force", action="store_true", help="覆盖已存在文件")
    ap.add_argument("--venv", action="store_true", help="建 venv 并重编 native 库")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    module = args.module or root.name
    toplevel = args.toplevel or f"{module}_top"
    sim_dir = root / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    print(f"工程根: {root}  模块: {module}  顶层: {toplevel}  仿真器: {args.sim}")

    for src_rel, dst_rel in FILE_MAP:
        install_file(TEMPLATES / src_rel, sim_dir / dst_rel, args.force)

    # regress.yaml 渲染（module/toplevel/sim）
    install_file(TEMPLATES / "run" / "regress.yaml", sim_dir / "run" / "regress.yaml",
                 args.force, render={"__MODULE__": module, "__TOPLEVEL__": toplevel,
                                     "sim: verilator": f"sim: {args.sim}"})
    # regress.py 用 skill 最新版（工具迭代直接受益）
    install_file(SKILL_TOOLS / "regress.py", sim_dir / "run" / "regress.py", True)
    (sim_dir / "run" / "logs").mkdir(parents=True, exist_ok=True)

    if args.venv:
        venv_py = sim_dir / ".venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            print("跳过（已存在）: sim/.venv")
        else:
            print("创建 sim/.venv 并安装 cocotb==2.0.1 pyyaml ...")
            subprocess.run([sys.executable, "-m", "venv", str(sim_dir / ".venv")],
                           check=True)
            subprocess.run([str(venv_py), "-m", "pip", "install",
                            "cocotb==2.0.1", "pyyaml"], check=True)
        print("重编 cocotb native mingw 库 ...")
        subprocess.run(["bash", str(sim_dir / "tools" / "build_native_mingw.sh")],
                       check=True)

    print("\n平台骨架已就绪。")
    print(NEXT_STEPS)


if __name__ == "__main__":
    main()
