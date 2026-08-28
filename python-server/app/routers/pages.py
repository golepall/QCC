"""页面路由（服务端渲染 HTML）"""
from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from jose import JWTError

from app.dependencies import get_db
from app.services import auth_service, template_service, project_service, bug_service, product_service, dashboard_service, record_service, requirement_service, task_service
from app.config import settings
from app.middleware.auth import decode_token

TEMPLATE_DIR = str(Path(__file__).parent.parent.parent / "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

router = APIRouter(tags=["页面"])


# ── Cookie 认证辅助 ──

async def _get_user_from_cookie(request: Request, db: AsyncSession):
    token = request.cookies.get("qcc_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        return await auth_service.get_user_by_id(db, user_id)
    except (JWTError, ValueError, TypeError):
        return None


async def _require_auth(request: Request, db: AsyncSession):
    user = await _get_user_from_cookie(request, db)
    if user is None:
        return None, RedirectResponse("/page/login", status_code=302)
    return user, None


def _render(template_name: str, **ctx) -> HTMLResponse:
    return HTMLResponse(env.get_template(template_name).render(**ctx))


# ── 根路径重定向 ──

@router.get("/")
async def root():
    return RedirectResponse("/page/login", status_code=302)


# ── 公开页面 ──

@router.get("/page/login")
async def login_page(request: Request):
    return _render("auth/login.html", request=request)


@router.post("/page/login")
async def login_action(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await auth_service.authenticate(db, username, password)
    if result is None:
        return JSONResponse({"code": 1, "message": "用户名或密码错误"})
    response = JSONResponse({"code": 0, "message": "登录成功", "data": result})
    response.set_cookie("qcc_token", result["token"], httponly=True, max_age=259200, path="/")
    return response


@router.post("/page/register")
async def register_action(username: str = Form(...), password: str = Form(...), displayName: str = Form(""), db: AsyncSession = Depends(get_db)):
    user = await auth_service.register_user(db, username, password, displayName)
    if user is None:
        return JSONResponse({"code": 400, "message": "用户名已存在"})
    return JSONResponse({"code": 200, "message": "注册成功"})


@router.get("/page/logout")
async def logout():
    resp = RedirectResponse("/page/login", status_code=302)
    resp.delete_cookie("qcc_token", path="/")
    return resp


# ── 仪表盘 ──

@router.get("/page/dashboard")
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    d = await dashboard_service.get_dashboard_data(db)
    return _render("dashboard/index.html", request=request, user=user, active_page="dashboard",
                   stats={"projects": d["totalProjects"], "bugs": d["totalBugs"],
                          "tasks": d["totalTasks"], "templates": d["totalTemplates"]},
                   activities=d.get("recentActivities", []),
                   recent_projects=d.get("recentProjects", []))


# ── 模板管理 ──

@router.get("/page/templates")
async def templates_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    templates = await template_service.get_templates(db)
    data = [_tpl_dict(t) for t in templates]
    return _render("templates/list.html", request=request, user=user, active_page="templates", templates=data, filter="")


@router.get("/page/templates/list")
async def templates_list(request: Request, category: str = Query(""), keyword: str = Query(""), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    templates = await template_service.get_templates(db, category=category)
    data = [_tpl_dict(t) for t in templates]
    if keyword:
        data = [t for t in data if keyword.lower() in t["name"].lower()]
    return _render("components/template_cards.html", templates=data)


def _tpl_dict(t) -> dict:
    return {"id": t.id, "template_code": t.template_code, "name": t.name,
            "doc_code": t.doc_code, "version": t.version, "category": t.category, "product_type": t.product_type}


@router.get("/page/excel-templates/preview")
async def excel_template_preview(request: Request, file: str = Query("")):
    user, redirect = await _require_auth(request, await _get_db_session(request))
    if redirect: return redirect
    if not file:
        return RedirectResponse("/page/templates", status_code=302)
    return _render("templates/excel_preview.html", request=request, user=user, active_page="templates", filename=file)


async def _get_db_session(request):
    """获取数据库会话（辅助函数）"""
    from app.dependencies import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    engine = get_engine()
    async with AsyncSession(engine) as db:
        return db


# ── 项目管理 ──

@router.get("/page/projects")
async def projects_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await project_service.get_projects(db, page=1, page_size=20)
    return _render("projects/list.html", request=request, user=user, active_page="projects",
        projects=data["list"], total=data["total"], page=1,
        total_pages=max((data["total"] + 19) // 20, 1), filter_status="", keyword="")


@router.get("/page/projects/create")
async def create_project_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    templates = await template_service.get_templates(db)
    tpl_data = [{"id": t.id, "template_code": t.template_code, "name": t.name} for t in templates]
    return _render("projects/create.html", request=request, user=user, active_page="projects", templates=tpl_data)


@router.post("/page/projects/create")
async def create_project_action(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await request.json()
    result = await project_service.create_project(db, data, user.id)
    if "error" in result:
        return {"code": 400, "message": result["error"], "data": None}
    return {"code": 200, "message": "创建成功", "data": result}


@router.delete("/page/projects/{project_id}/delete")
async def delete_project_page(project_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    result = await project_service.delete_project(db, project_id, user.id, user.role)
    if "error" in result:
        return {"code": 400, "message": result["error"]}
    return Response(status_code=200)


@router.get("/page/projects/list")
async def projects_list(request: Request, status: str = Query(""), keyword: str = Query(""),
                         page: int = Query(1), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await project_service.get_projects(db, status=status, keyword=keyword, page=page, page_size=20)
    return _render("components/project_table.html", projects=data["list"], total=data["total"],
        page=page, total_pages=max((data["total"] + 19) // 20, 1))


@router.get("/page/projects/{project_id}")
async def project_detail(project_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    detail = await project_service.get_project_detail(db, project_id)
    if detail is None:
        return RedirectResponse("/page/projects", status_code=302)
    # 获取测试记录统计
    record_stats = await record_service.get_record_stats(db, project_id)
    # 获取该项目的 Bug 列表
    bug_list = await bug_service.get_project_bugs(db, project_id)
    return _render("projects/detail.html", request=request, user=user, active_page="projects",
                   project=detail, record_stats=record_stats, bugs=bug_list,
                   bug_total=len(bug_list))


# ── Bug 管理 ──

@router.get("/page/bugs")
async def bugs_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await bug_service.get_all_bugs(db, page=1, page_size=20)
    return _render("bugs/list.html", request=request, user=user, active_page="bugs",
        bugs=data["list"], total=data["total"], page=1,
        total_pages=max((data["total"] + 19) // 20, 1), filter_status="", filter_severity="")


@router.get("/page/bugs/list")
async def bugs_list(request: Request, status: str = Query(""), severity: str = Query(""),
                     keyword: str = Query(""), page: int = Query(1), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await bug_service.get_all_bugs(db, status=status, severity=severity, keyword=keyword, page=page, page_size=20)
    return _render("components/bug_table.html", bugs=data["list"], total=data["total"],
        page=page, total_pages=max((data["total"] + 19) // 20, 1))


# ── 产品管理 ──

@router.get("/page/products")
async def products_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await product_service.get_products(db, page=1, page_size=100)
    return _render("products/list.html", request=request, user=user, active_page="products", products=data["list"])


# ── 个人工作台 ──

@router.get("/page/workspace")
async def workspace_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    ws = await dashboard_service.get_workspace_data(db, user.id)
    return _render("workspace/index.html", request=request, user=user, active_page="workspace",
                   workspace=ws)


# ── 任务看板 ──

@router.get("/page/tasks")
async def tasks_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    board = await task_service.get_task_board(db)
    stats = await task_service.get_task_stats(db)
    return _render("tasks/board.html", request=request, user=user, active_page="tasks",
                   board=board, stats=stats)


# ── 需求管理 ──

@router.get("/page/requirements")
async def requirements_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await requirement_service.get_requirements(db, page=1, page_size=20)
    raw_stats = await requirement_service.get_req_stats(db)
    stats_obj = {
        "total": raw_stats.get("total", 0) or 0,
        "active": raw_stats.get("active", 0) or 0,
        "completed": raw_stats.get("completed", 0) or 0,
        "draft": raw_stats.get("draft", 0) or 0,
    }
    return _render("requirements/list.html", request=request, user=user, active_page="requirements",
                   requirements=data["list"], total=data["total"], page=1,
                   total_pages=max((data["total"] + 19) // 20, 1), stats=stats_obj)


@router.get("/page/requirements/list")
async def requirements_list(request: Request, req_type: str = Query(""), status: str = Query(""),
                             priority: str = Query(""), keyword: str = Query(""),
                             page: int = Query(1), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await requirement_service.get_requirements(db, req_type=req_type, status=status,
        priority=priority, keyword=keyword, page=page, page_size=20)
    return _render("components/requirement_table.html", requirements=data["list"], total=data["total"],
        page=page, total_pages=max((data["total"] + 19) // 20, 1))


# ── 报告中心 ──

@router.get("/page/report")
async def report_center_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await project_service.get_projects(db, page=1, page_size=20)
    # 统计各状态项目数（用SQL直接统计，避免全量加载）
    from sqlalchemy import text as sql_text
    count_result = await db.execute(sql_text("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status='testing' THEN 1 ELSE 0 END) as testing,
            SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END) as draft
        FROM report_project
    """))
    row = count_result.one()
    stats = {"total_projects": row.total or 0, "completed": row.completed or 0, "testing": row.testing or 0, "draft": row.draft or 0}
    return _render("report/index.html", request=request, user=user, active_page="report",
                   projects=data["list"], stats=stats, page=1,
                   total_pages=max((data["total"] + 19) // 20, 1))


@router.get("/page/report/list")
async def report_list(request: Request, status: str = Query(""), keyword: str = Query(""),
                       page: int = Query(1), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await project_service.get_projects(db, status=status, keyword=keyword, page=page, page_size=20)
    return _render("components/report_table.html", projects=data["list"], total=data["total"],
        page=page, total_pages=max((data["total"] + 19) // 20, 1))


@router.get("/page/projects/{project_id}/report/preview")
async def report_preview_page(project_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    project = await project_service.get_project_detail(db, project_id)
    if not project:
        return RedirectResponse("/page/report", status_code=302)
    return _render("report/preview.html", request=request, user=user, active_page="report",
                   project=project, project_id=project_id)


@router.get("/page/autotest")
async def autotest_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    data = await project_service.get_projects(db, page=1, page_size=100)
    projects = [{"id": p["id"], "project_code": p["project_code"], "product_name": p["product_name"]} for p in data["list"]]
    return _render("autotest/index.html", request=request, user=user, active_page="autotest", projects=projects)


# ── 测试记录页面 ──

@router.get("/page/projects/{project_id}/records")
async def test_records_page(project_id: int, request: Request, cat: str = Query(""), db: AsyncSession = Depends(get_db)):
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    project = await project_service.get_project_detail(db, project_id)
    if project is None:
        return RedirectResponse("/page/projects", status_code=302)
    records = await record_service.get_all_records(db, project_id)
    if records is None:
        return RedirectResponse("/page/projects", status_code=302)
    active_cat = cat if cat and cat in records else (list(records.keys())[0] if records else "")
    return _render("records/index.html", request=request, user=user, active_page="projects",
                   project=project, records=records, active_cat=active_cat, project_id=project_id)


@router.put("/page/projects/{project_id}/records/{record_id}")
async def update_record_row(project_id: int, record_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """HTMX — 更新单条测试记录，返回该行 HTML"""
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    body = await request.form()
    result_val = body.get("result", "")
    comment_val = body.get("comment", "")
    ok = await record_service.update_record(db, project_id, record_id,
        {"result": result_val if result_val else None, "comment": comment_val if comment_val else None})
    if not ok:
        return HTMLResponse("<span class='result-fail'>保存失败</span>")

    # 重新查询该记录对应的 item 信息，渲染单行
    from sqlalchemy import select
    from app.models.project import TestRecord
    from app.models.template import TestItem
    rec_result = await db.execute(select(TestRecord).where(TestRecord.id == record_id))
    record = rec_result.scalar_one_or_none()
    if not record:
        return HTMLResponse("<span>—</span>")
    item_result = await db.execute(select(TestItem).where(TestItem.id == record.item_id))
    item = item_result.scalar_one_or_none()
    tmpl = env.get_template("components/record_row.html")
    return HTMLResponse(tmpl.render(item=item, record=record, project_id=project_id))


@router.post("/page/projects/{project_id}/records/batch-set")
async def batch_set_records(project_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """HTMX — 批量设置分类结果"""
    user, redirect = await _require_auth(request, db)
    if redirect: return redirect
    body = await request.form()
    result_val = body.get("result", "")
    category_id = body.get("active-cat", "")
    if not result_val or not category_id:
        return HTMLResponse("<div class='empty-state'><div class='empty-title'>请选择结果和目标分类</div></div>")
    await record_service.batch_set_records(db, project_id, int(category_id), result_val)
    await db.flush()
    # 重新加载全部记录，保持与初始页面一致
    records = await record_service.get_all_records(db, project_id)
    return _render("components/record_rows.html", records=records or {}, project_id=project_id)
