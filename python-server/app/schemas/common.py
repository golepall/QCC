"""统一响应格式（评审建议十）"""
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应格式

    code=0 表示成功，非 0 表示错误
    """
    code: int = 0
    message: str = ""
    data: T | None = None


class PaginatedData(BaseModel, Generic[T]):
    """分页数据结构"""
    list: list[T]
    total: int
    page: int
    page_size: int


def success(data: Any = None, message: str = "ok") -> dict:
    """成功响应"""
    return {"code": 0, "message": message, "data": data}


def error(code: int = 1, message: str = "error", data: Any = None) -> dict:
    """错误响应"""
    return {"code": code, "message": message, "data": data}
