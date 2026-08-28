import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.system_collector import SystemCollector
from core.test_engine import TestEngine
from core.perf_runner import PerfRunner

collector = SystemCollector()
engine = TestEngine()


def pytest_configure(config):
    config.addinivalue_line("markers", "auto: 自动化测试项")
    config.addinivalue_line("markers", "manual: 需人工确认的测试项")
    config.addinivalue_line("markers", "performance: 性能测试项")
    config.addinivalue_line("markers", "stress: 压力测试项")
