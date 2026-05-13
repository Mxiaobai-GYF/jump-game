"""Pydantic 请求 / 响应模型"""

from pydantic import BaseModel


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SubmitScoreRequest(BaseModel):
    player_id: str
    score: int
