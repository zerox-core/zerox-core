#!/usr/bin/env python3
"""生成个人主页横幅 banner.svg。

- 「零核」用 Ma Shan Zheng（马善政楷书，OFL 开源）的矢量轮廓烘焙进 SVG，
  不依赖查看端字体，任何环境都能稳定显示毛笔艺术字；
- 渐变背景 + 双层波浪，风格对齐 capsule-render 的 waving 模板；
- 副标题为白描英文，用系统无衬线字体直接渲染。
"""
import io
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / ".fonts" / "MaShanZheng-Regular.ttf"
OUT_PATH = ROOT / "assets" / "banner.svg"

W, H = 854.0, 230.0
TITLE = "零核"
TITLE_SIZE = 96
DESC = "安静做事，让证据说话。"
DESC_SIZE = 20

GRAD_TOP = "#3b82f6"   # 蓝
GRAD_BOTTOM = "#22c55e"  # 绿


def emit_text_paths(font, text, size, cx, baseline_y, fill, letter_spacing=0.12):
    """把整句文字转成 <path> 组，水平居中于 cx。"""
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    upem = font["head"].unitsPerEm
    scale = size / upem

    advances = []
    paths = []
    for ch in text:
        glyph = glyph_set[cmap[ord(ch)]]
        pen = SVGPathPen(glyph_set)
        glyph.draw(pen)
        advances.append(glyph.width * scale + letter_spacing * size)
        paths.append(pen.getCommands())

    total = sum(advances) - letter_spacing * size
    x = cx - total / 2
    out = []
    for d, adv in zip(paths, advances):
        if d:
            out.append(
                f'<path transform="translate({x:.2f},{baseline_y:.2f}) '
                f'scale({scale:.6f},-{scale:.6f})" d="{d}" fill="{fill}"/>'
            )
        x += adv
    return "\n".join(out), total


def main():
    font = TTFont(str(FONT_PATH))

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}">'
    )
    parts.append(
        "<defs>"
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{GRAD_TOP}"/>'
        f'<stop offset="1" stop-color="{GRAD_BOTTOM}"/>'
        "</linearGradient>"
        "</defs>"
        f'<rect width="{W:.0f}" height="{H:.0f}" fill="url(#bg)"/>'
    )
    # 底部双层波浪（半透明），对齐 capsule-render waving 的观感
    parts.append(
        f'<path d="M0,{H - 52} C {W * 0.25},{H - 92} {W * 0.42},{H - 12} {W * 0.62},{H - 40} '
        f'C {W * 0.80},{H - 64} {W * 0.92},{H - 34} {W},{H - 52} L {W},{H} L 0,{H} Z" '
        'fill="#ffffff" opacity="0.14"/>'
    )
    parts.append(
        f'<path d="M0,{H - 30} C {W * 0.22},{H - 58} {W * 0.45},{H - 6} {W * 0.70},{H - 26} '
        f'C {W * 0.86},{H - 40} {W * 0.94},{H - 18} {W},{H - 30} L {W},{H} L 0,{H} Z" '
        'fill="#000000" opacity="0.18"/>'
    )

    # 主标题：毛笔楷书「零核」，居中
    title_paths, _ = emit_text_paths(font, TITLE, TITLE_SIZE, W / 2, 128, "#ffffff")
    parts.append(title_paths)
    # 标题右侧落款式小字（可选装饰）：印章式方块
    parts.append(
        f'<rect x="{W / 2 + 118:.1f}" y="58" width="34" height="34" rx="4" '
        'fill="#ffffff" opacity="0.16"/>'
    )
    parts.append(
        f'<text x="{W / 2 + 135:.1f}" y="80" text-anchor="middle" font-size="14" '
        'font-family="serif" fill="#ffffff" opacity="0.85">Xice</text>'
    )

    # 副标题
    parts.append(
        f'<text x="{W / 2:.1f}" y="{170}" text-anchor="middle" font-size="{DESC_SIZE}" '
        'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        f'fill="#ffffff" opacity="0.92" letter-spacing="0.5">{DESC}</text>'
    )

    parts.append("</svg>")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(parts), encoding="utf-8")
    print(f"OK: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
