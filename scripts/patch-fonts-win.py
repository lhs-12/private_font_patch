#!/usr/bin/env python3
"""Windows 字体宽度补丁:单文件,只依赖 fontTools。

    # 跑之前先关掉 VSCode/终端/浏览器等用字体的程序(被占用就只能排到重启时替换)
    pacman -S mingw-w64-ucrt-x86_64-python-fonttools   # 依赖, 装一次
    python scripts/patch-fonts-win.py                  # 打补丁; 自动弹 UAC; 幂等, 全打过了就不提权

改 3 个已装字体(从注册表定位;字体名/文件名不变,VSCode 配置不用动):

    Iosevka Term / Iosevka Term Bold -> cmap 删掉 oxfmt 算 2 格的码点,交给后面的字体
    Noto Color Emoji                 -> advance -> 1em(= 2 格)

改的内容和 Linux 的 scripts/fontpatch.py 完全一样(判据同为 data/width2.tsv),
本文件只是把"找文件 + 权限 + 写回 + 通知系统"换成 Windows 的做法:
字体从注册表(...\\CurrentVersion\\Fonts)定位,写回前自检,被占用的文件排到重启时替换,
换完广播 WM_FONTCHANGE。

字体升级/重装后重跑即可。不备份:要还原就重装字体。
"""

import ctypes
import os
import re
import shutil
import sys
import tempfile
import winreg
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

DATA = Path(__file__).resolve().parents[1] / "data"
FONTS_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
# shortcut: 只打 VSCode 用的 Regular/Bold,要全字重就把其余 Iosevka 家族名加进来
WANTED = {"Iosevka Term": "iosevka", "Iosevka Term Bold": "iosevka", "Noto Color Emoji": "noto"}


# ---- 补丁(与 scripts/fontpatch.py 同一套改动)


def load_widths():
    """oxfmt 判定为 2 格的码点集合。"""
    lines = (DATA / "width2.tsv").read_text(encoding="utf-8").splitlines()
    cps = {int(line, 16) for line in lines if line.strip() and not line.startswith("#")}
    assert 0x2705 in cps and 0x26A0 not in cps, "宽度表和 oxfmt 的行为不符"
    return cps


def load_fonts(inp, lazy):
    """ttc 集合和单 ttf 统一处理。用完 close(): fontTools 会占着文件句柄。"""
    with open(inp, "rb") as f:
        tag = f.read(4)
    if tag == b"ttcf":
        col = TTCollection(inp, lazy=lazy)
        return list(col.fonts), col
    font = TTFont(inp, lazy=lazy)
    return [font], font


def patch_iosevka(inp, out):
    to_remove = load_widths()
    fonts, saver = load_fonts(inp, lazy=False)
    try:
        total = 0
        for i, font in enumerate(fonts):
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
            print(f"  face {i} {font['name'].getDebugName(1)} 删 {len(removal)}")
        saver.save(out)
    finally:
        saver.close()
    print(f"  共删除 {total} 个映射")


def patch_noto(inp, out):
    fonts, saver = load_fonts(inp, lazy=False)
    try:
        font = fonts[0]
        upem = font["head"].unitsPerEm
        changed = 0
        for glyph, (advance, lsb) in list(font["hmtx"].metrics.items()):
            if advance and advance != upem:
                font["hmtx"].metrics[glyph] = (upem, lsb)
                changed += 1
        font["hhea"].advanceWidthMax = upem
        extra = ""
        if "CBLC" in font and "CBDT" in font:
            # 位图版: 位图自带的 advance(px)就是它该被解释成的 ppem,缩放到任何字号正好 1em
            strike = font["CBDT"].strikeData[0]
            npix = strike[min(strike)].metrics.Advance
            for s in font["CBLC"].strikes:
                s.bitmapSizeTable.ppemX = s.bitmapSizeTable.ppemY = npix
            extra = f", CBLC ppem -> {npix}"
        saver.save(out)
    finally:
        saver.close()
    print(f"  hmtx {changed} 个字形 -> {upem}{extra}")


