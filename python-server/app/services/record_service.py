"""测试记录管理业务逻辑"""
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import TestCategory, TestItem
from app.models.project import ReportProject, TestRecord


async def get_records(db: AsyncSession, project_id: int, category_id: str = "") -> list[dict]:
    """获取项目测试记录列表"""
    if category_id:
        sql = text("""
            SELECT tr.*, ti.item_no, ti.test_item, ti.test_case, ti.condition_desc, ti.criteria, ti.is_header,
                   tc.category_name, tc.sheet_name, tc.id as cat_id
            FROM test_record tr
            JOIN test_item ti ON tr.item_id = ti.id
            JOIN test_category tc ON ti.category_id = tc.id
            WHERE tr.project_id = :pid AND tc.id = :cid
            ORDER BY tc.sort_order, ti.sort_order
        """)
        result = await db.execute(sql, {"pid": project_id, "cid": int(category_id)})
    else:
        sql = text("""
            SELECT tr.*, ti.item_no, ti.test_item, ti.test_case, ti.condition_desc, ti.criteria, ti.is_header,
                   tc.category_name, tc.sheet_name, tc.id as cat_id
            FROM test_record tr
            JOIN test_item ti ON tr.item_id = ti.id
            JOIN test_category tc ON ti.category_id = tc.id
            WHERE tr.project_id = :pid
            ORDER BY tc.sort_order, ti.sort_order
        """)
        result = await db.execute(sql, {"pid": project_id})

    return [dict(r._mapping) for r in result.all()]


async def get_all_records(db: AsyncSession, project_id: int) -> dict | None:
    """获取全部记录（按分类分组）"""
    proj = await db.execute(select(ReportProject).where(ReportProject.id == project_id))
    project = proj.scalar_one_or_none()
    if project is None:
        return None

    cat_result = await db.execute(
        select(TestCategory).where(TestCategory.template_id == project.template_id).order_by(TestCategory.sort_order)
    )
    categories = list(cat_result.scalars().all())

    result = {}
    for cat in categories:
        item_result = await db.execute(
            select(TestItem).where(TestItem.category_id == cat.id).order_by(TestItem.sort_order)
        )
        items = list(item_result.scalars().all())

        rec_result = await db.execute(
            select(TestRecord).where(TestRecord.project_id == project_id,
                                     TestRecord.item_id.in_(
                                         select(TestItem.id).where(TestItem.category_id == cat.id)
                                     ))
        )
        record_map = {r.item_id: r for r in rec_result.scalars().all()}

        result[str(cat.id)] = {
            "category": {"id": cat.id, "category_code": cat.category_code, "category_name": cat.category_name,
                         "sheet_name": cat.sheet_name, "sort_order": cat.sort_order},
            "test_items": [
                {
                    "id": item.id, "item_no": item.item_no, "test_item": item.test_item,
                    "test_case": item.test_case, "condition_desc": item.condition_desc,
                    "criteria": item.criteria, "is_header": item.is_header, "sort_order": item.sort_order,
                    "record": (
                        {"id": record_map[item.id].id, "result": record_map[item.id].result,
                         "comment": record_map[item.id].comment, "evidence": record_map[item.id].evidence,
                         "tester": record_map[item.id].tester,
                         "test_date": str(record_map[item.id].test_date) if record_map[item.id].test_date else None}
                        if item.id in record_map else
                        {"result": "", "comment": ""}
                    ),
                }
                for item in items
            ],
        }

    return result


async def update_record(db: AsyncSession, project_id: int, record_id: int, data: dict) -> bool:
    """更新单条测试记录"""
    rec = await db.execute(
        select(TestRecord).where(TestRecord.id == record_id, TestRecord.project_id == project_id)
    )
    record = rec.scalar_one_or_none()
    if record is None:
        return False

    if data.get("result") is not None:
        record.result = data["result"]
    if data.get("comment") is not None:
        record.comment = data["comment"]
    if data.get("evidence") is not None:
        record.evidence = data["evidence"]
    if data.get("tester") is not None:
        record.tester = data["tester"]
    if data.get("test_date") is not None:
        record.test_date = data["test_date"]

    await db.flush()
    return True


async def batch_update_records(db: AsyncSession, project_id: int, records: list[dict]) -> bool:
    """批量更新测试记录"""
    if not records:
        return False
    for r in records:
        await db.execute(
            text("UPDATE test_record SET result = :result, comment = COALESCE(:comment, comment),"
                 " updated_at = CURRENT_TIMESTAMP WHERE id = :id AND project_id = :pid"),
            {"result": r.get("result"), "comment": r.get("comment"), "id": r.get("id"), "pid": project_id}
        )
    return True


async def get_record_stats(db: AsyncSession, project_id: int) -> dict:
    """获取测试记录统计"""
    overall_sql = text("""
        SELECT COUNT(*) as total,
            SUM(CASE WHEN result = 'Pass' THEN 1 ELSE 0 END) as pass,
            SUM(CASE WHEN result = 'Fail' THEN 1 ELSE 0 END) as fail,
            SUM(CASE WHEN result = 'NA' THEN 1 ELSE 0 END) as na,
            SUM(CASE WHEN result = 'Blocked' THEN 1 ELSE 0 END) as blocked,
            SUM(CASE WHEN result = 'Manual' THEN 1 ELSE 0 END) as manual,
            SUM(CASE WHEN result = 'Error' THEN 1 ELSE 0 END) as error,
            SUM(CASE WHEN result = '' OR result IS NULL OR result = 'NotTested' THEN 1 ELSE 0 END) as pending
        FROM test_record WHERE project_id = :pid
    """)
    result = await db.execute(overall_sql, {"pid": project_id})
    overall = dict(result.one()._mapping)

    cat_sql = text("""
        SELECT tc.id, tc.category_name,
            COUNT(tr.id) as total,
            SUM(CASE WHEN tr.result = 'Pass' THEN 1 ELSE 0 END) as pass,
            SUM(CASE WHEN tr.result = 'Fail' THEN 1 ELSE 0 END) as fail,
            SUM(CASE WHEN tr.result = 'NA' THEN 1 ELSE 0 END) as na,
            SUM(CASE WHEN tr.result = 'Blocked' THEN 1 ELSE 0 END) as blocked,
            SUM(CASE WHEN tr.result = 'Manual' THEN 1 ELSE 0 END) as manual,
            SUM(CASE WHEN tr.result = 'Error' THEN 1 ELSE 0 END) as error,
            SUM(CASE WHEN tr.result = '' OR tr.result IS NULL OR tr.result = 'NotTested' THEN 1 ELSE 0 END) as pending
        FROM test_record tr
        JOIN test_item ti ON tr.item_id = ti.id
        JOIN test_category tc ON ti.category_id = tc.id
        WHERE tr.project_id = :pid
        GROUP BY tc.id
        ORDER BY tc.sort_order
    """)
    result = await db.execute(cat_sql, {"pid": project_id})
    categories = [dict(r._mapping) for r in result.all()]

    return {"overall": overall, "categories": categories}


async def batch_set_records(db: AsyncSession, project_id: int, category_id: int, result_value: str) -> bool:
    """按分类批量设置未填写记录的结果"""
    await db.execute(text("""
        UPDATE test_record SET result = :result, updated_at = CURRENT_TIMESTAMP
        WHERE project_id = :pid AND item_id IN (
            SELECT id FROM test_item WHERE category_id = :cid AND is_header = 0
        ) AND (result = '' OR result IS NULL)
    """), {"result": result_value, "pid": project_id, "cid": category_id})
    return True
