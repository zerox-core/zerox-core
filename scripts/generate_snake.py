#!/usr/bin/env python3
"""生成贡献日历贪吃蛇动画 SVG。

与通用 snk 的区别：被蛇吃掉的格子不是保持空缺到循环结束，而是按被吃顺序
依次恢复——每格在被吃约 RECOVER_DELAY 秒后，用 RECOVER_DURATION 秒渐变回
原始贡献色，形成一条跟随蛇尾的"恢复波"。

SMIL 注意：calcMode="linear" 时 keyTimes 必须严格递增且首尾为 0/1，
所有动画都通过 animate() 统一归一化时间轴。
"""
import json
import os
import urllib.request

USER = os.environ.get("SNAKE_USER", "zerox-core")
TOKEN = os.environ["GITHUB_TOKEN"]

STEP = 0.045            # 蛇头经过一格用时（秒）
BODY_LEN = 10           # 蛇身长度（格）
RECOVER_DELAY = 15.0    # 被吃后到开始恢复的等待（秒）
RECOVER_DURATION = 2.0  # 恢复渐变时长（秒）
FADE = 0.5              # 蛇尾淡出时长（秒）
CELL = 10               # 单元格边长（px）
GAP = 3                 # 单元格间距（px）
RAD = 2                 # 圆角半径（px）
ROWS = 7
EMPTY = "#161b22"       # 无贡献格子
EATEN = "#0d1117"       # 被吃掉的格子（比空格子更暗，像被挖掉）
BODY = "#39d353"        # 蛇身
HEAD = "#9be9a8"        # 蛇头

QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
            color
            weekday
          }
        }
      }
    }
  }
}"""


def fetch_calendar():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "contribution-snake-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data or not data.get("data"):
        raise RuntimeError(f"GraphQL error: {json.dumps(data)[:500]}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    if not weeks:
        raise RuntimeError("empty contribution calendar")
    return weeks


def build_grid(weeks):
    """按 weekday 补齐为 7 行的矩形网格；缺失的日期视为空格子。"""
    grid = []
    for w in weeks:
        col = [None] * ROWS
        for d in w["contributionDays"]:
            col[d["weekday"]] = {"count": d["contributionCount"], "color": d["color"]}
        for r in range(ROWS):
            if col[r] is None:
                col[r] = {"count": 0, "color": None}
        grid.append(col)
    return grid


def f(x):
    return f"{x:.5f}"


def animate(points, dur, attr):
    """把 (time_seconds, value) 序列规范成合法的 SMIL animate 元素。

    - 时间负值截断为 0，同一时刻的重复点保留最后一个值；
    - 时间轴不足 dur 时补一个"保持末值"的收尾点，保证 keyTimes 首尾为 0/1。
    """
    pts = sorted((max(t, 0.0), v) for t, v in points)
    cleaned = []
    for t, v in pts:
        if cleaned and abs(cleaned[-1][0] - t) < 1e-9:
            cleaned[-1] = (t, v)
        else:
            cleaned.append((t, v))
    if dur - cleaned[-1][0] > 1e-9:
        cleaned.append((dur, cleaned[-1][1]))
    vals = ";".join(v for _, v in cleaned)
    keys = ";".join(f(min(t / dur, 1.0)) for t, _ in cleaned)
    return (
        f'<animate attributeName="{attr}" dur="{dur:.3f}s" repeatCount="indefinite" '
        f'calcMode="linear" values="{vals}" keyTimes="{keys}"/>'
    )


def build_svg(grid):
    nw = len(grid)
    width = nw * (CELL + GAP) + GAP
    height = ROWS * (CELL + GAP) + GAP

    # 蛇形路径：偶数列自上而下，奇数列自下而上
    path = []
    for w in range(nw):
        rows = range(ROWS) if w % 2 == 0 else range(ROWS - 1, -1, -1)
        for r in rows:
            path.append((w, r))

    K = len(path)
    dur = K * STEP + RECOVER_DELAY + RECOVER_DURATION
    index_of = {cell: k for k, cell in enumerate(path)}

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )

    # 底层：贡献格子。有贡献的格子被吃后按被吃顺序依次恢复。
    for w, col in enumerate(grid):
        for r, cell in enumerate(col):
            x = GAP + w * (CELL + GAP)
            y = GAP + r * (CELL + GAP)
            color = cell["color"] or EMPTY
            if cell["count"] <= 0:
                out.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" fill="{EMPTY}"/>'
                )
                continue
            t = index_of[(w, r)] * STEP
            points = [
                (0, color),
                (t - 0.2, color),
                (t, EATEN),
                (t + RECOVER_DELAY, EATEN),
                (t + RECOVER_DELAY + RECOVER_DURATION, color),
            ]
            out.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" fill="{color}">'
                f"{animate(points, dur, 'fill')}</rect>"
            )

    # 中层：蛇身。每格在蛇头经过后保持 BODY_LEN 格的长度，然后淡出。
    for k, (w, r) in enumerate(path):
        x = GAP + w * (CELL + GAP)
        y = GAP + r * (CELL + GAP)
        t = k * STEP
        points = [
            (0, "0"),
            (t - 0.1, "0"),
            (t, "1"),
            (t + BODY_LEN * STEP, "1"),
            (t + BODY_LEN * STEP + FADE, "0"),
        ]
        out.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" fill="{BODY}" opacity="0">'
            f"{animate(points, dur, 'opacity')}</rect>"
        )

    # 顶层：蛇头高亮。
    for k, (w, r) in enumerate(path):
        x = GAP + w * (CELL + GAP)
        y = GAP + r * (CELL + GAP)
        t = k * STEP
        points = [
            (0, "0"),
            (t - 0.08, "0"),
            (t, "1"),
            (t + 1.4 * STEP, "1"),
            (t + 1.4 * STEP + 0.3, "0"),
        ]
        out.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" fill="{HEAD}" opacity="0">'
            f"{animate(points, dur, 'opacity')}</rect>"
        )

    out.append("</svg>")
    return "\n".join(out), K, dur


def main():
    grid = build_grid(fetch_calendar())
    svg, cells, dur = build_svg(grid)
    os.makedirs("dist", exist_ok=True)
    out_path = os.path.join("dist", "github-contribution-grid-snake.svg")
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(svg)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"OK: {cells} cells, loop {dur:.1f}s (path {cells * STEP:.1f}s + "
          f"recover {RECOVER_DELAY:.0f}s + {RECOVER_DURATION:.0f}s fade), {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
