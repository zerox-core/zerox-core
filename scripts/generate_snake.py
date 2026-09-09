#!/usr/bin/env python3
"""生成贡献日历贪吃蛇动画 SVG（觅食 AI 版）。

与固定蛇形扫格的版本不同：
- 以存在贡献的格子为"食物"，蛇头用 BFS 主动寻找最近的食物块前进，
  路径带随机性（等距方向随机选择 + 少量绕步），减少规律性；
- 像真实贪吃蛇一样，蛇身只会与"还可见的身体段"相撞——路径规划时
  规避最近 RECENT_WINDOW 格，允许跨过早已离开的旧轨迹，因此身体不重叠；
- 途中顺路碰到的食物也会被吃掉（与真实游戏一致）；
- 被吃掉的格子按被吃顺序，在 RECOVER_DELAY 秒后用 RECOVER_DURATION 秒
  渐变恢复原色，形成跟随蛇尾的"恢复波"。

SMIL 注意：calcMode="linear" 时 keyTimes 必须严格递增且首尾为 0/1，
所有动画统一经 animate() 归一化时间轴。
"""
import json
import os
import random
import urllib.request
from collections import deque

USER = os.environ.get("SNAKE_USER", "zerox-core")
TOKEN = os.environ["GITHUB_TOKEN"]

STEP_MAX = 0.11          # 单格耗时上限（秒），路径很长时自动压缩总时长
PATH_SECONDS = 20.0      # 蛇完成整条觅食路径的目标时长（秒）
BODY_LEN = 10            # 可见蛇身长度（格）
RECENT_WINDOW = 16       # 路径规划时视为"会撞上的身体"的窗口（格）
RECOVER_DELAY = 15.0     # 被吃后到开始恢复的等待（秒）
RECOVER_DURATION = 2.0   # 恢复渐变时长（秒）
FADE = 0.5               # 蛇尾淡出时长（秒）
HEAD_HOLD = 1.4          # 蛇头在每个格子停留的倍数（× STEP）
CELL = 10
GAP = 3
RAD = 2
ROWS = 7
EMPTY = "#161b22"
EATEN = "#0d1117"
BODY = "#f0883e"         # 蛇身（橙色系，与绿色贡献块区分）
HEAD_CORE = "#ffe1bd"    # 蛇头亮芯
HEAD_HALO = "#f5a863"    # 蛇头光晕

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


def neighbors(cell, nw):
    w, r = cell
    for dw, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        w2, r2 = w + dw, r + dr
        if 0 <= w2 < nw and 0 <= r2 < ROWS:
            yield (w2, r2)


def bfs(start, blocked, nw):
    """从蛇头出发、避开 blocked 集合的 BFS 距离场。"""
    dist = {start: 0}
    q = deque([start])
    while q:
        c = q.popleft()
        for n in neighbors(c, nw):
            if n not in dist and n not in blocked:
                dist[n] = dist[c] + 1
                q.append(n)
    return dist