def check_iosevka(inp):
    to_remove = load_widths()
    fonts, saver = load_fonts(inp, lazy=True)
    try:
        return all(not (set(f.getBestCmap()) & to_remove) for f in fonts)
    finally:
        saver.close()


def check_noto(inp):
    fonts, saver = load_fonts(inp, lazy=True)
    try:
        upem = fonts[0]["head"].unitsPerEm
        return all(a in (0, upem) for a, _ in fonts[0]["hmtx"].metrics.values())
    finally:
        saver.close()


# ---- Windows


def find_targets():
    """[(kind, 路径)]: 注册表值名的第一个家族名命中 WANTED 就算,按路径去重。"""
    default = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    seen, out = set(), []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, FONTS_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                name, data, _ = winreg.EnumValue(key, i)
                if not isinstance(data, str) or not data:
                    continue
                family = re.sub(r"\s*\((TrueType|OpenType)\)\s*$", "", name).split(" & ")[0].strip()
                kind = WANTED.get(family)
                path = Path(data)
                path = path if path.is_absolute() else default / path
                if kind and path not in seen:
                    seen.add(path)
                    if path.is_file():
                        out.append((kind, path))
                    else:
                        print(f"!! 字体文件不存在, 跳过: {path}")
    return out


def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def relaunch_elevated():
    """UAC 提权重跑自己(新窗口)。"""
    params = f'"{Path(__file__).resolve()}"'
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, str(Path(__file__).parent), 1)
    return rc > 32


def replace_file(src, dst):
    """src 换到 dst;被占用就排到重启时替换。返回 'replaced' | 'reboot'。"""
    tmp = dst.with_name(dst.name + ".patch-tmp")  # 和目标同卷,重启队列才能接管
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        return "replaced"
    except PermissionError:
        pass
    if ctypes.windll.kernel32.MoveFileExW(str(tmp), str(dst), 0x4):  # DELAY_UNTIL_REBOOT
        return "reboot"
    tmp.unlink(missing_ok=True)
    raise RuntimeError(f"替换失败: {dst}")


def main():
    targets = find_targets()
    if not targets:
        sys.exit("!! 注册表里没找到可用的 Iosevka Term / Iosevka Term Bold / Noto Color Emoji 字体文件")
    check = {"iosevka": check_iosevka, "noto": check_noto}
    pending = [(kind, path) for kind, path in targets if not check[kind](path)]
    if not pending:
        for _, path in targets:
            print(f"   = {path.name} 已打过")
        print("\n✅ 全部已打过, 无需改动")
        return 0
    if not is_admin():
        print("正在申请管理员权限,请在 UAC 对话框点「是」...")
        if relaunch_elevated():
            return 0
        sys.exit("!! 没拿到权限")

    need_reboot = []
    for kind, path in pending:
        patch = {"iosevka": patch_iosevka, "noto": patch_noto}[kind]
        print(f"\n== {path.name} ({kind})")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            out = Path(td) / path.name
            patch(path, out)
            assert check[kind](out), "check 没通过,不写入系统"
            how = replace_file(out, path)
        if how == "reboot":
            need_reboot.append(path)
            print("   -> 文件被占用,已排到重启时替换")
        else:
            print(f"   -> 已写入 {path}")

    # WM_FONTCHANGE: 通知所有窗口字体变了
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 5000, ctypes.byref(ctypes.c_size_t()))
    if need_reboot:
        print("\n!! 这些文件被占用,重启后生效(重启后可再跑一次本脚本确认):")
        for p in need_reboot:
            print(f"     {p}")
    else:
        print("\n✅ 完成。重开 VSCode 后生效。")
    if sys.stdin.isatty():  # UAC 新窗口跑完就关, 留住结果
        input("\n按回车关闭...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
