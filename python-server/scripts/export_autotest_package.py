"""自动测试工具包导出脚本
将 test_engine 和自动测试模块打包为独立可部署的工具包
"""
import os
import sys
import json
import zipfile
import shutil
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent
SERVER_DIR = ROOT_DIR / "python-server"
ENGINE_DIR = ROOT_DIR / "test_engine"
EXPORT_DIR = ROOT_DIR / "exports"


def create_export_package(version: str = "1.0.0"):
    """创建自动测试工具包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"QCC_AutoTest_v{version}_{timestamp}"
    export_path = EXPORT_DIR / package_name

    # 创建导出目录
    EXPORT_DIR.mkdir(exist_ok=True)
    if export_path.exists():
        shutil.rmtree(export_path)
    export_path.mkdir(parents=True)

    print(f"正在导出自动测试工具包: {package_name}")

    # 1. 复制测试引擎核心
    print("  复制测试引擎核心...")
    engine_dest = export_path / "test_engine"
    shutil.copytree(ENGINE_DIR, engine_dest, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', '.git', 'agent'
    ))

    # 2. 复制自动测试模块
    print("  复制自动测试模块...")
    autotest_dest = export_path / "autotest_module"
    autotest_dest.mkdir()

    # 复制路由
    routers_dir = autotest_dest / "routers"
    routers_dir.mkdir()
    for f in ["autotest.py", "agent.py", "remote.py"]:
        src = SERVER_DIR / "app" / "routers" / f
        if src.exists():
            shutil.copy2(src, routers_dir / f)

    # 复制服务
    services_dir = autotest_dest / "services"
    services_dir.mkdir()
    for f in ["autotest_service.py", "engine_service.py"]:
        src = SERVER_DIR / "app" / "services" / f
        if src.exists():
            shutil.copy2(src, services_dir / f)

    # 复制模型
    models_dir = autotest_dest / "models"
    models_dir.mkdir()
    for f in ["autotest.py", "project.py", "template.py", "management.py", "base.py"]:
        src = SERVER_DIR / "app" / "models" / f
        if src.exists():
            shutil.copy2(src, models_dir / f)

    # 复制前端模板
    templates_dir = autotest_dest / "templates"
    templates_dir.mkdir()
    src = SERVER_DIR / "templates" / "autotest" / "index.html"
    if src.exists():
        dest = templates_dir / "index.html"
        shutil.copy2(src, dest)

    # 3. 生成依赖清单
    print("  生成依赖清单...")
    requirements = generate_requirements()
    req_file = export_path / "requirements.txt"
    req_file.write_text(requirements, encoding="utf-8")

    # 4. 生成配置文件
    print("  生成配置文件...")
    config = generate_config()
    config_file = export_path / "config.json"
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. 生成部署脚本
    print("  生成部署脚本...")
    deploy_script = generate_deploy_script()
    deploy_file = export_path / "deploy.bat"
    deploy_file.write_text(deploy_script, encoding="utf-8")

    deploy_sh = generate_deploy_sh()
    deploy_sh_file = export_path / "deploy.sh"
    deploy_sh_file.write_text(deploy_sh, encoding="utf-8")

    # 6. 生成说明文档
    print("  生成说明文档...")
    readme = generate_readme(version)
    readme_file = export_path / "README.md"
    readme_file.write_text(readme, encoding="utf-8")

    # 7. 生成版本信息
    version_info = {
        "version": version,
        "build_time": datetime.now().isoformat(),
        "components": {
            "test_engine": "1.0.0",
            "autotest_module": "1.0.0",
            "api_version": "v1"
        },
        "python_requires": ">=3.11",
        "platform": ["windows", "linux", "macos"]
    }
    version_file = export_path / "version.json"
    version_file.write_text(json.dumps(version_info, ensure_ascii=False, indent=2), encoding="utf-8")

    # 8. 创建 ZIP 包
    print("  创建 ZIP 包...")
    zip_path = EXPORT_DIR / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(export_path):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(export_path.parent)
                zf.write(file_path, arcname)

    # 清理临时目录
    shutil.rmtree(export_path)

    print(f"\n导出完成!")
    print(f"  ZIP 包: {zip_path}")
    print(f"  大小: {zip_path.stat().st_size / 1024:.1f} KB")

    return str(zip_path)


def generate_requirements() -> str:
    """生成依赖清单"""
    return """# QCC AutoTest Tool - Python Dependencies
# Version: 1.0.0

# Core
fastapi>=0.115.0,<1.0.0
uvicorn[standard]>=0.30.0,<1.0.0

# Database
sqlalchemy[asyncio]>=2.0.35,<3.0.0
aiosqlite>=0.20.0,<1.0.0

# Auth
python-jose[cryptography]>=3.3.0,<4.0.0
passlib[bcrypt]>=1.7.4,<2.0.0

# Validation
pydantic>=2.9.0,<3.0.0
pydantic-settings>=2.5.0,<3.0.0
python-multipart>=0.0.12,<1.0.0

# Excel
openpyxl>=3.1.5,<4.0.0
xlrd>=2.0.0,<3.0.0

# SSH (for remote execution)
paramiko>=3.0.0,<4.0.0

# System Info
psutil>=5.9.0,<6.0.0