def build_path(grid, seed=20260909):
    """觅食 AI：生成蛇头的完整步序，返回 (path, foods_in_eat_order)。"""
    nw = len(grid)
    food = {(w, r) for w in range(nw) for r in range(ROWS) if grid[w][r]["count"] > 0}
    if not food:
        # 无贡献的兜底：退化为蛇形扫格
        path = []
        for w in range(nw):
            rows = range(ROWS) if w % 2 == 0 else range(ROWS - 1, -1, -1)
            for r in rows:
                path.append((w, r))
        return path, []

    rng = random.Random(seed)
    start = (0, 0)
    path = [start]
    eaten = set()
    eaten_order = []
    if start in food:
        eaten.add(start)
        eaten_order.append(start)
    head = start

    while food - eaten:
        remaining = food - eaten
        dist = None
        for window in (RECENT_WINDOW, RECENT_WINDOW // 2, 0):
            blocked = set(path[-window:]) if window else set()
            dist = bfs(head, blocked, nw)
            reachable = {t: dist[t] for t in remaining if t in dist}
            if reachable:
                break
        if not reachable:  # 理论上不会发生：网格最多被 16 格挡住一半
            raise RuntimeError("snake path planning failed: no reachable food")

        target = min(reachable, key=lambda t: (reachable[t], rng.random()))
        # 朝目标走一步：以目标为源做 BFS，选"离目标更近一格"的邻居，随机打破平局。
        # blocked 里可能含蛇头自身（recent 窗口末尾），寻路时必须放行蛇头所在格。
        dist_t = bfs(target, {c for c in blocked if c != head}, nw)
        step_cands = [
            n for n in neighbors(head, nw)
            if n in dist_t and dist_t[n] == dist_t[head] - 1
        ]
        step = rng.choice(step_cands)
        path.append(step)
        if step in remaining:
            eaten.add(step)
            eaten_order.append(step)
        head = step

    return path, eaten_order


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


def build_svg(grid, path, foods):
    nw = len(grid)
    width = nw * (CELL + GAP) + GAP
    height = ROWS * (CELL + GAP) + GAP

    K = len(path)
    step = min(STEP_MAX, PATH_SECONDS / K)  # 路径长时压缩单格耗时
    T_path = K * step
    dur = T_path + RECOVER_DELAY + RECOVER_DURATION

    first_index = {}
    for k, cell in enumerate(path):
        first_index.setdefault(cell, k)
    eat_time = {cell: first_index[cell] * step for cell in foods}

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )

    # 底层：贡献格子。食物被吃后按被吃顺序恢复。
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
            t = eat_time.get((w, r), 0.0)
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

    # 中层：蛇身。每格在蛇头经过后保持 BODY_LEN 格长度，然后淡出。
    for k, (w, r) in enumerate(path):
        x = GAP + w * (CELL + GAP)
        y = GAP + r * (CELL + GAP)
        t = k * step
        points = [
            (0, "0"),
            (t - 0.1, "0"),
            (t, "1"),
            (t + BODY_LEN * step, "1"),
            (t + BODY_LEN * step + FADE, "0"),
        ]
        out.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" fill="{BODY}" opacity="0">'
            f"{animate(points, dur, 'opacity')}</rect>"
        )

    # 顶层：蛇头——光晕 + 亮芯，比身体大一号，行为真实感的关键。
    for k, (w, r) in enumerate(path):
        cx = GAP + w * (CELL + GAP) + CELL / 2
        cy = GAP + r * (CELL + GAP) + CELL / 2
        t = k * step
        hold = HEAD_HOLD * step
        hx = cx - (CELL + 4) / 2
        hy = cy - (CELL + 4) / 2
        halo_points = [
            (0, "0"),
            (t - 0.08, "0"),
            (t, "0.5"),
            (t + hold, "0.5"),
            (t + hold + 0.25, "0"),
        ]
        core_points = [
            (0, "0"),
            (t - 0.05, "0"),
            (t, "1"),
            (t + hold * 0.8, "1"),
            (t + hold * 0.8 + 0.3, "0"),
        ]
        out.append(
            f'<rect x="{hx:.2f}" y="{hy:.2f}" width="{CELL + 4}" height="{CELL + 4}" rx="3.5" '
            f'fill="{HEAD_HALO}" opacity="0">'
            f"{animate(halo_points, dur, 'opacity')}</rect>"
        )
        out.append(
            f'<rect x="{cx - (CELL + 1) / 2:.2f}" y="{cy - (CELL + 1) / 2:.2f}" '
            f'width="{CELL + 1}" height="{CELL + 1}" rx="3" '
            f'fill="{HEAD_CORE}" opacity="0">'
            f"{animate(core_points, dur, 'opacity')}</rect>"
        )

    out.append("</svg>")
    return "\n".join(out), K, dur, step


def main():
    grid = build_grid(fetch_calendar())
    path, foods = build_path(grid)
    svg, cells, dur, step = build_svg(grid, path, foods)
    os.makedirs("dist", exist_ok=True)
    out_path = os.path.join("dist", "github-contribution-grid-snake.svg")
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(svg)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"OK: path {cells} steps, {len(foods)} foods eaten, "
          f"loop {dur:.1f}s (path {cells * step:.1f}s @ {step * 1000:.0f}ms/cell + "
          f"recover {RECOVER_DELAY:.0f}s + {RECOVER_DURATION:.0f}s), {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
