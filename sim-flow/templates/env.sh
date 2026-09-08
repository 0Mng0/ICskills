# =============================================================================
# sim/env.sh — 验证环境变量（Git Bash 中使用：source env.sh）
# 拷入新工程后，标 ★ 的行按本机实际路径适配：
#   - 原生 Python 目录在最前：让 verilator 的 makefile 里的 python3 解析到原生
#     Python（MSYS2 的 cygwin python 不认 C:/ 路径，会导致 verilator_includer
#     生成空文件）
#   - MSYS2 工具链：verilator / iverilog / make / g++
#   - 末尾激活本工程 .venv（cocotb + pyyaml）
# =============================================================================
# ★ 原生 Python 安装目录（按本机实际改）
export PATH="/c/Users/USERNAME/AppData/Local/Programs/Python/Python313:$PATH"
# ★ MSYS2 安装目录（按本机实际改）
export PATH="/d/msys64/ucrt64/bin:/d/msys64/usr/bin:$PATH"
# 让中文日志不乱码
export PYTHONIOENCODING=utf-8
# 激活本工程虚拟环境（cocotb）
source "$(dirname "${BASH_SOURCE[0]}")/.venv/Scripts/activate"
