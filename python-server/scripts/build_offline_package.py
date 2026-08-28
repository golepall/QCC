"""构建离线测试完整工具包（包含 EXE）
使用 PyInstaller 打包 Agent 为独立 EXE，然后与测试数据合并
"""
import os
import sys
import json
import shutil
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path

# 路径配置
ROOT_DIR = Path(__file__).parent.parent.parent
ENGINE_DIR = ROOT_DIR / "test_engine"
SERVER_DIR = ROOT_DIR / "python-server"
OUTPUT_DIR = ROOT_DIR / "exports"


def build_exe_agent():
    """使用 PyInstaller 打包 Agent 为 EXE"""
    print("[1/4] 正在打包 Agent 为 EXE...")

    agent_dir = ENGINE_DIR / "agent"
    spec_file = agent_dir / "agent_runner.spec"

    # 如果没有 spec 文件，使用命令行参数
    if not spec_file.exists():
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onedir",
            "--name", "QCC_Test_Agent",
            "--add-data", f"{ENGINE_DIR / 'core'};core",
            "--add-data", f"{ENGINE_DIR / 'script_registry.json'};.",
            "--add-data", f"{ENGINE_DIR / 'scripts'};scripts",
            "--hidden-import", "psutil",
            "--hidden-import", "tkinter",
            "--noconfirm",
            "--clean",
            "--distpath", str(ENGINE_DIR / "dist"),
            "--workpath", str(ENGINE_DIR / "build"),
            str(agent_dir / "agent_runner.py")
        ]
    else:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--distpath", str(ENGINE_DIR / "dist"),
            "--workpath", str(ENGINE_DIR / "build"),
            "--noconfirm",
            str(spec_file)
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(agent_dir))

    if result.returncode != 0:
        print(f"打包失败: {result.stderr}")
        return None

    exe_path = ENGINE_DIR / "dist" / "QCC_Test_Agent" / "QCC_Test_Agent.exe"
    if exe_path.exists():
        print(f"打包成功: {exe_path}")
        return ENGINE_DIR / "dist" / "QCC_Test_Agent"
    else:
        print("打包失败: 未找到生成的 EXE")
        return None


def create_offline_package(exe_dir: Path, project_code: str = None):
    """创建完整的离线测试包"""
    print("[2/4] 正在创建离线测试包...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    code = project_code or "Offline"
    package_name = f"QCC_Agent_{code}_{timestamp}"

    # 创建临时目录
    temp_dir = OUTPUT_DIR / package_name
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    # 复制 EXE 及依赖
    if exe_dir and exe_dir.exists():
        print("  复制 Agent EXE...")
        shutil.copytree(exe_dir, temp_dir / "QCC_Test_Agent")

    # 创建测试数据目录
    data_dir = temp_dir / "test_data"
    data_dir.mkdir()

    # 创建示例测试数据
    sample_data = {
        "manifest.json": {
            "project_code": code,
            "generated_at": datetime.now().isoformat(),
            "agent_version": "1.1.0",
            "package_type": "offline_exe"
        },
        "test_plan.json": [],
        "config.json": {},
        "script_mapping.json": []
    }

    for filename, data in sample_data.items():
        with open(data_dir / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # 创建启动说明
    readme = f"""QCC 离线测试工具包
================================

版本: 1.1.0
构建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

一、目录结构
------------
{package_name}/
├── QCC_Test_Agent/          Agent 程序目录
│   ├── QCC_Test_Agent.exe   主程序（双击启动）
│   ├── _internal/           依赖文件
│   └── ...
├── test_data/               测试数据目录
│   ├── manifest.json        项目信息
│   ├── test_plan.json       测试计划
│   ├── config.json          设备配置
│   └── script_mapping.json  脚本映射
├── README.txt               本说明文件
└── 启动测试.bat             快速启动脚本

二、使用方法
------------
方式一：使用启动脚本（推荐）
    双击 "启动测试.bat" 文件

方式二：直接启动 EXE
    双击 "QCC_Test_Agent/QCC_Test_Agent.exe"
    然后在程序中加载 test_data 目录

三、环境要求
------------
- Windows 10/11 64位
- 无需安装 Python 环境
- 管理员权限（S3/S4/重启测试需要）

四、测试流程
------------
1. 启动 Agent 程序
2. 加载测试数据（如有多个项目）
3. 系统自动采集设备信息
4. 逐项执行测试并填写结果
5. 导出结果包
6. 上传到 QCC 平台归档

五、常见问题
------------
Q: 启动时提示缺少 DLL
A: 安装 Visual C++ Redistributable

Q: 无法读取测试数据
A: 确保 test_data 目录与 EXE 在同一级

Q: 权限不足
A: 右键 -> 以管理员身份运行

六、技术支持
------------
如有问题，请联系测试团队。
"""
    with open(temp_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme)

    # 创建启动脚本
    start_bat = f"""@echo off
chcp 65001 >nul
echo ========================================
echo   QCC 离线测试工具包
echo   版本: 1.1.0
echo ========================================
echo.

echo [1/2] 检查环境...
if not exist "QCC_Test_Agent\\QCC_Test_Agent.exe" (
    echo [错误] 未找到 Agent 程序
    echo 请确保目录结构完整
    pause
    exit /b 1
)

echo [OK] 环境检查通过
echo.

echo [2/2] 启动 Agent...
start "" "QCC_Test_Agent\\QCC_Test_Agent.exe"

echo [OK] Agent 已启动
echo.
echo 提示: Agent 启动后会自动加载 test_data 目录
echo.
pause
"""
    with open(temp_dir / "启动测试.bat", "w", encoding="utf-8") as f:
        f.write(start_bat)

    print(f"  离线包目录: {temp_dir}")
    return temp_dir


def create_zip_package(package_dir: Path):
    """打包为 ZIP 文件"""
    print("[3/4] 正在打包为 ZIP...")

    zip_path = OUTPUT_DIR / f"{package_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                file_path = Path(root) / file
                arc_name = file_path.relative_to(package_dir.parent)
                zf.write(file_path, arc_name)

    # 计算大小
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  ZIP 文件: {zip_path}")
    print(f"  文件大小: {size_mb:.1f} MB")

    return zip_path


def cleanup_temp_files():
    """清理临时文件"""
    print("[4/4] 清理临时文件...")
    build_dir = ENGINE_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)


def main():
    """主流程"""
    print("=" * 60)
    print("QCC 离线测试工具包构建工具")
    print("=" * 60)
    print()

    # 确保输出目录存在
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. 打包 EXE
    exe_dir = build_exe_agent()
    if not exe_dir:
        print("EXE 打包失败，将创建仅脚本版本...")
        exe_dir = None

    # 2. 创建离线包
    package_dir = create_offline_package(exe_dir, "Offline")

    # 3. 打包 ZIP
    zip_path = create_zip_package(package_dir)

    # 4. 清理
    cleanup_temp_files()

    print()
    print("=" * 60)
    print("构建完成!")
    print(f"输出文件: {zip_path}")
    print(f"文件大小: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    print("=" * 60)

    return str(zip_path)


if __name__ == "__main__":
    main()
