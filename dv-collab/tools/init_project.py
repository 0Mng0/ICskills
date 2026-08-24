#!/usr/bin/env python3
# init_project.py —— dv-collab §2 工程结构初始化（定稿目录树 + .gitignore）
# 用法: python init_project.py <工程根路径> [--git]
# 幂等：目录/.gitignore 已存在则跳过，重复运行无差异；dv-collab 与
#   design-flow 两侧流程谁先触发都可以（后者已建则前者跳过）。
# --git：无 .git 时执行 git init（默认不碰 git）。
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，统一 UTF-8 输出

DIRS = ["doc/md", "doc/yaml", "rtl/design", "rtl/ref", "rtl/sim",
        "sim", "tools", "work", "migration"]

GITIGNORE = """\
~$*
*.swp
__pycache__/
*.pyc
sim_build/
obj_dir/
*.vcd
*.fst
*.log
*.daidir/
csrc/
work/
migration/
.$*.bkp
.$*.dtmp
"""


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not argv:
        print("用法: python init_project.py <工程根路径> [--git]")
        sys.exit(2)
    root = pathlib.Path(argv[0])
    root.mkdir(parents=True, exist_ok=True)

    for d in DIRS:
        p = root / d
        if p.exists():
            print(f"跳过（已存在）: {d}/")
        else:
            p.mkdir(parents=True)
            print(f"创建: {d}/")

    gi = root / ".gitignore"
    if gi.exists():
        have = set(gi.read_text(encoding="utf-8").splitlines())
        missing = [l for l in GITIGNORE.splitlines() if l and l not in have]
        if missing:
            print(".gitignore 已存在，以下条目未自动添加（需人工确认合并）:")
            for l in missing:
                print("   ", l)
        else:
            print("跳过（已存在且条目齐全）: .gitignore")
    else:
        gi.write_text(GITIGNORE, encoding="utf-8")
        print("创建: .gitignore")

    if "--git" in sys.argv:
        if (root / ".git").exists():
            print("跳过（已存在）: .git/")
        else:
            subprocess.run(["git", "init"], cwd=root)
    print("完成")


if __name__ == "__main__":
    main()
