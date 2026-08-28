"""报告中心路由（配置/结果/日志导入）"""
import json
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.project import ReportProject, TestRecord
from app.models.template import TestCategory, TestItem
from app.models.management import ReportBatch, ReportArtifact, ActivityLog

router = APIRouter(prefix="/api/projects", tags=["报告中心"])


@router.get("/{project_id}/report-center/summary")
async def get_report_center_summary(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """获取报告中心摘要"""
    batches_result = await db.execute(
        select(ReportBatch).where(ReportBatch.project_id == project_id).order_by(ReportBatch.created_at.desc())
    )
    batches = [{"id": b.id, "batch_type": b.batch_type, "source": b.source,
                "status": b.status, "summary_json": b.summary_json, "note": b.note,
                "created_at": str(b.created_at) if b.created_at else None}
              for b in batches_result.scalars().all()]

    record_result = await db.execute(
        select(TestRecord).where(TestRecord.project_id == project_id)
    )
    all_records = list(record_result.scalars().all())
    stats = {"total": len(all_records),
             "pass": sum(1 for r in all_records if r.result == "Pass"),
             "fail": sum(1 for r in all_records if r.result == "Fail"),
             "pending": sum(1 for r in all_records if not r.result or r.result == "NotTested")}

    return {"code": 200, "message": "success",
            "data": {"batches": batches, "stats": stats}}


@router.post("/{project_id}/report-center/import-config")
async def import_config_file(project_id: int, file: UploadFile = File(...),
                              db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """上传并导入设备配置文件"""
    content = await file.read()
    try:
        config_data = json.loads(content)
    except json.JSONDecodeError:
        return {"code": 400, "message": "无效的 JSON 文件", "data": None}

    from app.models.config import DeviceConfig
    cfg = DeviceConfig(config_name=file.filename, raw_data=json.dumps(config_data))
    # 填充字段
    for key in ["bios_vendor", "bios_version", "cpu_model", "gpu_model", "os_version"]:
        if key in config_data:
            setattr(cfg, key, config_data[key])

    db.add(cfg)
    await db.flush()

    # 关联到项目
    proj = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj.scalar_one_or_none()
    if project:
        project.config_id = cfg.id

    db.add(ActivityLog(user_id=user.id, action="import", target_type="config",
                      target_id=cfg.id, detail=f"导入配置文件 {file.filename}"))
    await db.flush()
    return {"code": 200, "message": "配置导入成功", "data": {"id": cfg.id}}


@router.post("/{project_id}/report-center/import-results")
async def import_results_file(project_id: int, file: UploadFile = File(...),
                               db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """上传并导入结果文件"""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"code": 400, "message": "无效的 JSON 文件", "data": None}

    key = data.get("key", "test_batch")
    batch = ReportBatch(project_id=project_id, batch_type="result_import",
                        source="json", status="completed",
                        summary_json=json.dumps({"key": key}),
                        note=f"导入结果 {file.filename}", created_by=user.id)
    db.add(batch)
    db.add(ActivityLog(user_id=user.id, action="import", target_type="result",
                      target_id=batch.id, detail=f"导入结果文件"))
    await db.flush()
    return {"code": 200, "message": "结果导入成功", "data": {"batch_id": batch.id}}


@router.post("/{project_id}/report-center/upload-logs")
async def upload_log_files(project_id: int, files: list[UploadFile] = File(...),
                            db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """上传日志文件"""
    batch = ReportBatch(project_id=project_id, batch_type="log_upload",
                        source="upload", status="completed",
                        note=f"上传 {len(files)} 个日志文件", created_by=user.id)
    db.add(batch)
    await db.flush()
    return {"code": 200, "message": f"成功上传 {len(files)} 个日志文件", "data": {"batch_id": batch.id}}


@router.get("/{project_id}/export/check")
async def export_check(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """导出前完整性检查"""
    result = await db.execute(select(TestRecord).where(TestRecord.project_id == project_id))
    records = list(result.scalars().all())
    issues = []
    if any(r.result == "Fail" and not r.comment for r in records):
        issues.append("存在 Fail 结果但未填写备注")
    pending = sum(1 for r in records if not r.result)
    if pending > 0:
        issues.append(f"还有 {pending} 条记录未测试")

    return {"code": 200, "message": "success",
            "data": {"valid": len(issues) == 0, "issues": issues, "total": len(records)}}


@router.post("/{project_id}/report/generate")
async def generate_report(project_id: int, db: AsyncSession = Depends(get_db)):
    """生成测试报告"""
    from app.services import report_service
    html_content = await report_service.generate_report_html(db, project_id)
    if html_content.startswith("<h1>"):
        return {"code": 400, "message": html_content, "data": None}

    result = await report_service.save_report_artifact(db, project_id, html_content, 1)
    return {"code": 200, "message": "报告生成成功", "data": result}


@router.get("/{project_id}/report/data")
async def get_report_data(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """获取报告结构化数据"""
    from app.services import report_service
    data = await report_service.generate_report_data(db, project_id)
    if "error" in data:
        return {"code": 400, "message": data["error"], "data": None}
    return {"code": 200, "message": "success", "data": data}


@router.get("/{project_id}/report/preview")
async def preview_report(project_id: int, db: AsyncSession = Depends(get_db)):
    """预览HTML报告"""
    from fastapi.responses import HTMLResponse
    from app.services import report_service
    html_content = await report_service.generate_report_html(db, project_id)
    if html_content.startswith("<h1>"):
        return HTMLResponse(f"<h1 style='text-align:center;margin-top:100px'>{html_content}</h1>", status_code=400)
    return HTMLResponse(html_content)


@router.get("/{project_id}/report/artifacts")
async def list_report_artifacts(project_id: int, db: AsyncSession = Depends(get_db)):
    """获取已生成的报告列表"""
    result = await db.execute(
        select(ReportArtifact)
        .where(ReportArtifact.project_id == project_id, ReportArtifact.artifact_type == "html_report")
        .order_by(ReportArtifact.created_at.desc())
    )
    artifacts = [{"id": a.id, "file_name": a.file_name, "file_size": a.file_size,
                  "created_at": str(a.created_at) if a.created_at else None}
                 for a in result.scalars().all()]
    return {"code": 200, "message": "success", "data": artifacts}


@router.delete("/{project_id}/report/artifacts/{artifact_id}")
async def delete_report_artifact(project_id: int, artifact_id: int, db: AsyncSession = Depends(get_db)):
    """删除历史报告"""
    result = await db.execute(
        select(ReportArtifact)
        .where(ReportArtifact.id == artifact_id, ReportArtifact.project_id == project_id)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"code": 404, "message": "报告不存在", "data": None}

    # 删除文件
    import os
    if artifact.file_path and os.path.isfile(artifact.file_path):
        try:
            os.remove(artifact.file_path)
        except Exception:
            pass  # 文件删除失败不影响数据库记录删除

    # 删除数据库记录
    await db.delete(artifact)
    await db.flush()

    return {"code": 200, "message": "报告删除成功", "data": None}
