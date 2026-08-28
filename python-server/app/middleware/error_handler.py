"""全局异常处理 + 统一错误响应格式"""
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.common import error


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局未捕获异常处理器"""
    return JSONResponse(
        status_code=500,
        content=error(code=500, message=str(exc) or "服务器内部错误"),
    )


class AppException(Exception):
    """业务异常，自动映射为对应的 HTTP 响应"""

    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """业务异常处理器"""
    return JSONResponse(
        status_code=exc.code if exc.code >= 400 else 400,
        content=error(code=exc.code, message=exc.message),
    )