# Logging
structlog>=24.4.0,<25.0.0
"""


def generate_config() -> dict:
    """生成配置文件"""
    return {
        "app": {
            "name": "QCC AutoTest Tool",
            "version": "1.0.0",
            "debug": False
        },
        "server": {
            "host": "0.0.0.0",
            "port": 3000,
            "workers": 1
        },
        "database": {
            "url": "sqlite+aiosqlite:///./data/qcc_autotest.db",
            "echo": False
        },
        "engine": {
            "test_timeout": 30,
            "max_concurrent": 4,
            "collect_interval": 60
        },
        "paths": {
            "data_dir": "./data",
            "export_dir": "./exports",
            "scripts_dir": "./test_engine/scripts"
        }
    }


def generate_deploy_script() -> str:
    """生成 Windows 部署脚本"""
    return """@echo off
echo ========================================
echo QCC AutoTest Tool - Deployment Script
echo ========================================
echo.

REM Check Python version
python --version 2>NUL
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)

REM Create virtual environment
echo [1/4] Creating virtual environment...
python -m venv .venv
call .venv\\Scripts\\activate.bat

REM Install dependencies
echo [2/4] Installing dependencies...
pip install -r requirements.txt

REM Initialize database
echo [3/4] Initializing database...
if not exist data mkdir data
python -c "from app.models.base import Base; from app.dependencies import get_engine; import asyncio; asyncio.run(get_engine().run_sync(Base.metadata.create_all))"

REM Create admin user
echo [4/4] Creating admin user...
python scripts/create_admin.py

echo.
echo ========================================
echo Deployment completed!
echo Run 'start.bat' to start the server.
echo ========================================
pause
"""


def generate_deploy_sh() -> str:
    """生成 Linux/Mac 部署脚本"""
    return """#!/bin/bash
echo "========================================"
echo "QCC AutoTest Tool - Deployment Script"
echo "========================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.11+ from https://www.python.org/"
    exit 1
fi

# Create virtual environment
echo "[1/4] Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
echo "[2/4] Installing dependencies..."
pip install -r requirements.txt

# Initialize database
echo "[3/4] Initializing database..."
mkdir -p data
python -c "from app.models.base import Base; from app.dependencies import get_engine; import asyncio; asyncio.run(get_engine().run_sync(Base.metadata.create_all))"

# Create admin user
echo "[4/4] Creating admin user..."
python scripts/create_admin.py

echo ""
echo "========================================"
echo "Deployment completed!"
echo "Run './start.sh' to start the server."
echo "========================================"
"""


def generate_readme(version: str) -> str:
    """生成说明文档"""
    return f"""# QCC AutoTest Tool

版本: {version}
构建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 概述

QCC 自动测试工具是一个独立的测试执行和管理平台，支持：

- **用例管理**: 从项目模板自动生成测试计划
- **执行调度**: 在线创建和执行测试运行
- **结果采集**: 自动收集测试结果并持久化存储
- **报告生成**: 生成 HTML 格式的测试报告

## 系统要求

- Python 3.11+
- Windows / Linux / macOS
- 内存: 512MB+
- 磁盘: 100MB+

## 快速开始

### Windows

```cmd
deploy.bat
start.bat
```

### Linux / macOS

```bash
chmod +x deploy.sh start.sh
./deploy.sh
./start.sh
```

### 手动安装

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\\Scripts\\activate.bat  # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## 访问地址

启动后访问: http://localhost:3000

## API 文档

启动后访问: http://localhost:3000/api/docs

## 目录结构

```
QCC_AutoTest/
├── test_engine/          # 测试引擎核心
│   ├── core/            # 核心模块
│   │   ├── test_engine.py      # 测试引擎
│   │   ├── system_collector.py # 系统采集
│   │   ├── script_runner.py    # 脚本执行器
│   │   ├── perf_runner.py      # 性能测试
│   │   ├── stress_manager.py   # 压力测试
│   │   └── remote_executor.py  # 远程执行
│   └── scripts/         # 采集脚本
├── autotest_module/     # 自动测试模块
│   ├── routers/         # API 路由
│   ├── services/        # 业务服务
│   ├── models/          # 数据模型
│   └── templates/       # 前端模板
├── requirements.txt     # Python 依赖
├── config.json         # 配置文件
├── version.json        # 版本信息
├── deploy.bat          # Windows 部署脚本
├── deploy.sh           # Linux 部署脚本
└── README.md           # 本文件
```

## API 接口

### 测试计划
- `GET /api/autotest/plan/{{project_id}}` - 获取项目测试计划
- `GET /api/autotest/available-tests` - 获取可用测试项

### 执行调度
- `POST /api/autotest/run/create` - 创建测试运行
- `POST /api/autotest/run/{{run_id}}/execute` - 执行测试运行
- `POST /api/autotest/run/{{run_id}}/cancel` - 取消测试运行

### 结果采集
- `GET /api/autotest/runs` - 获取运行列表
- `GET /api/autotest/run/{{run_id}}` - 获取运行详情
- `GET /api/autotest/statistics` - 获取统计数据

### 报告生成
- `GET /api/autotest/run/{{run_id}}/report` - 获取报告数据
- `GET /api/autotest/run/{{run_id}}/report/html` - 预览 HTML 报告

### 系统采集
- `GET /api/autotest/system/collect` - 采集系统信息
- `POST /api/autotest/system/validate` - 验证设备配置

## 故障排除

### 端口被占用
修改 `config.json` 中的 `server.port` 配置

### 数据库错误
删除 `data/qcc_autotest.db` 重新运行部署脚本

### 依赖安装失败
确保使用 Python 3.11+，并尝试：
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

## 技术支持

如有问题，请联系开发团队。
"""


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
    create_export_package(version)
