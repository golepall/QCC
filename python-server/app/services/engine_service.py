"""测试引擎服务 — 直接导入调用（不再 HTTP 代理 Flask）"""
import sys
import os
import traceback
from typing import Any

# 确保 test_engine 在 Python 路径中
_ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_engine")
if _ENGINE_PATH not in sys.path:
    sys.path.insert(0, _ENGINE_PATH)

_instances: dict[str, Any] = {}


def _get_collector():
    if "collector" not in _instances:
        from core.system_collector import SystemCollector
        _instances["collector"] = SystemCollector()
    return _instances["collector"]


def _get_engine():
    if "engine" not in _instances:
        from core.test_engine import TestEngine
        _instances["engine"] = TestEngine()
    return _instances["engine"]


def _get_perf():
    if "perf" not in _instances:
        from core.perf_runner import PerfRunner
        _instances["perf"] = PerfRunner()
    return _instances["perf"]


def _get_stress():
    if "stress" not in _instances:
        from core.stress_manager import StressManager
        _instances["stress"] = StressManager()
    return _instances["stress"]


def _get_remote():
    if "remote" not in _instances:
        from core.remote_executor import RemoteExecutor
        _instances["remote"] = RemoteExecutor()
    return _instances["remote"]


def ok(data=None, msg="success"):
    return {"code": 200, "message": msg, "data": data}


def err(msg, code=500):
    return {"code": code, "message": msg, "data": None}


# ── 公开 API ──

def collect_system():
    """采集系统信息"""
    try:
        data = _get_collector().collect()
        return ok(data)
    except Exception as e:
        traceback.print_exc()
        return err(str(e))


def validate_config(config: dict = None, spec: dict = None):
    """验证设备配置"""
    try:
        result = _get_collector().validate(config or {}, spec or {})
        return ok(result)
    except Exception as e:
        return err(str(e))


def execute_test_item(test_id: str, spec: dict = None, timeout: int = 30):
    """执行单个测试项"""
    try:
        data = _get_engine().execute(test_id, spec or {}, timeout)
        return ok(data)
    except Exception as e:
        return err(str(e))


def run_performance(config: dict = None):
    """执行性能测试"""
    try:
        data = _get_perf().run(config or {})
        return ok(data)
    except Exception as e:
        return err(str(e))


def run_stress(config: dict = None):
    """执行压力测试"""
    try:
        data = _get_stress().run(config or {})
        return ok(data)
    except Exception as e:
        return err(str(e))


def remote_connect(host: str, port: int = 22, username: str = "", password: str = ""):
    """SSH 连接测试"""
    try:
        data = _get_remote().connect(host, port, username, password)
        return ok(data)
    except Exception as e:
        return err(str(e))


def remote_collect(host: str, port: int = 22, username: str = "", password: str = ""):
    """SSH 远程采集系统信息"""
    try:
        data = _get_remote().collect(host, port, username, password)
        return ok(data)
    except Exception as e:
        return err(str(e))


def remote_execute(host: str, port: int = 22, username: str = "", password: str = "",
                   test_ids: list = None, spec: dict = None, timeout: int = 30):
    """SSH 远程执行测试"""
    try:
        data = _get_remote().execute(host, port, username, password, test_ids or [], spec or {}, timeout)
        return ok(data)
    except Exception as e:
        return err(str(e))
