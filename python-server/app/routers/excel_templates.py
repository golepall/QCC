"""Excel模板文件管理API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services import excel_template_service

router = APIRouter(prefix="/api/excel-templates", tags=["Excel模板"])


@router.get("")
async def list_excel_templates():
    """获取所有xlsx模板文件列表"""
    try:
        files = excel_template_service.list_excel_files()
        return {"code": 200, "message": "success", "data": files}
    except FileNotFoundError as e:
        return {"code": 404, "message": str(e), "data": []}
    except PermissionError as e:
        return {"code": 403, "message": str(e), "data": []}


@router.get("/permissions")
async def check_permissions():
    """检查模板目录权限"""
    result = excel_template_service.check_permissions()
    return {"code": 200, "message": "success", "data": result}


@router.get("/{filename}/preview")
async def preview_excel(filename: str, max_rows: int = 50):
    """预览Excel文件内容"""
    try:
        data = excel_template_service.read_excel_preview(filename, max_rows=max_rows)
        return {"code": 200, "message": "success", "data": data}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {str(e)}")


class WriteRequest(BaseModel):
    sheet_name: str
    data: list[dict]
    start_row: int = 2


@router.post("/{filename}/write")
async def write_to_excel(filename: str, body: WriteRequest):
    """将业务数据写入Excel模板"""
    try:
        result = excel_template_service.write_data_to_template(
            filename, body.sheet_name, body.data, start_row=body.start_row
        )
        return {"code": 200, "message": "数据写入成功", "data": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {str(e)}")
