"""通知管理业务逻辑"""
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management import Notification


async def get_notifications(
    db: AsyncSession, user_id: int, is_read: int = None, page: int = 1, page_size: int = 50
) -> dict:
    params = {"uid": user_id}
    conditions = ["n.user_id = :uid"]
    if is_read is not None:
        conditions.append("n.is_read = :is_read")
        params["is_read"] = is_read
    where = " AND ".join(conditions)

    count_result = await db.execute(text(f"SELECT COUNT(*) FROM notification n WHERE {where}"), params)
    total = count_result.scalar()
    offset = (page - 1) * page_size

    result = await db.execute(text(f"""
        SELECT n.* FROM notification n WHERE {where}
        ORDER BY n.created_at DESC LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": offset})
    list_data = [dict(r._mapping) for r in result.all()]
    for item in list_data:
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])

    unread_result = await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == 0)
    )
    unread = unread_result.scalar()

    return {"list": list_data, "total": total, "unread": unread, "page": page, "pageSize": page_size}


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == 0)
    )
    return result.scalar()


async def mark_as_read(db: AsyncSession, noti_id: int, user_id: int):
    await db.execute(
        text("UPDATE notification SET is_read = 1 WHERE id = :id AND user_id = :uid"),
        {"id": noti_id, "uid": user_id}
    )


async def mark_all_read(db: AsyncSession, user_id: int):
    await db.execute(
        text("UPDATE notification SET is_read = 1 WHERE user_id = :uid"),
        {"uid": user_id}
    )


async def delete_notification(db: AsyncSession, noti_id: int, user_id: int):
    await db.execute(
        text("DELETE FROM notification WHERE id = :id AND user_id = :uid"),
        {"id": noti_id, "uid": user_id}
    )
