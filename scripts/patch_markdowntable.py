#!/usr/bin/env python3
"""让 markdowntable 的表格格式化改走 oxfmt(直接改插件源码, 不用另装东西)。

做法:在插件自己的 out/markdownTableDataHelper.js 末尾追加一段包装,把导出的
toFormatTableStr 换成"先按原逻辑排版,再交给 oxfmt 重排"。插件的 commands.js 是
mtdh.toFormatTableStr(...) 这种属性访问,所以覆盖这个属性就能接管所有格式化出口
(Tab 跳格、增删行列、对齐)。

用法:
    python scripts/patch_markdowntable.py --dry-run   # 只看会改哪个文件
    python scripts/patch_markdowntable.py             # 打补丁(之后重载 VSCode 窗口)
    python scripts/patch_markdowntable.py --revert    # 还原成插件原样
"""

import argparse
import shutil
import sys
from pathlib import Path

MARKER = "/* == markdowntable-oxfmt-table (auto-generated, do not edit) == */"
HELPER = "out/markdownTableDataHelper.js"

# 用 % 而不是 .format():这样 JS 原文里的花括号不用写成 {{ }}
SNIPPET = """
%(marker)s
(function () {
  var cp = require('child_process');
  var original = exports.toFormatTableStr;
  exports.toFormatTableStr = function (tableData) {
    var md = original(tableData);
    try {
      var r = cp.spawnSync(%(oxfmt)s, ['--stdin-filepath', 'table.md'], { input: md, encoding: 'utf8' });
      if (r.status === 0 && typeof r.stdout === 'string' && r.stdout.trim() !== '') {
        return r.stdout.replace(/[\\r\\n]+$/, '');
      }
    } catch (e) {}
    return md;
  };
})();
"""


def find_oxfmt():
    """PATH 里没有就退回 mise 的安装目录(脚本可能跑在没有 shim 的环境里)。"""
    if path := shutil.which("oxfmt"):
        return path
    installed = sorted((Path.home() / ".local/share/mise/installs/oxfmt").glob("*/node_modules/.bin/oxfmt"))
    return str(installed[-1]) if installed else None


def patch(helper, oxfmt, dry_run):
    src = helper.read_text(encoding="utf-8")
    if MARKER in src:
        return "已打过补丁,跳过"
    if "exports.toFormatTableStr" not in src:
        return "找不到 exports.toFormatTableStr,插件结构可能变了"
    if dry_run:
        return "会追加包装"
    helper.write_text(src + SNIPPET % {"marker": MARKER, "oxfmt": repr(oxfmt)}, encoding="utf-8")
    return "已追加包装"


def revert(helper):
    src = helper.read_text(encoding="utf-8")
    if MARKER not in src:
        return "没有本脚本的补丁"
    helper.write_text(src[: src.index(MARKER)].removesuffix("\n"), encoding="utf-8")
    return "已还原"


args = argparse.ArgumentParser()
args.add_argument("--revert", action="store_true", help="去掉本脚本的补丁")
args.add_argument("--dry-run", action="store_true")
args = args.parse_args()

roots = sorted((Path.home() / ".vscode/extensions").glob("takumii.markdowntable-*"))
if not roots:
    sys.exit("找不到 markdowntable:装了才能打补丁")

oxfmt = None
if not args.revert:
    oxfmt = find_oxfmt()
    if not oxfmt:
        sys.exit("找不到 oxfmt 可执行文件(装 oxfmt,或把它加进 PATH)")
    print(f"oxfmt: {oxfmt}")

for root in roots:
    helper = root / HELPER
    if helper.is_file():
        print(f"  {root.name}: {revert(helper) if args.revert else patch(helper, oxfmt, args.dry_run)}")
    else:
        print(f"  {root.name}: 没有 {HELPER}")

if not args.revert and not args.dry_run:
    print("\n重载 VSCode 窗口才会生效(Developer: Reload Window)")
