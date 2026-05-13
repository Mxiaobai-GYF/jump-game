# -*- coding: utf-8 -*-
"""
FakeSupabase — 模拟 Supabase 客户端，带 sha256 密码加密和 JSON 文件持久化
===================================================================
修改说明:
  * [新增] hashlib 导入，自动对 password 字段做 sha256 哈希
  * [新增] JSON 文件持久化（数据存在 fakedb.json，服务器重启不丢失）
  * [新增] 完整的查询链：select → eq → order → limit → execute
  * [新增] 支持 JOIN 查询（leaderboard 用）
  * [新增] 自动生成 uuid 作为 player id
===================================================================
"""

import hashlib
import json
import os
import uuid
import time
from types import SimpleNamespace


DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fakedb.json")


def _hash_password(password: str) -> str:
    """对密码做 sha256 并返回十六进制字符串"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class FakeQuery:
    """构建中的查询对象，支持 select / eq / order / limit / execute"""

    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._filters = []       # [("eq", col, val), ...]
        self._order_col = None
        self._order_desc = False
        self._limit_val = None
        self._select_raw = "*"   # "score, players!inner(username)" 或 "*"
        self._join_info = None   # 解析后的 JOIN 信息
        self._last_insert_data = None

    def select(self, cols="*"):
        self._select_raw = cols
        # 解析 JOIN 语法: "score, players!inner(username)"
        if "!" in cols:
            parts = cols.split(",")
            join_part = None
            for p in parts:
                p = p.strip()
                if "!" in p:
                    join_part = p
            if join_part:
                # "players!inner(username)" -> ("players", "username")
                tbl_part, _, col_part = join_part.partition("!")
                # col_part: "inner(username)"
                inner_part = col_part.strip()
                if inner_part.startswith("inner(") and inner_part.endswith(")"):
                    self._join_info = {
                        "table": tbl_part.strip(),
                        "column": inner_part[6:-1].strip(),
                    }
        return self

    def eq(self, col, val):
        # 如果是 password 字段，自动哈希后再比较
        if col == "password":
            val = _hash_password(val)
        self._filters.append(("eq", col, val))
        return self

    def insert(self, data):
        data = dict(data)  # 复制一份
        if self._table_name == "players":
            # [新增] 自动哈希密码
            if "password" in data:
                data["password"] = _hash_password(data["password"])
            data["id"] = str(uuid.uuid4())
            data["created_at"] = time.time()
            self._db._tables["players"][data["username"]] = data
            self._last_insert_data = [dict(data)]

        elif self._table_name == "scores":
            player_id = data.get("player_id", "")
            new_score = data.get("score", 0)

            # 查找该玩家是否已有记录
            existing_idx = None
            for i, s in enumerate(self._db._tables["scores"]):
                if s["player_id"] == player_id:
                    existing_idx = i
                    break

            if existing_idx is not None:
                existing = self._db._tables["scores"][existing_idx]
                if new_score > existing["score"]:
                    # 新分数更高，更新
                    existing["score"] = new_score
                    existing["created_at"] = time.time()
                    self._last_insert_data = [dict(existing)]
                else:
                    # 新分数不高于已有最高分，不更新
                    self._last_insert_data = [dict(existing)]
            else:
                # 该玩家首次提交分数
                new_entry = {
                    "id": len(self._db._tables["scores"]) + 1,
                    "player_id": player_id,
                    "score": new_score,
                    "created_at": time.time(),
                }
                self._db._tables["scores"].append(new_entry)
                self._last_insert_data = [dict(new_entry)]

        self._db._save()  # 持久化
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def execute(self):
        """执行查询，返回 SimpleNamespace(data=...)"""
        if self._last_insert_data is not None:
            return SimpleNamespace(data=self._last_insert_data)

        # --- SELECT 查询 ---
        if self._table_name == "players":
            records = list(self._db._tables["players"].values())
        elif self._table_name == "scores":
            records = list(self._db._tables["scores"])
        else:
            records = []

        # 应用 eq 过滤器
        for op, col, val in self._filters:
            if op == "eq":
                records = [r for r in records if r.get(col) == val]

        # 处理 JOIN: scores 表 JOIN players 表
        if self._join_info:
            joined = []
            jtbl = self._join_info["table"]     # "players"
            jcol = self._join_info["column"]    # "username"
            for rec in records:
                pid = rec.get("player_id")
                # 在 players 表中找匹配
                player_rec = None
                for p in self._db._tables["players"].values():
                    if p["id"] == pid:
                        player_rec = p
                        break
                if player_rec:
                    joined.append({
                        "score": rec["score"],
                        jtbl: {jcol: player_rec[jcol]},
                    })
            records = joined

        # 排序
        if self._order_col:
            reverse = self._order_desc
            records.sort(key=lambda r: r.get(self._order_col, 0), reverse=reverse)

        # limit
        if self._limit_val is not None and self._limit_val > 0:
            records = records[: self._limit_val]

        return SimpleNamespace(data=records)


class FakeSupabase:
    """模拟 Supabase 客户端"""

    def __init__(self):
        self._tables = {"players": {}, "scores": []}
        self._load()

    def _load(self):
        """从 JSON 文件恢复数据"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self._tables = json.load(f)
            except Exception:
                self._tables = {"players": {}, "scores": []}
            # 确保 scores 里的 id 是整数
            for s in self._tables.get("scores", []):
                if isinstance(s.get("id"), str):
                    s["id"] = int(s["id"])

    def _save(self):
        """保存数据到 JSON 文件（持久化）"""
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._tables, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 写文件失败不崩服务器

    def table(self, name):
        return FakeQuery(self, name)


# 单例，供 main.py 导入
supabase = FakeSupabase()
