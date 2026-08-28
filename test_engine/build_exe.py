"""打包 Agent 为独立 EXE"""
import subprocess
import sys
import os
import shutil
from pathlib import Path

# 路径配置
ENGINE_DIR = Path(__file__).parent
AGENT_DIR = ENGINE_DIR / "agent"
DIST_DIR = ENGINE_DIR / "dist"
BUILD_DIR = ENGINE_DIR / "build"


def build_exe():
    """使用 PyInstaller 打包"""
    print("=" * 60)
    print("Building QCC Test Agent EXE")
    print("=" * 60)

    # 清理旧的构建文件
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned: {d}")

    # PyInstaller 参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name", "QCC_Test_Agent",
        "--add-data", f"{ENGINE_DIR / 'core'};core",
        "--add-data", f"{ENGINE_DIR / 'script_registry.json'};.",
        "--add-data", f"{ENGINE_DIR / 'scripts'};scripts",
        "--hidden-import", "psutil",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "uuid",              # 修复：添加 uuid 模块
        "--hidden-import", "json",
        "--hidden-import", "hashlib",
        "--hidden-import", "socket",
        "--hidden-import", "platform",
        "--hidden-import", "subprocess",
        "--hidden-import", "shutil",
        "--hidden-import", "zipfile",
        "--hidden-import", "webbrowser",
        "--hidden-import", "datetime",
        "--collect-submodules", "core",
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        str(AGENT_DIR / "agent_runner.py")
    ]

    print("\nRunning PyInstaller...")
    print(f"Command: {' '.join(cmd[:5])}...")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(AGENT_DIR))

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed!")
        print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
        return None

    # 检查输出
    exe_path = DIST_DIR / "QCC_Test_Agent" / "QCC_Test_Agent.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / 1024 / 1024
        print(f"\n[SUCCESS] Build completed!")
        print(f"EXE path: {exe_path}")
        print(f"EXE size: {size_mb:.1f} MB")
        return DIST_DIR / "QCC_Test_Agent"
    else:
        print("\n[ERROR] EXE not found after build!")
        return None


def create_portable_package(exe_dir: Path):
    """创建便携式测试包"""
    print("\n" + "=" * 60)
    print("Creating portable package")

    # 创建输出目录
    output_dir = ENGINE_DIR / "QCC_Test_Agent_Portable"
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # 复制 EXE 及依赖
    shutil.copytree(exe_dir, output_dir / "Agent")
    print(f"Copied Agent to: {output_dir / 'Agent'}")

    # 创建测试数据目录模板
    data_dir = output_dir / "TestData"
    data_dir.mkdir()

    # 创建示例文件
    import json
    sample = {
        "manifest": {"project_code": "SAMPLE", "generated_at": "2026-01-01"},
        "test_plan": [],
        "config": {},
        "script_mapping": []
    }

    for name, data in sample.items():
        with open(data_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # 创建启动脚本（ASCII 编码）
    start_bat = """@echo off
title QCC Test Agent

echo ========================================
echo   QCC Test Agent - Offline Edition
echo ========================================
echo.

if not exist "Agent\\QCC_Test_Agent.exe" (
    echo [ERROR] Agent not found!
    pause
    exit /b 1
)

echo [OK] Starting Agent...
start "" "Agent\\QCC_Test_Agent.exe"
echo [OK] Agent started.
echo.
pause
"""
    with open(output_dir / "start.bat", "w", encoding="ascii") as f:
        f.write(start_bat)

    # 创建说明文件
    readme = """QCC Test Agent - Portable Edition
================================

This is a standalone test agent that requires NO Python installation.

Usage:
1. Extract this folder to any location
2. Double-click "start.bat" to launch
3. Load test data from "TestData" folder
4. Run tests and export results

Requirements:
- Windows 10/11 (64-bit)
- No Python required
- No internet connection needed

Folder Structure:
- Agent/        : Test agent program
- TestData/     : Test data files
- start.bat     : Launch script

For admin operations (S3/S4/Reboot tests):
Right-click start.bat -> Run as administrator
"""
    with open(output_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"Created portable package: {output_dir}")
    return output_dir


if __name__ == "__main__":
    exe_dir = build_exe()
    if exe_dir:
        create_portable_package(exe_dir)
        print("\n" + "=" * 60)
        print("Done! Portable package is ready.")
        print("=" * 60)
    else:
        print("\nBuild failed!")
        sys.exit(1)
