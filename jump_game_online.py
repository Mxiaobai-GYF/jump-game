# -*- coding: utf-8 -*-
"""
跳一跳 Pygame 版 - 带登录/注册/分数提交/排行榜渲染
===================================================
运行方式: 先启动 FastAPI 后端，再运行本文件

运行步骤:
  终端1: cd 项目目录 && uvicorn main:app --reload --port 8000
  终端2: python jump_game_online.py

【修改标注】
==========================================================
* [新增] 顶部配置区 (FASTAPI_URL, 窗口大小等)
* [新增] 终端登录/注册流程 (input + requests)
* [新增] submit_and_fetch() 后台线程提交分数+拉取排行榜
* [新增] Pygame 游戏主循环 (玩家、平台、跳跃、物理)
* [新增] 游戏结束界面用 pygame.font 渲染排行榜文字
==========================================================
"""

import pygame
import requests
import sys
import threading
import random
import math

# ==================== 配置区 ====================
FASTAPI_URL = "http://127.0.0.1:8000"
SCREEN_WIDTH = 400
SCREEN_HEIGHT = 700
# ===============================================

# ==================== [修改] 终端登录/注册 — 失败循环重试 ====================
print("=" * 50)
print("  跳一跳 Pygame - 登录 / 注册")
print("=" * 50)
print()
print("  提示: 输入错误后可以重新选择，关闭窗口即可退出")
print()

player_id = None
username = ""
password = ""

