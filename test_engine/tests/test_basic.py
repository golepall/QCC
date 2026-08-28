import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.test_engine import TestEngine

engine = TestEngine()


@pytest.mark.auto
class TestBiosCheck:

    def test_bios_version(self):
        result = engine.execute("bios_version_check")
        assert result["success"], f"BIOS信息获取失败: {result.get('error', '')}"
        assert result["verdict"] == "Pass", f"BIOS版本检查失败: {result['parsed']}"
        print(f"BIOS: {result['parsed']}")


@pytest.mark.auto
class TestDeviceInfo:

    def test_cpu_info(self):
        result = engine.execute("cpu_info_check")
        assert result["success"], f"CPU信息获取失败"
        print(f"CPU: {result['parsed']}")

    def test_memory_info(self):
        result = engine.execute("memory_check")
        assert result["success"], f"内存信息获取失败"
        print(f"Memory: {result['parsed']}")

    def test_disk_info(self):
        result = engine.execute("disk_check")
        assert result["success"], f"硬盘信息获取失败"
        print(f"Disk: {result['parsed']}")

    def test_gpu_info(self):
        result = engine.execute("gpu_check")
        assert result["success"], f"显卡信息获取失败"
        print(f"GPU: {result['parsed']}")


@pytest.mark.auto
class TestDeviceManager:

    def test_no_problem_devices(self):
        result = engine.execute("device_manager_check")
        assert result["success"], f"设备管理器检查失败"
        assert result["verdict"] == "Pass", f"发现异常设备: {result['parsed'].get('raw', '')}"
        print("设备管理器: 无异常设备")


@pytest.mark.auto
class TestNetwork:

    def test_lan(self):
        result = engine.execute("network_lan_check")
        assert result["success"], f"有线网络检查失败"
        print(f"LAN: {result['parsed']}")

    def test_wlan(self):
        result = engine.execute("network_wlan_check")
        assert result["success"], f"无线网络检查失败"
        print(f"WLAN: {result['parsed']}")

    def test_ping(self):
        result = engine.execute("ping_test")
        assert result["success"], f"Ping测试失败"
        print(f"Ping: {'OK' if result['parsed'].get('ping_ok') else 'FAIL'}")


@pytest.mark.auto
class TestAudioVideo:

    def test_audio_device(self):
        result = engine.execute("audio_check")
        assert result["success"], f"音频设备检查失败"
        assert result["verdict"] == "Pass", "未检测到音频设备"
        print(f"Audio: {result['parsed']}")

    def test_usb_devices(self):
        result = engine.execute("usb_check")
        assert result["success"], f"USB设备检查失败"
        print(f"USB: {result['parsed']}")


@pytest.mark.auto
class TestPowerManagement:

    def test_s3_support(self):
        result = engine.execute("s3_support_check")
        assert result["success"], f"S3支持检查失败"
        print(f"S3 Support: {result['parsed']}")

    def test_boot_time(self):
        result = engine.execute("boot_time_check")
        assert result["success"], f"开机时间检查失败"
        print(f"Boot: {result['parsed']}")
