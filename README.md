<h1><center>字体宽度补丁</center></h1>

让 emoji 在所有软件里都显示成彩色, 占 2 格(宽度以 `oxfmt` 为准), 同时保持中英 2:1 和等宽.  
做法是给两处系统字体文件和一个 VSCode 插件打补丁, 不加配置文件.

# 背景

这个项目不装新字体, 只用机器上本来就有的这些(都是等宽链上会碰到的):

| 字体                       | 包                             | 用途                                                                             |
| -------------------------- | ------------------------------ | -------------------------------------------------------------------------------- |
| `Iosevka Term`             | `ttc-iosevka`                  | 主字体, 拉丁和符号, 拉丁字宽 `0.5em`                                             |
| `MiSans` / `MiSans L3`     | `ttf-misans` / `ttf-misans-l3` | 汉字, 字宽 `1em`, 和拉丁成 2:1; 编辑器用静态 `MiSans`, fontconfig 用 `MiSans VF` |
| `Noto Color Emoji`         | `noto-fonts-emoji`             | 彩色 emoji; 位图字体, 补丁改的是它的 `hmtx`                                      |
| `Noto Sans Mono CJK KR` 等 | `noto-fonts-cjk`               | 中日韩兜底(含韩文, 1.84 格)                                                      |

fontconfig 的 `monospace` 顺序: `~/.config/fontconfig/conf.d/50-generic.conf` 里 prepend 了这 5 个, 后面的由系统其它 fontconfig 配置接上(装了什么就有什么, 会混进各种日文字体和合成字体):

`Iosevka Term` → `MiSans VF` → `Symbols Nerd Font Mono` → `Noto Color Emoji` → `MiSans L3` → …

VSCode 不走这条链, 走 `editor.fontFamily`: `Iosevka Term`, `MiSans`, `MiSans L3`, `Symbols Nerd Font Mono`, `Noto Color Emoji`(见 "还剩什么" 里的 "终端和编辑器是两条字体链").

# 做了什么

| 文件                                                                          | 改动                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `/usr/share/fonts/noto/NotoColorEmoji.ttf`                                    | `hmtx` advance `2550 → 2048`(`1em` = 2 格); `CBLC` 位图 `ppem` `109 → 136` |
| `/usr/share/fonts/TTF/Iosevka-*.ttc`                                          | 每个 face 的 cmap 删掉 290 个 "`oxfmt` 算 2 格" 的码点                     |
| `~/.vscode/extensions/takumii.markdowntable-*/out/markdownTableDataHelper.js` | 末尾追加一段包装, 让表格格式化改走 `oxfmt`                                 |

字体补丁需要 `python3` + `fontTools`: `sudo pacman -S python-fonttools`(脚本会自己找带 fontTools 的解释器).

```bash
# 字体补丁(可重复跑; 需要 sudo)
bash scripts/patch-fonts.sh

# markdowntable 补丁(改完重载 VSCode 窗口)
python scripts/patch_markdowntable.py

# 想撤销:
sudo pacman -S ttc-iosevka noto-fonts-emoji && sudo fc-cache -f
python scripts/patch_markdowntable.py --revert
```

那 290 个码点从 Iosevka 消失后换给别的字体, 落到哪、宽度对不对, 见 "还剩什么".  
markdowntable 那段包装先按原逻辑排版, 再交给 `oxfmt` 重排; 它的命令(Tab 跳格, 增删行列, 对齐)都是对 `toFormatTableStr` 的属性访问, 所以全部会被接管.

# 怎么算出要删哪些字符

分两步:

1. 拿到 `oxfmt` 的判定: 规则来自 Rust 的 `unicode-width`(oxc 的 `Cargo.lock` 把它锁在 0.2.2), 宽度为 2 的码点写在 `data/width2.tsv`(其余的都不是 2 格).
2. 拿待改字体的 cmap 跟这张表求交集. `fontpatch.py` 里就是一行, 交集就是要从 Iosevka 删掉的码点 —— 当前 290 个, 存在 `data/iosevka-removed.txt`. 对这 290 个来说这个集合正好等于 "Iosevka 自己画的宽度和 `oxfmt` 矛盾" 的那批, 所以是纯静态的差集, 不需要判断别的东西.

Noto 那边用不到这张表: 它的 advance 是固定的 `1.2451em`, 改成 `1em` 就行.

`data/width2.tsv` 由 `scripts/gen_width2.py` 生成: 它把每个码点单独塞进一张 markdown 表格, 让 `oxfmt` 自己补空格, 从而问出每个码点的宽度.

# 结果

打上补丁后, 按 fontconfig 的回退链逐个码点比一遍字体 advance 和 `oxfmt` 的宽度:

- 绝大多数码点两者一致, 也没有豆腐.
- `✅` `❌` `🎉` 这类是彩色 2 格; `⚠` 是 1 格黑白, `⚠︎` 1 格, `⚠️` 2 格彩色.
- 宽度对得上的那些, 编辑器/终端/其它程序表现一致, 不需要任何软件补丁, 也不需要 fontconfig 规则; 对不上的都在下面.

# 还剩什么

打完补丁后仍然对不上的都在这儿. 补丁只删 Iosevka 的 cmap、不补字形, 所以能不能修好取决于后面的字体接不接得住、接住后画几格.

## 184 个: oxfmt 算 1 格, 但全机没有字体能画成 1 格

