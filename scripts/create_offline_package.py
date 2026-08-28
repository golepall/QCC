"""创建完整离线测试包（含 EXE）"""
import os
import sys
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

# 路径配置
ROOT_DIR = Path(__file__).parent.parent
ENGINE_DIR = ROOT_DIR / "test_engine"
AGENT_EXE_DIR = ENGINE_DIR / "QCC_Test_Agent_Portable" / "Agent"
OUTPUT_DIR = ROOT_DIR / "exports"


def create_package(project_code: str = "RPT-20260714-002"):
    """创建完整离线测试包"""
    print("=" * 60)
    print(f"Creating offline package for: {project_code}")
    print("=" * 60)

    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"QCC_Agent_{project_code}_{timestamp}"
    package_dir = OUTPUT_DIR / package_name

    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir()

    # 1. 复制 EXE
    print("\n[1/4] Copying Agent EXE...")
    agent_dest = package_dir / "Agent"
    if AGENT_EXE_DIR.exists():
        shutil.copytree(AGENT_EXE_DIR, agent_dest)
        exe_size = (agent_dest / "QCC_Test_Agent.exe").stat().st_size / 1024 / 1024
        print(f"  Copied: Agent/ ({exe_size:.1f} MB)")
    else:
        print(f"  ERROR: Agent EXE not found at {AGENT_EXE_DIR}")
        return None

    # 2. 复制测试数据（从导出包）
    print("\n[2/4] Copying test data...")
    data_src = ROOT_DIR / project_code
    if data_src.exists():
        data_dest = package_dir / "TestData"
        data_dest.mkdir()

        # 复制 JSON 文件
        for json_file in ["manifest.json", "test_plan.json", "config.json", "script_mapping.json", "result_template.json"]:
            src = data_src / json_file
            if src.exists():
                shutil.copy2(src, data_dest / json_file)
                print(f"  Copied: {json_file}")

        # 复制脚本文件
        scripts_src = data_src / "scripts"
        if scripts_src.exists():
            shutil.copytree(scripts_src, data_dest / "scripts")
            print(f"  Copied: scripts/")

        # 复制脚本注册表
        registry = data_src / "script_registry.json"
        if registry.exists():
            shutil.copy2(registry, data_dest / "script_registry.json")
            print(f"  Copied: script_registry.json")
    else:
        print(f"  WARNING: Test data not found, creating sample data")
        _create_sample_data(package_dir / "TestData", project_code)

    # 3. 创建启动脚本
    print("\n[3/4] Creating launch scripts...")
    _create_launch_scripts(package_dir, project_code)

    # 4. 创建 ZIP
    print("\n[4/4] Creating ZIP archive...")
    zip_path = OUTPUT_DIR / f"{package_name}.zip"
    _create_zip(package_dir, zip_path)

    # 清理临时目录
    shutil.rmtree(package_dir)

    print("\n" + "=" * 60)
    print("Package created successfully!")
    print(f"Output: {zip_path}")
    print(f"Size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    print("=" * 60)

    return str(zip_path)


def _create_sample_data(data_dir: Path, project_code: str):
    """创建示例测试数据"""
    data_dir.mkdir(exist_ok=True)

    manifest = {
        "project_code": project_code,
        "generated_at": datetime.now().isoformat(),
        "agent_version": "1.1.0"
    }

    with open(data_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(data_dir / "test_plan.json", "w", encoding="utf-8") as f:
        json.dump([], f)

    with open(data_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    with open(data_dir / "script_mapping.json", "w", encoding="utf-8") as f:
        json.dump([], f)


def _create_launch_scripts(package_dir: Path, project_code: str):
    """创建启动脚本（纯 ASCII 编码，避免乱码）"""

    # Windows 批处理 - 纯英文，使用二进制写入确保正确的 CRLF 换行符
    lines = [
        '@echo off',
        'title QCC Test Agent - ' + project_code,
        '',
        'echo ========================================',
        'echo   QCC Test Agent - Offline Edition',
        'echo   Project: ' + project_code,
        'echo ========================================',
        'echo.',
        '',
        'echo [1/2] Checking environment...',
        'if not exist "Agent\\QCC_Test_Agent.exe" (',
        '    echo [ERROR] Agent not found!',
        '    pause',
        '    exit /b 1',
        ')',
        '',
        'echo [2/2] Starting Agent...',
        'echo.',
        '',
        'start "" "Agent\\QCC_Test_Agent.exe"',
        '',
        'echo [OK] Agent started.',
        'echo.',
        'pause',
    ]

    # 使用二进制模式写入，确保 CRLF 换行符
    with open(package_dir / "start.bat", "wb") as f:
        for line in lines:
            f.write((line + '\r\n').encode('ascii'))
    print("  Created: start.bat")

    # README
    readme = f"""QCC Test Agent - Offline Edition
================================

Project: {project_code}
Version: 1.1.0
Build: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

QUICK START
-----------
1. Double-click "start.bat" (or "启动测试.bat")
2. The Agent window will open automatically
3. Load test data from "TestData" folder
4. Run tests and export results

FOLDER STRUCTURE
----------------
├── Agent/              Test Agent program (EXE)
│   ├── QCC_Test_Agent.exe
│   └── _internal/      Dependencies
├── TestData/           Test data files
│   ├── manifest.json   Project info
│   ├── test_plan.json  Test plan
│   ├── config.json     Device config
│   └── script_mapping.json
├── start.bat           Launch script (English)
├── 启动测试.bat        Launch script (Chinese)
└── README.txt          This file

SYSTEM REQUIREMENTS
-------------------
- Windows 10/11 (64-bit)
- No Python required
- No internet connection needed
- 100 MB free disk space

FOR ADMIN OPERATIONS
--------------------
S3/S4/Reboot tests require administrator privileges:
Right-click start.bat -> Run as administrator

TROUBLESHOOTING
---------------
Q: Agent won't start
A: Check if Windows Defender blocks it. Click "More info" -> "Run anyway"

Q: Missing VCRUNTIME140.dll
A: Install Visual C++ Redistributable from Microsoft

Q: Tests not running
A: Ensure TestData folder contains valid test_plan.json

SUPPORT
-------
Contact the test team for assistance.
"""

    with open(package_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme)
    print("  Created: README.txt")


def _create_zip(source_dir: Path, zip_path: Path):
    """创建 ZIP 文件"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(source_dir.parent)
                zf.write(file_path, arcname)


if __name__ == "__main__":
    # 使用命令行参数或默认值
    code = sys.argv[1] if len(sys.argv) > 1 else "RPT-20260714-002"
    create_package(code)
