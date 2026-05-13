"""Supabase 配置 — 从 .env 文件加载 URL 和 Key"""

import os
from dotenv import load_dotenv

load_dotenv()  # 读取 .env 文件

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "请在 .env 文件中设置 SUPABASE_URL 和 SUPABASE_KEY"
    )