如 `☁` `☂` `☃` `☎` `♨` `♻` `✂` `✈` `☠` `⛰` `🏔`: `oxfmt` 按 1 格算, 能画出它们的字体(先是 CJK 兜底的 `Noto Sans Mono CJK KR`, 再是 `Noto Color Emoji`)都画 2 格. 全机所有字体面里没有一个能给它们 1 格, 所以不补字形就修不掉. 表格里别写它们, 改用有字形的写法(如 `❄️` `⚠️`), 或直接写 "云" "剪刀" 这样的文字.  
在 kitty 里还有第二个后果: 宽度算 1 格、又只有 `Noto Color Emoji`(纯位图字体)能提供的字符会被画成空白.  
这类字符里, 属于 `Emoji` 属性的写成带 U+FE0F 的 `☁️` `✂️` 就正常了(kitty 会按 emoji 处理, 彩色 2 格); 剩下的标签/组合用途的字符, 本来就不单独显示.

## 23 个: oxfmt 算 1 格, Iosevka 画成 2 格

长箭头 `⟝` `⟵` `⟶` 这一批(`U+27DD-U+27DE`, `U+27F5-U+27FF`, `U+2B33`, `U+1F8D0-U+1F8D8`): 字形是有的, 只是 Iosevka 给它们的 advance 就是 `1em`. 要改它的 `hmtx`, 没做.

## 290 个: oxfmt 算 2 格, 而 Iosevka 只画 1 格

`⌚` `〈` `⏩`、`✅` `❌`、八卦 `☰`、六十四卦 `䷀`、算筹 `𝍠` 等共 290 个(从 `U+231A` 起), 在 Iosevka 里 advance 是 `0.5em` = 1 格, 而 `oxfmt` 按 Unicode 算 2 格 —— 这 290 个正好是 Iosevka 里 "`oxfmt` 算 2 格、它却只画 1 格" 的全部.  
补丁把它们从 Iosevka 删掉、换给别的字体, 换到哪取决于本机装了哪些: 后面的字体画 2 格就对了, 画 1 格就还是不对.  
本机是这几类: 落到 `Noto Color Emoji` / `MS Gothic` / `Symbols Nerd Font Mono` 的对了; 八卦、六十四卦、算筹(`U+268A-U+268F` `U+4DC0-U+4DFF` `U+1D300-U+1D371`)大多落到 `Sarasa Mono CL`, 它画 1 格, 所以没修好.  
要修就得让画全角的字体排在它前面: 可选装的 `I.Ming` 就能把这些都画成 2 格(别排到 Iosevka 前面, 它的拉丁只有 `0.72em`).

## Nerd Font 图标

`Symbols Nerd Font Mono`(等宽链上的兜底层)的字形一律是 `1em`, 也就是 2 格; `oxfmt` 把这类码点(PUA)算 1 格, 所以在编辑器里会偏 1 格(终端把字形塞进固定格子, 看不出来). 常见的 powerline 图标(`U+E0B0` `U+E0A0`)是 `Iosevka Term` 自己提供的(`0.5em`), 不受影响. 这个不打算处理, 表格里别写这些图标.

## 单个国旗字母 `🇦`

也是 1 格还是 2 格的问题, 但两边标准本身就不一致: `oxfmt` 算 1 格, 终端和字体是 2 格.

## 终端和编辑器是两条字体链

终端走 fontconfig 的 `monospace` 列表, 编辑器走 `editor.fontFamily`; 同一个字符由谁渲染, 取决于哪条链先给出字形.  
两边都把 `Noto Color Emoji` 排在 CJK 字体前面, 所以 `☁` `✂` `㊗` `⚽` 这类在终端和编辑器里都是彩色. 韩文音节终端由 `Noto Sans Mono CJK KR` 给、编辑器走系统兜底, 是 1.84 格.

# 为什么改字体文件

fontconfig 改不了宽度: 它的属性里没有 advance 和 ppem, `matrix` 只影响绘制, 排版用的 advance 在字体的 `hmtx` 里.  
VSCode 和 Chromium 也不看 fontconfig 的 charset: 遍历 CSS 字体列表时它们用字体自己的 cmap 判断有没有这个字, fontconfig 的 charset 只在整条列表都失败之后的系统兜底里用到.  
所以往编辑器里注入 CSS 也不行: 只管得了那一个软件, 而且编辑器一升级就要重打一遍; 只有改字体文件能一次覆盖所有软件.

# 目录

```
scripts/patch-fonts.sh          ★ 打字体补丁(需要 sudo)
scripts/fontpatch.py            └ 它调用的两个字体改写(Noto / Iosevka)
scripts/gen_width2.py           └ 重新导出 data/width2.tsv(判据变了才需要跑)
scripts/patch_markdowntable.py  ★ 给 markdowntable 追加 oxfmt 包装
data/width2.tsv                 oxfmt 判定为 2 格的码点
data/iosevka-removed.txt        从 Iosevka 删掉的 290 个码点
docs/验收.md                    肉眼验收: 表格竖线是否对齐
```

# 维护

| 上游变了                                | 怎么做                                                                                      |
| --------------------------------------- | ------------------------------------------------------------------------------------------- |
| `ttc-iosevka` / `noto-fonts-emoji` 升级 | `sudo bash scripts/patch-fonts.sh`(补丁被 pacman 覆盖掉)                                    |
| oxc 换了 `unicode-width` 版本           | `python scripts/gen_width2.py` -> `sudo pacman -S ttc-iosevka noto-fonts-emoji` -> 重跑补丁 |
| markdowntable 升级                      | `python scripts/patch_markdowntable.py`, 然后重载窗口                                       |
| VSCode 升级                             | 不用动                                                                                      |

判据变了必须**先重装字体包再重打**: Iosevka 那个补丁是删 cmap, 不可逆. 改完跑一眼 `docs/验收.md`.
