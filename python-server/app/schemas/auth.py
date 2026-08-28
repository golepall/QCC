"""认证相关 Pydantic Schema"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=20)
    display_name: str = Field("", max_length=100)
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    """认证响应"""
    token: str
    user: dict


class UserInfo(BaseModel):
    """用户信息"""
    id: int
    username: str
    display_name: str
    role: str
    created_at: str | None = None

    class Config:
        from_attributes = True
