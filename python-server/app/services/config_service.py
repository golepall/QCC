"""设备配置管理业务逻辑"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import DeviceConfig

CONFIG_FIELDS = [
    "config_name", "source", "bios_vendor", "bios_version", "bios_date",
    "ec_version", "ec_date", "motherboard", "mb_material_code",
    "cpu_model", "cpu_frequency", "cpu_cores", "memory_info", "disk_info",
    "gpu_model", "gpu_driver", "panel_info", "panel_resolution",
    "wlan_model", "wlan_driver", "lan_model", "lan_driver",
    "bt_model", "bt_driver", "audio_codec", "audio_driver",
    "camera_model", "fingerprint_model", "touchpad_model", "touchpad_driver",
    "cardreader_model", "adapter_info", "battery_info", "chassis",
    "psu_info", "odd_info", "os_version", "os_build", "os_language", "os_kernel",
    "cpld_hw_version", "cpld_sw_version", "mcu_hw_version", "mcu_sw_version",
    "software_info", "raw_data",
]


def _dict_to_model(data: dict, existing: DeviceConfig = None) -> DeviceConfig:
    target = existing or DeviceConfig()
    for field in CONFIG_FIELDS:
        if field in data and data[field] is not None:
            val = data[field]
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            setattr(target, field, val)
    return target


async def get_configs(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(DeviceConfig).order_by(DeviceConfig.created_at.desc()))
    return [_row_to_dict(r) for r in result.scalars().all()]


async def get_config(db: AsyncSession, config_id: int) -> dict | None:
    result = await db.execute(select(DeviceConfig).where(DeviceConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    return _row_to_dict(cfg) if cfg else None


async def create_config(db: AsyncSession, data: dict) -> dict:
    cfg = _dict_to_model(data)
    db.add(cfg)
    await db.flush()
    return {"id": cfg.id}


async def update_config(db: AsyncSession, config_id: int, data: dict) -> bool:
    result = await db.execute(select(DeviceConfig).where(DeviceConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return False
    _dict_to_model(data, cfg)
    await db.flush()
    return True


async def import_config(db: AsyncSession, data: dict) -> dict:
    return await create_config(db, data)


def _row_to_dict(cfg: DeviceConfig) -> dict:
    return {c.name: getattr(cfg, c.name) for c in cfg.__table__.columns} | {
        "created_at": str(cfg.created_at) if cfg.created_at else None,
    }
