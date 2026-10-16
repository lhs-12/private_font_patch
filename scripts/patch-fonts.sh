#!/usr/bin/env bash
#
# 字体宽度补丁:改系统字体文件(需要 sudo)。
#   Noto Color Emoji : advance -> 1em, CBLC ppem 109 -> 136
#   Iosevka          : 每个字重的所有 face,从 cmap 删掉 oxfmt 算 2 格的码点
#
# 依赖: python3 + fontTools  ->  sudo pacman -S python-fonttools
# 为什么必须改字体文件(而不是 fontconfig / 注入 CSS),见 README。
# 不产生配置文件,不往用户目录放字体;pacman 覆盖后重跑本脚本即可。
# 判据(data/width2.tsv)变了要先重装字体包再重跑: cmap 删掉回不来(见 README 维护)。
#
#   bash scripts/patch-fonts.sh          # 全部, 并发 4
#   JOBS=2 bash scripts/patch-fonts.sh   # 内存紧张时降并发
#   PYTHON=/path/to/python bash scripts/patch-fonts.sh
#
# 还原: sudo pacman -S ttc-iosevka noto-fonts-emoji && sudo fc-cache -f
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTO=/usr/share/fonts/noto/NotoColorEmoji.ttf
JOBS="${JOBS:-4}"

# 找一个装了 fontTools 的解释器(PYTHON=... 可指定)
for PY in "${PYTHON:-}" python3 python; do
    if [ -n "$PY" ] && "$PY" -c 'import fontTools' 2>/dev/null; then break; fi
    PY=""
done
[ -n "$PY" ] || { echo "!! 找不到装了 fontTools 的 python: sudo pacman -S python-fonttools" >&2; exit 1; }
echo "== python: $PY"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo
echo "== [1/2] Noto Color Emoji =="
if [ -f "$NOTO" ]; then
    "$PY" "$ROOT/scripts/fontpatch.py" noto "$NOTO" "$TMP/NotoColorEmoji.ttf"
    sudo cp -f "$TMP/NotoColorEmoji.ttf" "$NOTO"
    echo "   -> 已写入 $NOTO"
else
    echo "!! 找不到 $NOTO(装了 noto-fonts-emoji 吗?)"
fi

echo
echo "== [2/2] Iosevka 各字重(并发 $JOBS)=="
start=$(date +%s)
for f in /usr/share/fonts/TTF/Iosevka-*.ttc; do
    [ -e "$f" ] || continue
    base="$(basename "$f")"
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 0.3; done # 限流
    (
        if "$PY" "$ROOT/scripts/fontpatch.py" iosevka "$f" "$TMP/$base" >"$TMP/$base.log" 2>&1; then
            sudo cp -f "$TMP/$base" "$f"
            echo "   ✓ $base"
        else
            # 直接打出日志:$TMP 在退出时就被删了,给出路径没用
            echo "   ✗ $base 失败:"
            tail -n 4 "$TMP/$base.log" | sed 's/^/      /'
            : >"$TMP/$base.failed"
        fi
        rm -f "$TMP/$base"
    ) &
done
wait
echo "   Iosevka 用时 $(( $(date +%s) - start )) 秒"
if ls "$TMP"/*.failed >/dev/null 2>&1; then
    echo "!! 有字重没打上补丁, 字体现在不一致(上面有 ✗)" >&2
    exit 1
fi

echo
echo "== 刷新字体缓存 =="
sudo fc-cache -f >/dev/null
echo
echo "✅ 完成。自检:"
echo "   fc-match -f '%{family[0]}\\n' 'Iosevka Term:charset=2705'   # 应为 Noto Color Emoji"
echo "   fc-match -f '%{family[0]}\\n' 'Iosevka Term:charset=20'     # 应为 Iosevka Term"
echo "   fc-match -f '%{family[0]}\\n' sans-serif                    # 应为 Noto Sans"
