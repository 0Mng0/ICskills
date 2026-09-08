#!/usr/bin/env bash
# 在 Git Bash（已 source sim/env.sh）中运行：
#   COCOTB_SRC=/path/to/cocotb-2.0.1/src/cocotb bash tools/build_native_mingw.sh
# 用 mingw g++ 重建 cocotb 的 native 库，解决 MSVC 编译的 DLL 与 mingw ABI 不兼容、
# 且官方 Windows 包缺少 Verilator VPI 库的问题。
# 自定位：cocotb 包路径、Python home 与版本均取本脚本上级目录的 sim/.venv。
# 前提：cocotb 的 C 源码树（pip wheel 不含 C++ 源码，需单独下载对应版本源码包，
#       取其中 src/cocotb 目录），通过环境变量 COCOTB_SRC 传入。
set -e

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.venv/Lib/site-packages/cocotb" && pwd)"
VENV_PY="$(dirname "${BASH_SOURCE[0]}")/../.venv/Scripts/python.exe"
SRC="${COCOTB_SRC:?请设置 COCOTB_SRC 指向 cocotb 源码树（含 share/lib 的 src/cocotb 目录）}"
PYHOME="${PYHOME:-$(cygpath -u "$("$VENV_PY" -c 'import sys; print(sys.base_prefix)')")}"
PYVER="$("$VENV_PY" -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")')"
PYDLL="python${PYVER}.dll"
LIBS="$PKG/libs"

INC=(-I"$PKG/share/include" -I"$SRC")
PYINC=(-I"$PYHOME/include")
PYLIB=(-L"$PYHOME" -l:"$PYDLL")
CXXFLAGS=(-std=c++17 -O2 -D__STDC_FORMAT_MACROS -DWIN32)

echo "== gpilog =="
g++ -shared "${CXXFLAGS[@]}" -DGPILOG_EXPORTS "${INC[@]}" \
    "$SRC/share/lib/gpi_log/gpi_logging.cpp" \
    -o "$LIBS/gpilog.dll"

echo "== cocotbutils =="
g++ -shared "${CXXFLAGS[@]}" -DCOCOTBUTILS_EXPORTS "${INC[@]}" \
    "$SRC/share/lib/utils/cocotb_utils.cpp" \
    -L"$LIBS" -l:gpilog.dll \
    -o "$LIBS/cocotbutils.dll"

echo "== pygpilog =="
g++ -shared "${CXXFLAGS[@]}" -DPYGPILOG_EXPORTS "${INC[@]}" "${PYINC[@]}" \
    "$SRC/share/lib/py_gpi_log/py_gpi_logging.cpp" \
    -L"$LIBS" -l:gpilog.dll "${PYLIB[@]}" \
    -o "$LIBS/pygpilog.dll"

echo "== embed =="
g++ -shared "${CXXFLAGS[@]}" -DCOCOTB_EMBED_EXPORTS -DPYTHON_LIB="$PYDLL" -DEMBED_IMPL_LIB=cocotb.dll \
    "${INC[@]}" "${PYINC[@]}" \
    "$SRC/share/lib/embed/embed.cpp" \
    -L"$LIBS" -l:gpilog.dll -l:cocotbutils.dll "${PYLIB[@]}" \
    -o "$LIBS/embed.dll"

echo "== gpi =="
g++ -shared "${CXXFLAGS[@]}" -DGPI_EXPORTS -DLIB_EXT='".dll"' -DSINGLETON_HANDLES \
    "${INC[@]}" \
    "$SRC/share/lib/gpi/GpiCbHdl.cpp" \
    "$SRC/share/lib/gpi/GpiCommon.cpp" \
    -L"$LIBS" -l:cocotbutils.dll -l:gpilog.dll -l:embed.dll \
    -o "$LIBS/gpi.dll"

echo "== cocotb(gpi_embed) =="
g++ -shared "${CXXFLAGS[@]}" "${INC[@]}" "${PYINC[@]}" \
    "$SRC/share/lib/embed/gpi_embed.cpp" \
    -L"$LIBS" -l:gpilog.dll -l:cocotbutils.dll -l:pygpilog.dll -l:gpi.dll "${PYLIB[@]}" \
    -o "$LIBS/cocotb.dll"

echo "== cocotbvpi_verilator (静态库) =="
TMPD=$(mktemp -d)
for f in VpiImpl VpiCbHdl VpiObj VpiIterator VpiSignal; do
    g++ -c -std=c++17 -O2 -D__STDC_FORMAT_MACROS -DCOCOTBVPI_EXPORTS -DVERILATOR "${INC[@]}" \
        "$SRC/share/lib/vpi/$f.cpp" -o "$TMPD/$f.o"
done
ar rcs "$LIBS/libcocotbvpi_verilator.a" "$TMPD"/*.o
rm -rf "$TMPD"

echo "== simulator.pyd (替换 MSVC 版，消除 SxS 清单依赖) =="
PYD="$PKG/simulator.cp${PYVER}-win_amd64.pyd"
cp -n "$PYD" "$PYD.msvc.bak" 2>/dev/null || true
g++ -shared "${CXXFLAGS[@]}" "${INC[@]}" "${PYINC[@]}" \
    "$SRC/share/lib/simulator/simulatormodule.cpp" \
    -L"$LIBS" -l:cocotbutils.dll -l:gpilog.dll -l:gpi.dll -l:pygpilog.dll "${PYLIB[@]}" \
    -o "$PYD"

echo "== cocotbvpi_icarus.vpl (同样存在 ABI 问题，一并重编) =="
TMPD=$(mktemp -d)
dlltool --def "$SRC/share/def/icarus.def" --output-lib "$TMPD/vvp.a"
for f in VpiImpl VpiCbHdl VpiObj VpiIterator VpiSignal; do
    g++ -c -std=c++17 -O2 -D__STDC_FORMAT_MACROS -DWIN32 -DCOCOTBVPI_EXPORTS -DICARUS "${INC[@]}" \
        "$SRC/share/lib/vpi/$f.cpp" -o "$TMPD/$f.o"
done
g++ -shared "$TMPD"/Vpi*.o \
    -L"$LIBS" -l:gpi.dll -l:gpilog.dll -l:cocotbutils.dll \
    "$TMPD/vvp.a" \
    -o "$LIBS/cocotbvpi_icarus.vpl"
rm -rf "$TMPD"

echo "== 全部完成 =="
ls -la "$LIBS" | grep -E "gpi|embed|cocotb|verilator"
