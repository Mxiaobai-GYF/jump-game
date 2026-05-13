# -*- coding: utf-8 -*-
"""
游戏后端服务器 — FastAPI + FakeSupabase
========================================
修改说明:
  * [修改] signup 接口: 密码存入已由 database.py 自动哈希，不再明文
  * [修改] login 接口: 密码比对已由 database.py 自动哈希，不再明文
  * [修复] 删除了重复的 /login endpoint
  * [修复] 修复了 /leaderboard 中装饰器嵌套在函数内的 bug
  * [新增] /leaderboard 使用 JOIN 查询返回用户名+分数
  * [新增] CORS 中间件（允许来自 file:// 和任何域名的跨域请求）
========================================
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import supabase
from models import SignupRequest, LoginRequest, SubmitScoreRequest

app = FastAPI(title="Game Server", version="1.0.0")

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ────────────────────────────── 注册 ──────────────────────────────

@app.post("/signup")
def signup(body: SignupRequest):
    """注册新用户（密码由 database.py 自动 sha256 加密后存入）"""
    # 先检查用户名是否已存在
    existing = (
        supabase.table("players")
        .select("id")
        .eq("username", body.username)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="用户名已存在")

    # 插入新用户（密码哈希在 FakeQuery.insert 中自动处理）
    result = (
        supabase.table("players")
        .insert({"username": body.username, "password": body.password})
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="注册失败")

    new_user = result.data[0]
    return {
        "status": "ok",
        "player_id": new_user["id"],
        "username": new_user["username"],
    }


# ────────────────────────────── 登录 ──────────────────────────────

@app.post("/login")
def login(body: LoginRequest):
    """验证用户名和密码（密码比对由 database.py 自动哈希处理）"""
    result = (
        supabase.table("players")
        .select("id")
        .eq("username", body.username)
        .eq("password", body.password)
        .execute()
    )

    if not result.data:
        return {"status": "error"}

    return {"status": "ok", "player_id": result.data[0]["id"]}


# ────────────────────────────── 提交分数 ──────────────────────────

@app.post("/submit_score")
def submit_score(body: SubmitScoreRequest):
    """记录玩家分数到 scores 表"""
    result = (
        supabase.table("scores")
        .insert({"player_id": body.player_id, "score": body.score})
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="提交分数失败")

    return {"status": "ok"}


# ────────────────────────────── 排行榜 ────────────────────────────

@app.get("/leaderboard")
def leaderboard():
    """返回分数最高的前 10 名玩家（含用户名），按分数降序"""
    result = (
        supabase.table("scores")
        .select("score, players!inner(username)")
        .order("score", desc=True)
        .limit(10)
        .execute()
    )

    rows = []
    for item in result.data:
        rows.append({
            "username": item["players"]["username"],
            "score": item["score"],
        })

    return rows


# ── 静态文件 ──
import os
from fastapi.responses import FileResponse


@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


@app.get("/game.html")
async def serve_game():
    return FileResponse("static/game.html")
