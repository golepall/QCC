"""离线测试包管理路由（导出/导入 ZIP）"""
import os, json, zipfile, io
from datetime import date
from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.middleware.auth import get_current_user
from app.models.project import ReportProject, TestRecord
from app.models.template import TestCategory, TestItem, ReportTemplate
from app.models.config import DeviceConfig
from app.models.management import ReportBatch, ReportArtifact, ActivityLog

router = APIRouter(prefix="/api/projects", tags=["离线测试"])

SCRIPT_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_engine", "script_registry.json")
LEGACY_TEST_CASE_TO_SCRIPT_ID = {
    "bios_version_check": "collector.bios.info",
    "cpu_info_check": "collector.cpu.info",
    "memory_check": "collector.memory.info",
    "disk_check": "collector.disk.info",
    "gpu_check": "collector.gpu.info",
    "network_lan_check": "collector.lan.info",
    "network_wlan_check": "collector.wlan.info",
    "audio_check": "collector.audio.info",
    "usb_check": "collector.usb.info",
    "device_manager_check": "collector.device_manager.info",
}
CATEGORY_CODE_TO_SCRIPT_ID = {
    "bios_info": "collector.bios.info", "bios_check": "collector.bios.info",
    "cpu_info": "collector.cpu.info", "cpu": "collector.cpu.info",
    "memory_info": "collector.memory.info", "memory": "collector.memory.info",
    "disk_info": "collector.disk.info", "hdd_ssd": "collector.disk.info",
    "gpu_info": "collector.gpu.info", "vga": "collector.gpu.info",
    "network_lan": "collector.lan.info", "lan": "collector.lan.info",
    "network_wlan": "collector.wlan.info", "wlan": "collector.wlan.info",
    "audio": "collector.audio.info",
    "usb": "collector.usb.info",
    "basic_function": "collector.device_manager.info",
}


