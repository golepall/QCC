"""构建 QCC 离线测试工作台安装程序"""
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# 路径配置
ROOT_DIR = Path(__file__).parent.parent
INSTALLER_DIR = ROOT_DIR / "installer"
OUTPUT_DIR = INSTALLER_DIR / "output"
AGENT_DIR = ROOT_DIR / "test_engine" / "QCC_Test_Agent_Portable" / "Agent"

# Inno Setup 路径（默认安装位置）
INNO_SETUP_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
]


def find_inno_setup():
    """查找 Inno Setup 编译器"""
    for path in INNO_SETUP_PATHS:
        if os.path.exists(path):
            return path
    return None


def check_prerequisites():
    """检查构建前置条件"""
    print("检查构建环境...")
    
    # 检查 Inno Setup
    iscc_path = find_inno_setup()
    if not iscc_path:
        print("[错误] 未找到 Inno Setup")
        print("请从以下地址下载安装：")
        print("  https://jrsoftware.org/isinfo.php")
        return None
    print(f"  Inno Setup: {iscc_path}")
    
    # 检查 Agent 文件
    exe_path = AGENT_DIR / "QCC_Test_Agent.exe"
    if not exe_path.exists():
        print(f"[错误] 未找到 Agent: {exe_path}")
        return None
    print(f"  Agent EXE: {exe_path}")
    
    # 检查图标
    icon_path = INSTALLER_DIR / "icon.ico"
    if not icon_path.exists():
        print(f"[警告] 未找到图标文件，将使用默认图标")
    
    print("  环境检查通过")
    return iscc_path


def build_installer(iscc_path: str):
    """构建安装程序"""
    print("\n开始构建安装程序...")
    
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 构建命令
    iss_file = INSTALLER_DIR / "QCC_Test_Agent.iss"
    cmd = [
        iscc_path,
        str(iss_file),
        f"/O{OUTPUT_DIR}",
        "/Q"  # 安静模式
    ]
    
    print(f"  执行: {' '.join(cmd)}")
    
    # 执行构建
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"\n[错误] 构建失败！")
        print(result.stderr)
        return None
    
    # 查找输出文件
    for file in OUTPUT_DIR.glob("*.exe"):
        if "Setup" in file.name:
            size_mb = file.stat().st_size / 1024 / 1024
            print(f"\n[成功] 安装程序已生成：")
            print(f"  文件: {file}")
            print(f"  大小: {size_mb:.1f} MB")
            return str(file)
    
    print("[错误] 未找到生成的安装程序")
    return None


def create_readme():
    """创建安装说明"""
    readme_content = f"""QCC 离线测试工作台 - 安装说明
================================

版本: 1.1.0
构建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

一、安装步骤
-----------
1. 双击 QCC_Test_Agent_Setup_1.1.0.exe
2. 按照安装向导提示完成安装
3. 安装完成后，桌面会创建快捷方式

二、安装选项
-----------
- 安装位置: 默认 C:\\Program Files\\QCC_Test_Agent
- 桌面快捷方式: 可选
- 快速启动栏: 可选

三、使用方法
-----------
1. 双击桌面快捷方式启动程序
2. 将测试包中的 TestData 文件夹复制到程序目录
3. 程序会自动加载测试数据
4. 执行测试并导出结果

四、卸载方法
-----------
1. 从开始菜单找到卸载程序
2. 或从控制面板 -> 程序和功能中卸载

五、系统要求
-----------
- Windows 10/11 (64位)
- 管理员权限（安装时需要）
- 100MB 可用磁盘空间

六、常见问题
-----------
Q: 安装时提示权限不足？
A: 右键安装程序 -> 以管理员身份运行

Q: 如何更新测试计划？
A: 将新的测试包中的 TestData 文件夹复制到安装目录

Q: 如何导入结果到平台？
A: 程序导出的 ZIP 文件可直接在 QCC 平台导入

---
QCC 测试团队
"""
    
    readme_path = INSTALLER_DIR / "docs" / "INSTALL.txt"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"  安装说明: {readme_path}")


def main():
    """主流程"""
    print("=" * 60)
    print("QCC 离线测试工作台 - 安装程序构建工具")
    print("=" * 60)
    
    # 检查环境
    iscc_path = check_prerequisites()
    if not iscc_path:
        return False
    
    # 创建安装说明
    create_readme()
    
    # 构建安装程序
    output_file = build_installer(iscc_path)
    
    if output_file:
        print("\n" + "=" * 60)
        print("构建完成！")
        print(f"安装程序: {output_file}")
        print("=" * 60)
        return True
    else:
        print("\n构建失败！")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
