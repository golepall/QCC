"""设备配置数据模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DeviceConfig(Base):
    __tablename__ = "device_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual")

    # BIOS / EC
    bios_vendor: Mapped[str] = mapped_column(String(200), default="")
    bios_version: Mapped[str] = mapped_column(String(100), default="")
    bios_date: Mapped[str] = mapped_column(String(50), default="")
    ec_version: Mapped[str] = mapped_column(String(100), default="")
    ec_date: Mapped[str] = mapped_column(String(50), default="")

    # 主板
    motherboard: Mapped[str] = mapped_column(String(200), default="")
    mb_material_code: Mapped[str] = mapped_column(String(100), default="")

    # CPU
    cpu_model: Mapped[str] = mapped_column(String(200), default="")
    cpu_frequency: Mapped[str] = mapped_column(String(50), default="")
    cpu_cores: Mapped[int] = mapped_column(Integer, default=0)

    # 内存/磁盘
    memory_info: Mapped[str] = mapped_column(Text, default="[]")
    disk_info: Mapped[str] = mapped_column(Text, default="[]")

    # GPU
    gpu_model: Mapped[str] = mapped_column(String(200), default="")
    gpu_driver: Mapped[str] = mapped_column(String(100), default="")

    # 面板
    panel_info: Mapped[str] = mapped_column(String(200), default="")
    panel_resolution: Mapped[str] = mapped_column(String(50), default="")

    # 无线/有线
    wlan_model: Mapped[str] = mapped_column(String(200), default="")
    wlan_driver: Mapped[str] = mapped_column(String(100), default="")
    lan_model: Mapped[str] = mapped_column(String(200), default="")
    lan_driver: Mapped[str] = mapped_column(String(100), default="")

    # 蓝牙/音频
    bt_model: Mapped[str] = mapped_column(String(200), default="")
    bt_driver: Mapped[str] = mapped_column(String(100), default="")
    audio_codec: Mapped[str] = mapped_column(String(200), default="")
    audio_driver: Mapped[str] = mapped_column(String(100), default="")

    # 摄像头/指纹/触摸板/读卡器
    camera_model: Mapped[str] = mapped_column(String(200), default="")
    fingerprint_model: Mapped[str] = mapped_column(String(200), default="")
    touchpad_model: Mapped[str] = mapped_column(String(200), default="")
    touchpad_driver: Mapped[str] = mapped_column(String(100), default="")
    cardreader_model: Mapped[str] = mapped_column(String(200), default="")

    # 适配器/电池/机箱/电源/光驱
    adapter_info: Mapped[str] = mapped_column(Text, default="")
    battery_info: Mapped[str] = mapped_column(Text, default="")
    chassis: Mapped[str] = mapped_column(String(200), default="")
    psu_info: Mapped[str] = mapped_column(Text, default="")
    odd_info: Mapped[str] = mapped_column(Text, default="")

    # OS
    os_version: Mapped[str] = mapped_column(String(200), default="")
    os_build: Mapped[str] = mapped_column(String(100), default="")
    os_language: Mapped[str] = mapped_column(String(50), default="")
    os_kernel: Mapped[str] = mapped_column(String(100), default="")

    # CPLD/MCU
    cpld_hw_version: Mapped[str] = mapped_column(String(100), default="")
    cpld_sw_version: Mapped[str] = mapped_column(String(100), default="")
    mcu_hw_version: Mapped[str] = mapped_column(String(100), default="")
    mcu_sw_version: Mapped[str] = mapped_column(String(100), default="")

    # 软件/原始数据
    software_info: Mapped[str] = mapped_column(Text, default="{}")
    raw_data: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    projects: Mapped[list["ReportProject"]] = relationship(back_populates="config")