@router.get("/{project_id}/export-agent")
async def export_agent_package(project_id: int, package_type: str = "full",
                                db: AsyncSession = Depends(get_db)):
    """导出离线测试包 ZIP

    Args:
        package_type: 导出类型
            - "data": 仅数据包（需配合已安装的Agent使用）
            - "full": 完整包（包含Agent脚本，推荐）
    """
    result = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return {"code": 404, "message": "项目不存在", "data": None}

    tpl = await db.execute(select(ReportTemplate).where(ReportTemplate.id == project.template_id))
    template = tpl.scalar_one_or_none()

    # 生成测试计划
    cat_result = await db.execute(
        select(TestCategory).where(TestCategory.template_id == project.template_id).order_by(TestCategory.sort_order)
    )
    test_plan = []
    script_mapping = []
    for cat in cat_result.scalars().all():
        items = await db.execute(
            select(TestItem).where(TestItem.category_id == cat.id).order_by(TestItem.sort_order)
        )
        for item in items.scalars().all():
            entry = {"id": item.id, "item_no": item.item_no, "test_item": item.test_item,
                     "category": cat.category_name, "is_header": item.is_header}
            test_plan.append(entry)

            if not item.is_header and item.test_case:
                sid = LEGACY_TEST_CASE_TO_SCRIPT_ID.get(item.test_case)
                if not sid:
                    sid = CATEGORY_CODE_TO_SCRIPT_ID.get(cat.category_code)
                script_mapping.append({"item_id": item.id, "item_no": item.item_no,
                                       "test_case": item.test_case, "script_id": sid,
                                       "category": cat.category_code, "mode": "auto" if sid else "manual"})

    manifest = {
        "project_id": project_id, "project_code": project.project_code,
        "product_model": project.product_model, "product_name": project.product_name,
        "template_id": project.template_id, "generated_at": str(date.today()),
        "package_type": package_type,
        "agent_version": "1.1.0"
    }

    config_data = {}
    if project.config_id:
        cfg = await db.execute(select(DeviceConfig).where(DeviceConfig.id == project.config_id))
        dev_cfg = cfg.scalar_one_or_none()
        if dev_cfg:
            config_data = {c.name: getattr(dev_cfg, c.name) for c in dev_cfg.__table__.columns
                          if not c.name.startswith("_")}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # 数据文件 - 放到 TestData 目录（Agent 期望的结构）
        z.writestr(f"{project.project_code}/TestData/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr(f"{project.project_code}/TestData/config.json", json.dumps(config_data, ensure_ascii=False, indent=2))
        z.writestr(f"{project.project_code}/TestData/test_plan.json", json.dumps(test_plan, ensure_ascii=False, indent=2))
        z.writestr(f"{project.project_code}/TestData/script_mapping.json", json.dumps(script_mapping, ensure_ascii=False, indent=2))
        z.writestr(f"{project.project_code}/TestData/result_template.json", json.dumps([], ensure_ascii=False))

        # 完整包：包含Agent脚本和运行说明
        if package_type == "full":
            agent_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_engine")
            agent_dir = os.path.normpath(agent_dir)
            if os.path.exists(agent_dir):
                _add_agent_to_zip(z, agent_dir, project.project_code)

            # 添加启动说明
            readme_content = _generate_readme(project.project_code)
            z.writestr(f"{project.project_code}/README.txt", readme_content)

            # 添加 Windows 启动脚本（纯英文，避免编码问题）
            start_bat = _generate_start_bat(project.project_code)
            z.writestr(f"{project.project_code}/start.bat", start_bat)

    buf.seek(0)
    filename = f"QCC_Agent_{project.project_code}_{'complete' if package_type == 'full' else 'data'}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                            headers={"Content-Disposition": f"attachment; filename={filename}"})


def _add_agent_to_zip(z: zipfile.ZipFile, agent_dir: str, project_code: str):
    """将 Agent 添加到 ZIP（优先使用 EXE 版本）"""
    # 优先检查是否有打包好的 EXE 版本
    exe_dir = os.path.join(agent_dir, "QCC_Test_Agent_Portable", "Agent")
    if os.path.exists(exe_dir) and os.path.exists(os.path.join(exe_dir, "QCC_Test_Agent.exe")):
        # 添加 EXE 及所有依赖
        for root, dirs, files in os.walk(exe_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, exe_dir)
                z.write(file_path, f"{project_code}/Agent/{arc_name}")
        return

    # 如果没有 EXE，回退到脚本版本
    agent_file = os.path.join(agent_dir, "agent", "agent_runner.py")
    if os.path.exists(agent_file):
        z.write(agent_file, f"{project_code}/agent/agent_runner.py")

    # 添加 core 模块
    core_dir = os.path.join(agent_dir, "core")
    if os.path.exists(core_dir):
        for root, dirs, files in os.walk(core_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, agent_dir)
                    z.write(file_path, f"{project_code}/{arc_name}")

    # 添加脚本注册表
    registry_file = os.path.join(agent_dir, "script_registry.json")
    if os.path.exists(registry_file):
        z.write(registry_file, f"{project_code}/script_registry.json")

    # 添加采集脚本
    scripts_dir = os.path.join(agent_dir, "scripts")
    if os.path.exists(scripts_dir):
        for root, dirs, files in os.walk(scripts_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, agent_dir)
                    z.write(file_path, f"{project_code}/{arc_name}")


def _generate_readme(project_code: str) -> str:
    """生成启动说明（适配 EXE 版本）"""
    # 检查是否有 EXE
    exe_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_engine", "QCC_Test_Agent_Portable", "Agent", "QCC_Test_Agent.exe")
    has_exe = os.path.exists(exe_path)

    if has_exe:
        return f"""QCC 离线测试 Agent - 使用说明
================================

项目编号: {project_code}
版本: 1.1.0

一、环境要求
------------
- Windows 10/11 (64位)
- 无需安装 Python
- 无需联网

二、启动方式
------------
双击 "启动测试.bat" 文件即可启动

三、测试流程
------------
1. 启动 Agent 后，系统会自动采集当前设备信息
2. 查看左侧测试项列表，逐项执行测试
3. 填写测试结果（Pass/Fail/NA/Blocked）
4. 完成后点击 "导出结果包"
5. 将生成的 result.zip 上传到 QCC 平台

四、常见问题
------------
Q: Agent 无法启动
A: 检查是否被 Windows Defender 拦截，点击"更多信息"->"仍要运行"

Q: 提示缺少 VCRUNTIME140.dll
A: 下载安装 Visual C++ Redistributable

Q: S3/S4/重启测试提示权限不足
A: 右键 "启动测试.bat" -> 以管理员身份运行

五、文件说明
------------
Agent/              - 测试 Agent 程序（EXE）
manifest.json       - 项目信息
config.json         - 设备配置
test_plan.json      - 测试计划
script_mapping.json - 脚本映射
启动测试.bat        - 启动脚本
"""
    else:
        return f"""QCC 离线测试 Agent - 使用说明
================================

项目编号: {project_code}
版本: 1.1.0

一、环境要求
------------
1. Python 3.11 或更高版本
2. 安装依赖: pip install psutil

二、启动方式
------------
双击 "启动测试.bat" 文件

三、测试流程
------------
1. 启动 Agent 后，系统会自动采集当前设备信息
2. 查看左侧测试项列表，逐项执行测试
3. 填写测试结果（Pass/Fail/NA/Blocked）
4. 完成后点击 "导出结果包"
5. 将生成的 result.zip 上传到 QCC 平台

四、常见问题
------------
Q: 提示 "No module named 'tkinter'"
A: Python 安装时未勾选 tcl/tk，需重新安装 Python

Q: 提示 "No module named 'psutil'"
A: 执行 pip install psutil

Q: S3/S4/重启测试提示权限不足
A: 右键 "启动测试.bat" -> 以管理员身份运行

五、文件说明
------------
manifest.json       - 项目信息
config.json         - 设备配置
test_plan.json      - 测试计划
script_mapping.json - 脚本映射
agent/              - Agent 脚本
core/               - 核心模块
scripts/            - 采集脚本

六、技术支持
------------
如有问题，请联系测试团队。
"""


def _generate_start_bat(project_code: str) -> bytes:
    """生成 Windows 启动脚本（GBK编码，适配 EXE 版本）"""
    # 检查是否有 EXE
    exe_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_engine", "QCC_Test_Agent_Portable", "Agent", "QCC_Test_Agent.exe")
    has_exe = os.path.exists(exe_path)

    if has_exe:
        # EXE 版本 - 无需 Python
        content = f"""@echo off
chcp 936 >nul 2>&1
title QCC 离线测试 Agent - {project_code}

echo ========================================
echo   QCC 离线测试 Agent
echo   Project: {project_code}
echo ========================================
echo.

echo [1/2] 检查环境...
if not exist "%~dp0Agent\\QCC_Test_Agent.exe" (
    echo [错误] 未找到 Agent 程序！
    pause
    exit /b 1
)

echo [2/2] 启动 Agent...
echo.

start "" "%~dp0Agent\\QCC_Test_Agent.exe"

echo [OK] Agent 已启动
echo.
pause
"""
    else:
        # 脚本版本 - 需要 Python
        content = f"""@echo off
chcp 936 >nul 2>&1
title QCC Offline Test Agent - {project_code}

echo ========================================
echo   QCC Offline Test Agent
echo   Project: {project_code}
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check psutil
python -c "import psutil" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing psutil...
    pip install psutil -q
)

echo [OK] Environment check passed
echo [OK] Starting Agent...
echo.

python "%~dp0agent\\agent_runner.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Agent exited with error. Please check above messages.
    pause
)
"""
    # 确保使用 CRLF 换行符（Windows 标准）
    content = content.replace('\n', '\r\n')
    return content.encode('gbk')


@router.get("/{project_id}/export-options")
async def get_export_options(project_id: int):
    """获取导出选项说明"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "options": [
                {
                    "type": "data",
                    "name": "仅数据包",
                    "description": "仅包含测试计划和配置，需配合已安装的 Agent 使用",
                    "size": "约 10KB",
                    "requires": "需要在被测设备上已安装 QCC_Test_Agent"
                },
                {
                    "type": "full",
                    "name": "完整包（推荐）",
                    "description": "包含测试数据 + Agent脚本 + 启动说明，可直接运行",
                    "size": "约 500KB",
                    "requires": "需要 Python 3.11+ 环境"
                }
            ]
        }
    }


@router.post("/{project_id}/import-result-package")
async def import_result_package(project_id: int, file: UploadFile = File(...),
                                 db: AsyncSession = Depends(get_db)):
    """导入 ZIP 结果包"""
    content = await file.read()
    result_data = None

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "result.json" in z.namelist():
                result_data = json.loads(z.read("result.json"))
    except zipfile.BadZipFile:
        return {"code": 400, "message": "无效的ZIP文件", "data": None}

    if result_data is None:
        return {"code": 400, "message": "结果包中未找到 result.json", "data": None}

    updated = _import_results(db, project_id, result_data)
    await db.flush()

    batch = ReportBatch(project_id=project_id, batch_type="result_import",
                        source="zip", status="completed",
                        summary_json=json.dumps({"updated": updated}),
                        created_by=None)
    db.add(batch)
    await db.flush()

    db.add(ActivityLog(user_id=None, action="import", target_type="report",
                      target_id=batch.id, detail=f"导入结果包 {file.filename}"))
    return {"code": 200, "message": "导入成功", "data": {"updated": updated, "batch_id": batch.id}}


def _import_results(db_session, project_id, result_data):
    """解析 results 并更新 test_record 表"""
    results = result_data if isinstance(result_data, list) else result_data.get("test_results", [])
    from sqlalchemy import select, and_
    from app.models.project import TestRecord
    from app.models.template import TestItem
    import asyncio

    async def _do_import():
        updated = 0
        for r in results:
            item_no = r.get("item_no") or r.get("test_id") or r.get("id")
            verdict = r.get("verdict") or r.get("result") or ""
            comment = r.get("comment") or r.get("detail") or ""

            if not item_no or not verdict:
                continue

            # 查找对应的测试项
            item_result = await db_session.execute(
                select(TestItem).where(TestItem.item_no == str(item_no))
            )
            item = item_result.scalar_one_or_none()
            if not item:
                continue

            # 查找对应的测试记录
            record_result = await db_session.execute(
                select(TestRecord).where(and_(
                    TestRecord.project_id == project_id,
                    TestRecord.item_id == item.id
                ))
            )
            record = record_result.scalar_one_or_none()
            if record:
                record.result = verdict
                record.comment = comment
                record.tester = "Agent"
                record.test_date = date.today()
                updated += 1
        return updated

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _do_import())
                return future.result()
        else:
            return loop.run_until_complete(_do_import())
    except Exception:
        return 0
