#!/usr/bin/env python3
"""改两个系统字体文件, 让字符宽度和 oxfmt 算的一致:

  noto    : advance 2550 -> 2048(= 1em = 2 格),CBLC ppem 109 -> 136,不重采样位图
  iosevka : 每个 face 的 cmap 删掉"oxfmt 算 2 格"的码点,让这些字符交给后面的字体

判据只看 oxfmt,不看字体自己画了几格 —— 对这 290 个来说两者等价:
Iosevka 的 cmap 里"oxfmt 算 2 格"的码点, 正好就是它自己画 1 格的那批。
删掉后由谁接手、宽度对不对取决于装了哪些字体,见 README 的"还剩什么"。

check   : 判断文件是否已打过补丁, 退出码 0 打过 / 1 没打(patch-fonts.sh 靠它跳过)。

用法: python scripts/fontpatch.py noto|iosevka <输入> <输出>
      python scripts/fontpatch.py check noto|iosevka <文件>
被 patch-fonts.sh 调用。
"""

import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

DATA = Path(__file__).resolve().parents[1] / "data"


def load_widths():
    """oxfmt 判定为 2 格的码点集合。补丁只关心这一侧: 不在表里就不删, 是 0 还是 1 格都无所谓。"""
    cps = set()
    for line in (DATA / "width2.tsv").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            cps.add(int(line, 16))
    # 自检:表必须和 oxfmt 对得上(✅ 2 格;⚠ 1 格,不该在表里)
    assert 0x2705 in cps and 0x26A0 not in cps, "宽度表和 oxfmt 的行为不符"
    return cps


def patch_noto(inp, out):
    font = TTFont(inp, lazy=False)
    upem = font["head"].unitsPerEm
    changed = 0
    for glyph, (advance, lsb) in list(font["hmtx"].metrics.items()):
        if advance and advance != upem:
            font["hmtx"].metrics[glyph] = (upem, lsb)
            changed += 1
    font["hhea"].advanceWidthMax = upem
    # CBDT 位图自带的 advance(px)就是它该被解释成的 ppem,这样缩放到任何字号都正好 1em
    strike = font["CBDT"].strikeData[0]
    npix = strike[min(strike)].metrics.Advance
    for s in font["CBLC"].strikes:
        s.bitmapSizeTable.ppemX = s.bitmapSizeTable.ppemY = npix
    font.save(out)
    print(f"  hmtx {changed} 个字形 -> {upem};hhea.advanceWidthMax -> {upem};CBLC ppem -> {npix}")


def patch_iosevka(inp, out):
    to_remove = load_widths()
    collection = TTCollection(inp, lazy=False)
    total = 0
    for i, font in enumerate(collection.fonts):
        removal = set(font.getBestCmap()) & to_remove
        for table in font["cmap"].tables:
            if table.format in (4, 12):
                for cp in removal & set(table.cmap):
                    del table.cmap[cp]
            elif table.format == 14:
                for cp in removal & set(table.uvsDict):
                    del table.uvsDict[cp]
        assert not removal & set(font.getBestCmap()), f"face {i} 的 cmap 没删干净"
        total += len(removal)
        name = font["name"]
        style = f"{name.getDebugName(1):<24} {name.getDebugName(2):<10}"
        print(f"  face {i:>2} {style} 删 {len(removal)}")
    collection.save(out)
    print(f"  共删除 {total} 个映射")


def check_noto(inp):
    """打过了 = 每个字形 advance 都是 1em。补丁不动 advance=0 的字形(.notdef 之类), 所以 0 也算打过。"""
    font = TTFont(inp, lazy=True)
    upem = font["head"].unitsPerEm
    return all(a in (0, upem) for a, _ in font["hmtx"].metrics.values())


def check_iosevka(inp):
    """打过了 = 每个 face 的 cmap 都没有 width2 里的码点(逐 face 早退, 没打过时快)。"""
    to_remove = load_widths()
    collection = TTCollection(inp, lazy=True)
    return all(not (set(font.getBestCmap()) & to_remove) for font in collection.fonts)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "check" and args[1] in ("noto", "iosevka"):
        sys.exit(0 if (check_noto if args[1] == "noto" else check_iosevka)(args[2]) else 1)
    if len(args) == 3 and args[0] in ("noto", "iosevka"):
        (patch_noto if args[0] == "noto" else patch_iosevka)(args[1], args[2])
    else:
        sys.exit(f"用法: {sys.argv[0]} noto|iosevka <输入> <输出> | check noto|iosevka <文件>")
