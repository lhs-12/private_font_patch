#!/usr/bin/env python3
"""重新导出 data/width2.tsv: oxfmt 判定为 2 格的码点。

oxc 换掉锁定的 unicode-width 版本后判据就变了, 这时重跑本脚本, 再按 README 的维护一节重打字体补丁。
做法是把每个码点单独塞进一张 markdown 表格的格子里, 让 oxfmt 按它自己的宽度补空格, 空格数就是宽度。

用法:
    python scripts/gen_width2.py     # 和现有表比对, 有变化才覆盖, 并报出增减
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "width2.tsv"
HEADER = "# oxfmt 算 2 格的码点(unicode-width); 由 scripts/gen_width2.py 生成; 不在表里的都不是 2 格"
CELL = 4  # 表头 "xxxx" 把这一列撑成 4 格宽, 于是 列宽 - 补的空格数 - 1 = 该格的宽度
CHUNK = 100_000  # 每次调用 oxfmt 都有进程启动开销, 所以切成大块; 再大就只是在拼串和解析上耗时间了
# ASCII 可见字符必然 1 格; 控制字符/代理对/行分隔符放不进表格, 一并跳过
SKIP = set("|\\`*_[]<>&$#+-~\"'!(){}^:;,.?/ =")


def find_oxfmt():
    """PATH 里没有就退回 mise 的安装目录(脚本可能跑在没有 shim 的环境里)。"""
    if path := shutil.which("oxfmt"):
        return path
    installed = sorted((Path.home() / ".local/share/mise/installs/oxfmt").glob("*/node_modules/.bin/oxfmt"))
    return str(installed[-1]) if installed else None


def probe(oxfmt):
    """返回 (2 格的码点集合, 实际探测了多少个码点)。"""
    cps = [
        c
        for c in range(0x110000)
        if c >= 0x20
        and not 0x7F <= c <= 0x9F
        and not 0xD800 <= c <= 0xDFFF
        and c not in (0x2028, 0x2029)
        and chr(c) not in SKIP
    ]
    wide = set()
    for i in range(0, len(cps), CHUNK):
        chunk = cps[i : i + CHUNK]
        src = "| xxxx |\n| --- |\n" + "".join(f"| {chr(c)} |\n" for c in chunk)
        text = subprocess.run(
            [oxfmt, "--stdin-filepath", "table.md"], input=src, capture_output=True, text=True, check=True
        ).stdout
        for c, line in zip(chunk, text.splitlines()[2:], strict=False):
            body = line.strip().strip("|")
            if CELL - (len(body) - len(body.rstrip(" ")) - 1) == 2:
                wide.add(c)
    return wide, len(cps)


def load():
    if not OUT.is_file():
        return set()
    return {
        int(line, 16)
        for line in OUT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


oxfmt = find_oxfmt()
if not oxfmt:
    sys.exit("找不到 oxfmt 可执行文件(装 oxfmt, 或把它加进 PATH)")

old = load()
new, seen = probe(oxfmt)
version = subprocess.run([oxfmt, "--version"], check=False, capture_output=True, text=True).stdout.strip() or oxfmt
print(f"{version.removeprefix('Version: ')} 探测 {seen} 个码点, 2 格 {len(new)} 个")

if new == old:
    print(f"和 {OUT.relative_to(ROOT)} 一致, 没有改动")
    sys.exit(0)

print(f"判据变了: 新增 {len(new - old)} 个, 消失 {len(old - new)} 个")
for c in sorted(new - old)[:8]:
    print(f"  + U+{c:04X}")
for c in sorted(old - new)[:8]:
    print(f"  - U+{c:04X}")
OUT.write_text(HEADER + "\n" + "".join(f"{c:X}\n" for c in sorted(new)), encoding="utf-8")
print(f"已写入 {OUT.relative_to(ROOT)}; 记得重装字体包再重跑 scripts/patch-fonts.sh")