while player_id is None:
    print("1. 登录")
    print("2. 注册")
    print("0. 退出程序")
    choice = input("请选择 (1/2/0): ").strip()

    if choice == "0":
        print("\n再见！")
        sys.exit(0)

    if choice not in ("1", "2"):
        print("输入无效，请重试\n")
        continue

    tmp_user = input("用户名: ").strip()
    tmp_pass = input("密码: ").strip()

    try:
        if choice == "2":
            resp = requests.post(
                f"{FASTAPI_URL}/signup",
                json={"username": tmp_user, "password": tmp_pass},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                player_id = data["player_id"]
                username = tmp_user
                password = tmp_pass
                print(f"\n[注册成功] 欢迎 {username}！")
            else:
                err_msg = data.get("detail", "未知错误")
                print(f"\n注册失败: {err_msg}")
        else:
            resp = requests.post(
                f"{FASTAPI_URL}/login",
                json={"username": tmp_user, "password": tmp_pass},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                player_id = data["player_id"]
                username = tmp_user
                password = tmp_pass
                print(f"\n[欢迎回来] {username}！")
            else:
                print(f"\n登录失败，用户名或密码错误")
    except requests.exceptions.ConnectionError:
        print(f"\n无法连接后端服务器 ({FASTAPI_URL})，请确认服务器已启动\n")

    if player_id is None:
        print()  # 空行分隔，方便继续尝试

print()
# ==========================================================


# ==================== [新增] Pygame 初始化 ====================
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("跳一跳")
clock = pygame.time.Clock()

# -- 字体 --
try:
    font_title = pygame.font.SysFont("simhei", 44)
    font_big = pygame.font.SysFont("simhei", 36)
    font_mid = pygame.font.SysFont("simhei", 24)
    font_small = pygame.font.SysFont("simhei", 18)
except Exception:
    font_title = pygame.font.Font(None, 44)
    font_big = pygame.font.Font(None, 36)
    font_mid = pygame.font.Font(None, 24)
    font_small = pygame.font.Font(None, 18)

# -- 颜色 --
COLORS = {
    "bg_top": (26, 26, 46),
    "bg_bot": (15, 52, 96),
    "white": (255, 255, 255),
    "gold": (255, 215, 0),
    "red": (255, 80, 80),
    "gray": (180, 180, 180),
    "green": (100, 220, 100),
    "dark_overlay": (0, 0, 0, 160),
    "platforms": [
        (102, 126, 234), (240, 147, 251), (79, 172, 254),
        (67, 233, 123), (250, 112, 154), (254, 225, 64),
        (168, 237, 234), (161, 141, 209),
    ],
}

# -- 全局状态 --
game_state = "playing"
score = 0
best_score = 0

# -- 物理常量 --
GRAVITY = 0.55
JUMP_BASE = 10
JUMP_MAX = 22
CHARGE_RATE = 0.6
MAX_CHARGE = 100
MIN_JUMP_CHARGE = 2
PLAYER_SIZE = 22
PLATFORM_W = 72
PLATFORM_H = 14

# -- 玩家 --
class Player:
    """玩家对象，rect 属性 + 运动状态"""
    def __init__(self):
        self.rect = pygame.Rect(0, 0, PLAYER_SIZE, PLAYER_SIZE)
        self.vx = 0
        self.vy = 0
        self.grounded = False
        self.rotation = 0

    # 以下属性委托给 self.rect，保持与 pygame.Rect 兼容
    @property
    def x(self): return self.rect.x
    @x.setter
    def x(self, v): self.rect.x = v

    @property
    def y(self): return self.rect.y
    @y.setter
    def y(self, v): self.rect.y = v

    @property
    def left(self): return self.rect.left
    @left.setter
    def left(self, v): self.rect.left = v

    @property
    def right(self): return self.rect.right
    @right.setter
    def right(self, v): self.rect.right = v

    @property
    def bottom(self): return self.rect.bottom
    @bottom.setter
    def bottom(self, v): self.rect.bottom = v

    @property
    def centerx(self): return self.rect.centerx

    @property
    def top(self): return self.rect.top

player = Player()

# -- 游戏对象 --
platforms = []
particles = []
camera_y = 0

# -- 鼠标蓄力 --
mouse_charging = False    # 是否按住鼠标蓄力
charge_power = 0           # 蓄力值 0-100（随时间增长）
charge_start_x = 0         # 按下鼠标时的 x 坐标
drag_dir = 0               # 拖拽方向：-1=左（跳向右）, 1=右（跳向左）, 0=无
drag_offset = 0            # 拖拽强度 0-100
preview_vx = 0.0           # 预览抛物线水平速度
preview_vy = 0.0           # 预览抛物线垂直速度

# -- 排行榜数据 (线程间共享) --
leaderboard_data = None
leaderboard_loaded = False
leaderboard_error = False


def reset_game():
    """重置所有游戏状态"""
    global game_state, score, platforms, particles, camera_y
    global mouse_charging, charge_power, leaderboard_data, leaderboard_loaded, leaderboard_error
    global drag_dir, drag_offset, charge_start_x, preview_vx, preview_vy

    game_state = "playing"
    score = 0
    platforms.clear()
    particles.clear()
    camera_y = 0
    mouse_charging = False
    charge_power = 0
    drag_dir = 0
    drag_offset = 0
    charge_start_x = 0
    preview_vx = 0.0
    preview_vy = 0.0
    leaderboard_data = None
    leaderboard_loaded = False
    leaderboard_error = False

    # 起始平台
    start_p = {
        "rect": pygame.Rect(
            SCREEN_WIDTH // 2 - 60,
            SCREEN_HEIGHT - 90,
            120,
            PLATFORM_H,
        ),
        "color": COLORS["platforms"][0],
        "scored": False,
    }
    platforms.append(start_p)

    # 玩家
    player.x = start_p["rect"].centerx - PLAYER_SIZE // 2
    player.y = start_p["rect"].top - PLAYER_SIZE
    player.vx = 0
    player.vy = 0
    player.grounded = True
    player.rotation = 0

    # 预生成平台
    _generate_platforms_up_to(-SCREEN_HEIGHT * 2)


def _generate_platforms_up_to(limit_y):
    """向上生成平台直到 limit_y"""
    while platforms[-1]["rect"].y > limit_y:
        last = platforms[-1]["rect"]
        gap = 60 + random.random() * 50
        new_y = last.y - gap
        w = PLATFORM_W - random.random() * 16
        x = random.random() * (SCREEN_WIDTH - w)
        color = random.choice(COLORS["platforms"])
        platforms.append({
            "rect": pygame.Rect(x, new_y, w, PLATFORM_H),
            "color": color,
            "scored": False,
        })


# ==================== [新增] 后台提交分数 + 拉取排行榜 ====================
def submit_and_fetch(final_score):
    """在后台线程中提交分数并拉取排行榜 (不阻塞游戏循环)"""
    global leaderboard_data, leaderboard_loaded, leaderboard_error
    try:
        requests.post(
            f"{FASTAPI_URL}/submit_score",
            json={"player_id": player_id, "score": final_score},
            timeout=5,
        )
        resp = requests.get(f"{FASTAPI_URL}/leaderboard", timeout=5)
        leaderboard_data = resp.json()
        leaderboard_loaded = True
        leaderboard_error = False
    except Exception:
        leaderboard_data = None
        leaderboard_loaded = True
        leaderboard_error = True
# ========================================================================


def draw_rounded_rect(surface, rect, color, radius=8):
    """绘制圆角矩形"""
    r = pygame.Rect(rect)
    pygame.draw.rect(surface, color, r, border_radius=radius)


def draw_text(text, font, color, x, y, center=True):
    """绘制文字，返回 rect"""
    surf = font.render(text, True, color)
    rect = surf.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    screen.blit(surf, rect)
    return rect


# -- 粒子 --
def spawn_particles(x, y, color, count=6):
    for _ in range(count):
        angle = random.random() * math.pi * 2
        speed = random.random() * 4 + 1
        particles.append({
            "x": x, "y": y,
            "vx": math.cos(angle) * speed,
            "vy": -math.sin(angle) * speed - 1,
            "life": 1.0,
            "decay": 0.02 + random.random() * 0.02,
            "color": color,
            "size": random.randint(2, 4),
        })


def update_particles():
    for p in particles[:]:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vy"] += 0.08
        p["life"] -= p["decay"]
        if p["life"] <= 0:
            particles.remove(p)


def draw_particles():
    for p in particles:
        alpha = int(max(0, p["life"]) * 255)
        c = (*p["color"], alpha)
        surf = pygame.Surface((p["size"] * 2, p["size"] * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, c, (p["size"], p["size"]), p["size"])
        screen.blit(surf, (p["x"] - p["size"], p["y"] - camera_y - p["size"]))


# ==================== [新增] 排行榜渲染 (pygame.font) ====================
def render_leaderboard():
    """在游戏结束画面上渲染排行榜，逐行显示第1名、第2名..."""
    title_surf = font_big.render("[ 排行榜 TOP 10 ]", True, COLORS["gold"])
    title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 10))
    screen.blit(title_surf, title_rect)

    if not leaderboard_loaded:
        # 加载中
        msg = font_small.render("加载中...", True, COLORS["gray"])
        msg_rect = msg.get_rect(center=(SCREEN_WIDTH // 2, title_rect.bottom + 30))
        screen.blit(msg, msg_rect)
        return

    if leaderboard_error or not leaderboard_data:
        # 加载失败 (第5条要求)
        msg = font_small.render("排行榜加载失败", True, COLORS["red"])
        msg_rect = msg.get_rect(center=(SCREEN_WIDTH // 2, title_rect.bottom + 30))
        screen.blit(msg, msg_rect)
        return

    # 逐行显示排行榜条目 (第3条要求)
    start_y = title_rect.bottom + 15
    line_h = 26

    for i, entry in enumerate(leaderboard_data[:10]):
        y = start_y + i * line_h

        rank_str = f"第{i+1}名"
        name_str = entry["username"]
        score_str = f"{entry['score']}分"

        is_me = entry["username"] == username
        text_color = COLORS["gold"] if is_me else COLORS["white"]

        # 排名 (前3名金色)
        rank_color = COLORS["gold"] if i < 3 else COLORS["gray"]
        rank_surf = font_small.render(rank_str, True, rank_color)
        rank_rect = rank_surf.get_rect(midright=(SCREEN_WIDTH // 2 - 60, y))
        screen.blit(rank_surf, rank_rect)

        # 用户名 (我的名字金色高亮)
        name_surf = font_small.render(name_str, True, text_color)
        name_rect = name_surf.get_rect(midleft=(SCREEN_WIDTH // 2 - 50, y))
        screen.blit(name_surf, name_rect)

        # 分数 (右对齐,金黄色)
        score_surf = font_small.render(score_str, True, COLORS["gold"])
        score_rect = score_surf.get_rect(midleft=(SCREEN_WIDTH // 2 + 50, y))
        screen.blit(score_surf, score_rect)

        # 我的名字后加星标
        if is_me:
            star_surf = font_small.render("*", True, COLORS["gold"])
            star_rect = star_surf.get_rect(midleft=(score_rect.right + 6, y))
            screen.blit(star_surf, star_rect)
# ========================================================================


# ==================== [新增] 游戏主要逻辑 ====================
def update_game():
    global game_state, score, best_score, camera_y, charge_power, mouse_charging
    global leaderboard_loaded, leaderboard_data

    if game_state == "gameover":
        return

    # -- 蓄力（按住鼠标时力量随时间增长） --
    if mouse_charging and player.grounded:
        charge_power = min(charge_power + CHARGE_RATE, MAX_CHARGE)
        # 实时更新抛物线预览
        _update_preview()

    # -- 物理 --
    player.vy += GRAVITY
    player.x += player.vx
    player.y += player.vy

    if not player.grounded:
        player.rotation += player.vx * 0.06

    # 水平边界
    if player.left < 0:
        player.left = 0
        player.vx *= -0.3
    if player.right > SCREEN_WIDTH:
        player.right = SCREEN_WIDTH
        player.vx *= -0.3

    # -- 碰撞检测 --
    player.grounded = False
    for p in platforms:
        rect = p["rect"]
        if (player.vy >= 0
                and rect.colliderect(player.rect)
                and player.bottom <= rect.top + player.vy + 12
                and player.bottom >= rect.top):
            player.bottom = rect.top
            player.vy = 0
            player.vx *= 0.85
            player.grounded = True

            # 计分
            if not p["scored"]:
                p["scored"] = True
                score += 1
                spawn_particles(player.centerx, player.bottom, (255, 215, 0), 6)
            break

    if player.grounded and abs(player.rotation) > 0.1:
        player.rotation *= 0.85
    elif player.grounded:
        player.rotation = 0

    # -- 相机跟随 --
    target_y = player.y - SCREEN_HEIGHT * 0.35
    if target_y < camera_y:
        camera_y += (target_y - camera_y) * 0.08
        # 生成新平台（修复：直接传目标坐标，避免死循环）
        if platforms[-1]["rect"].y > camera_y - 200:
            _generate_platforms_up_to(camera_y - 200)
        # 清理已离开视口的平台
        platforms[:] = [p for p in platforms if p["rect"].y < camera_y + SCREEN_HEIGHT + 100]

    # -- 粒子（限制总量防卡顿） --
    if len(particles) > 300:
        particles[:] = particles[-200:]
    update_particles()

    # -- 游戏结束检测 --
    if player.y > camera_y + SCREEN_HEIGHT + 60:
        game_state = "gameover"

        if score > best_score:
            best_score = score

        # 重置排行榜加载状态
        leaderboard_loaded = False
        leaderboard_data = None
        leaderboard_error = False

        # 后台提交分数 + 拉取排行榜
        threading.Thread(
            target=submit_and_fetch,
            args=(score,),
            daemon=True,
        ).start()


# ─── 抛物线预览（实时计算跳跃轨迹） ───
def _update_preview():
    """根据当前蓄力值和鼠标拖拽，计算预览抛物线"""
    global preview_vx, preview_vy
    jump_force = min(JUMP_BASE + charge_power * 0.12, JUMP_MAX)
    dir_strength = drag_dir * (drag_offset / 100) * 5
    preview_vy = -jump_force
    preview_vx = dir_strength


def draw_trajectory():
    """在画面上绘制抛物线预览轨迹"""
    px = player.x + PLAYER_SIZE // 2
    py = player.y - camera_y + PLAYER_SIZE // 2

    sim_x, sim_y = px, py
    sim_vx, sim_vy = preview_vx, preview_vy

    points = []
    for _ in range(50):
        points.append((sim_x, sim_y))
        sim_vy += GRAVITY
        sim_x += sim_vx
        sim_y += sim_vy
        if sim_y > SCREEN_HEIGHT + 100:
            break

    # 画轨迹点
    for i, (x, y) in enumerate(points):
        if y < 0 or y > SCREEN_HEIGHT:
            continue
        alpha = 1.0 - (i / len(points)) * 0.6
        size = max(3 - (i / len(points)) * 2, 1.5)
        c = (79, 172, 254) if drag_dir == 1 else (240, 147, 251) if drag_dir == -1 else (200, 200, 255)
        s = pygame.Surface((int(size * 3), int(size * 3)), pygame.SRCALPHA)
        pygame.draw.circle(s, (*c, int(alpha * 180)), (int(size * 1.5), int(size * 1.5)), int(size))
        screen.blit(s, (int(x - size * 1.5), int(y - size * 1.5)))

    # 落点标记
    if len(points) > 3:
        end = points[-1]
        pygame.draw.circle(screen, (255, 215, 0), (int(end[0]), int(end[1])), 5)
        pygame.draw.circle(screen, (255, 255, 255), (int(end[0]), int(end[1])), 3)


def draw_game():
    # -- 背景渐变 --
    for y in range(SCREEN_HEIGHT):
        t = y / SCREEN_HEIGHT
        r = int(COLORS["bg_top"][0] * (1 - t) + COLORS["bg_bot"][0] * t)
        g = int(COLORS["bg_top"][1] * (1 - t) + COLORS["bg_bot"][1] * t)
        b = int(COLORS["bg_top"][2] * (1 - t) + COLORS["bg_bot"][2] * t)
        pygame.draw.line(screen, (r, g, b), (0, y), (SCREEN_WIDTH, y))

    # -- 背景星星 --
    seed = 7919
    for i in range(40):
        sx = (i * seed * 13) % SCREEN_WIDTH
        sy_base = (i * seed * 17) % (SCREEN_HEIGHT * 3)
        sy = (sy_base + pygame.time.get_ticks() * 0.003 * (i % 3 + 1)) % (SCREEN_HEIGHT * 2)
        sy -= camera_y * 0.05
        if 0 <= sy <= SCREEN_HEIGHT:
            alpha = 80 + (i % 5) * 30
            pygame.draw.circle(screen, (255, 255, 255, alpha), (int(sx), int(sy)), 1 + (i % 2))

    # -- 粒子 --
    draw_particles()

    # -- 平台 --
    for p in platforms:
        rect = pygame.Rect(p["rect"])
        rect.y -= camera_y
        if rect.bottom < 0 or rect.top > SCREEN_HEIGHT:
            continue
        draw_rounded_rect(screen, rect, p["color"], 6)
        # 高光
        highlight = pygame.Rect(rect.x + 4, rect.y + 2, rect.w - 8, 4)
        pygame.draw.rect(screen, (255, 255, 255, 50), highlight, border_radius=2)

    # -- 玩家 --
    px = player.x + PLAYER_SIZE // 2
    py = player.y + PLAYER_SIZE // 2 - camera_y

    # 阴影
    pygame.draw.circle(screen, (0, 0, 0, 40),
                       (int(px + 2), int(py + 3)),
                       PLAYER_SIZE // 2)

    # 身体 (带旋转)
    surf = pygame.Surface((PLAYER_SIZE, PLAYER_SIZE), pygame.SRCALPHA)
    center = (PLAYER_SIZE // 2, PLAYER_SIZE // 2)
    pygame.draw.circle(surf, (255, 255, 255), center, PLAYER_SIZE // 2)
    # 眼睛
    pygame.draw.circle(surf, (50, 50, 50), (center[0] - 4, center[1] - 3), 2.5)
    pygame.draw.circle(surf, (50, 50, 50), (center[0] + 4, center[1] - 3), 2.5)
    # 腮红
    pygame.draw.circle(surf, (255, 150, 150, 80), (center[0] - 7, center[1] + 2), 3)
    pygame.draw.circle(surf, (255, 150, 150, 80), (center[0] + 7, center[1] + 2), 3)

    rotated = pygame.transform.rotate(surf, player.rotation)
    rot_rect = rotated.get_rect(center=(px, py))
    screen.blit(rotated, rot_rect)

    # -- 力度条（鼠标蓄力时） --
    if mouse_charging:
        bar_w = 160
        bar_h = 14
        bar_x = (SCREEN_WIDTH - bar_w) // 2
        bar_y = SCREEN_HEIGHT - 50

        # 背景
        pygame.draw.rect(screen, (40, 40, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=7)

        # 填充
        fill_w = int(bar_w * (charge_power / MAX_CHARGE))
        if fill_w > 0:
            ratio = charge_power / MAX_CHARGE
            if ratio < 0.5:
                t2 = ratio * 2
                c = (74 + int(132 * t2), 222 - int(42 * t2), 128 - int(113 * t2))
            else:
                t2 = (ratio - 0.5) * 2
                c = (int(250 + 5 * t2), int(180 - 130 * t2), int(15 - 15 * t2))
            pygame.draw.rect(screen, c, (bar_x, bar_y, fill_w, bar_h), border_radius=7)

        # 边框
        pygame.draw.rect(screen, (100, 100, 140), (bar_x, bar_y, bar_w, bar_h), width=2, border_radius=7)

        # 力度数字
        draw_text(f"力度: {int(charge_power)}", font_small, COLORS["white"],
                  SCREEN_WIDTH // 2, bar_y - 20)

    # -- 得分 --
    draw_text(f"得分: {score}", font_mid, COLORS["white"], 70, 30)
    draw_text(f"最高: {best_score}", font_mid, COLORS["white"], SCREEN_WIDTH - 70, 30)

    # -- 抛物线预览（蓄力时显示） --
    if mouse_charging:
        draw_trajectory()

    # -- 提示 --
    if player.grounded and not mouse_charging:
        hint_alpha = 128 + int(80 * math.sin(pygame.time.get_ticks() * 0.004))
        draw_text("按住鼠标蓄力，滑动改变抛物线方向", font_small,
                  (255, 255, 255, hint_alpha), SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)

    # -- [修改] 游戏结束画面 (含排行榜) --
    if game_state == "gameover":
        # 半透明遮罩
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        # 游戏结束文字
        draw_text("游戏结束", font_title, COLORS["white"], SCREEN_WIDTH // 2, 70)
        draw_text(f"本局得分: {score}", font_big, COLORS["gold"], SCREEN_WIDTH // 2, 120)
        draw_text(f"历史最高: {best_score}", font_mid, COLORS["gray"], SCREEN_WIDTH // 2, 160)

        # [新增] 渲染排行榜 (pygame.font 逐行显示)
        render_leaderboard()

        # 操作提示
        draw_text("按 SPACE 再来一局 | 按 ESC 退出", font_small, COLORS["gray"],
                  SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40)


def handle_events():
    global mouse_charging, charge_power, charge_start_x, drag_dir, drag_offset, game_state
    global preview_vx, preview_vy

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_SPACE and game_state == "gameover":
                reset_game()

        # ── 鼠标按下：开始蓄力 ──
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if game_state == "playing" and player.grounded:
                mouse_charging = True
                charge_power = 0
                charge_start_x = event.pos[0]
                drag_dir = 0
                drag_offset = 0
                _update_preview()

        # ── 鼠标移动：控制抛物线方向（拖拽反向） ──
        if event.type == pygame.MOUSEMOTION and mouse_charging:
            current_x = event.pos[0]
            delta_x = current_x - charge_start_x
            max_drag = 80
            drag_offset = min(abs(delta_x) / max_drag, 1) * 100
            if delta_x < -10:
                drag_dir = 1       # 往左拖 → 往右跳
            elif delta_x > 10:
                drag_dir = -1      # 往右拖 → 往左跳
            else:
                drag_dir = 0
            _update_preview()

        # ── 鼠标松开：跳跃 ──
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and mouse_charging:
            mouse_charging = False
            if charge_power >= MIN_JUMP_CHARGE and player.grounded:
                player.vy = preview_vy
                player.vx = preview_vx
                player.grounded = False
                spawn_particles(player.centerx, player.bottom, (180, 200, 255), 5)
            charge_power = 0
            drag_dir = 0
            drag_offset = 0

    return True


# ==================== [新增] 主循环 ====================
def main():
    global game_state

    reset_game()

    running = True
    while running:
        running = handle_events()
        update_game()
        draw_game()
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
