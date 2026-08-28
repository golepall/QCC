"""Excel 报告导出路由"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.project import ReportProject
from app.models.template import ReportTemplate

router = APIRouter(prefix="/api/projects", tags=["报表导出"])


@router.get("/{project_id}/export")
async def export_report(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """生成并下载 Excel 测试报告"""
    result = await db.execute(
        select(ReportProject).where(ReportProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        return {"code": 404, "message": "项目不存在", "data": None}

    tpl = await db.execute(select(ReportTemplate).where(ReportTemplate.id == project.template_id))
    template = tpl.scalar_one_or_none()

    # 生成 Excel 报告
    from app.services.export_service import generate_report
    file_path = await generate_report(db, project, template)

    filename = f"{template.doc_code}_{project.product_model}_测试报告.xlsx" if template else f"{project.project_code}_测试报告.xlsx"
    return FileResponse(file_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
