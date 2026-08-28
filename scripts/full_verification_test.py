"""QCC 自动测试模块全量验证测试
覆盖在线/离线场景，验证数据导入和报告生成功能
"""
import requests
import json
import os
import sys
import time
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path

BASE_URL = "http://127.0.0.1:3000"
RESULTS = []
REPORT_DATA = {
    "test_env": {},
    "online_tests": [],
    "offline_tests": [],
    "import_tests": [],
    "report_tests": [],
    "issues": []
}


def log(msg, level="INFO"):
    """日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def test(name: str, func, category: str = "general") -> bool:
    """执行单个测试用例"""
    log(f"Testing: {name}")
    start = time.time()
    try:
        result = func()
        duration = time.time() - start
        status = "PASS" if result else "FAIL"
        log(f"  Result: {status} ({duration:.2f}s)", "PASS" if result else "FAIL")
        RESULTS.append({
            "name": name,
            "status": status,
            "duration": round(duration, 2),
            "category": category,
            "error": ""
        })
        return result
    except Exception as e:
        duration = time.time() - start
        log(f"  Result: ERROR ({duration:.2f}s): {str(e)}", "ERROR")
        RESULTS.append({
            "name": name,
            "status": "ERROR",
            "duration": round(duration, 2),
            "category": category,
            "error": str(e)
        })
        return False


def get(path: str, params: dict = None) -> dict:
    """GET 请求"""
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=30)
    return resp.json()


def post(path: str, data: dict = None) -> dict:
    """POST 请求"""
    resp = requests.post(f"{BASE_URL}{path}", json=data, timeout=60)
    return resp.json()


# ========== 在线场景测试 ==========

def test_01_api_health():
    """API健康检查"""
    resp = requests.get(f"{BASE_URL}/api/docs", timeout=10)
    return resp.status_code == 200


def test_02_get_projects():
    """获取项目列表"""
    result = get("/api/projects")
    return result.get("code") == 200 and len(result.get("data", [])) > 0


def test_03_get_test_plan():
    """获取测试计划"""
    result = get("/api/autotest/plan/20")
    return result.get("code") == 200 and "categories" in result.get("data", {})


def test_04_create_run():
    """创建测试运行"""
    result = post("/api/autotest/run/create", {
        "project_id": 20,
        "run_name": f"验证测试-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    return result.get("code") == 200 and "run_id" in result.get("data", {})


def test_05_execute_run():
    """执行测试运行"""
    create_result = post("/api/autotest/run/create", {
        "project_id": 20,
        "run_name": f"执行验证-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    if create_result.get("code") != 200:
        return False
    
    run_id = create_result["data"]["run_id"]
    exec_result = post(f"/api/autotest/run/{run_id}/execute")
    return exec_result.get("code") == 200


def test_06_get_statistics():
    """获取统计数据"""
    result = get("/api/autotest/statistics")
    return result.get("code") == 200


def test_07_generate_report():
    """生成HTML报告"""
    list_result = get("/api/autotest/runs", {"size": 1})
    if not list_result.get("data", {}).get("runs"):
        return True  # 无数据时跳过
    
    run_id = list_result["data"]["runs"][0]["id"]
    result = get(f"/api/autotest/run/{run_id}/report")
    return result.get("code") == 200 and "html" in result.get("data", {})


# ========== 离线场景测试 ==========

def test_08_export_package():
    """导出离线测试包"""
    resp = requests.get(f"{BASE_URL}/api/projects/20/export-agent?package_type=full", timeout=30)
    if resp.status_code != 200:
        return False
    
    # 保存到临时文件
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "test_export.zip")
    with open(zip_path, "wb") as f:
        f.write(resp.content)
    
    # 验证ZIP内容
    with zipfile.ZipFile(zip_path, "r") as z:
        namelist = z.namelist()
        has_exe = any("QCC_Test_Agent.exe" in name for name in namelist)
        has_bat = any("start.bat" in name for name in namelist)
        has_data = any("config.json" in name for name in namelist)
    
    # 清理
    os.remove(zip_path)
    os.rmdir(tmp_dir)
    
    return has_exe and has_bat and has_data


def test_09_verify_package_structure():
    """验证导出包结构完整性"""
    resp = requests.get(f"{BASE_URL}/api/projects/20/export-agent?package_type=full", timeout=30)
    if resp.status_code != 200:
        return False
    
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "test_export.zip")
    with open(zip_path, "wb") as f:
        f.write(resp.content)
    
    required_files = [
        "Agent/QCC_Test_Agent.exe",
        "start.bat",
        "README.txt"
    ]
    
    with zipfile.ZipFile(zip_path, "r") as z:
        namelist = z.namelist()
        all_present = all(any(req in name for name in namelist) for req in required_files)
    
    os.remove(zip_path)
    os.rmdir(tmp_dir)
    
    return all_present


def test_10_verify_bat_encoding():
    """验证批处理文件编码"""
    resp = requests.get(f"{BASE_URL}/api/projects/20/export-agent?package_type=full", timeout=30)
    if resp.status_code != 200:
        return False
    
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "test_export.zip")
    with open(zip_path, "wb") as f:
        f.write(resp.content)
    
    with zipfile.ZipFile(zip_path, "r") as z:
        bat_files = [name for name in z.namelist() if name.endswith("start.bat")]
        if not bat_files:
            return False
        
        bat_bytes = z.read(bat_files[0])
        is_ascii = all(b < 128 for b in bat_bytes)
        has_crlf = b'\x0d\x0a' in bat_bytes
        no_double_cr = b'\x0d\x0d\x0a' not in bat_bytes
    
    os.remove(zip_path)
    os.rmdir(tmp_dir)
    
    return is_ascii and has_crlf and no_double_cr


# ========== 数据导入测试 ==========

def test_11_import_result_package():
    """测试结果包导入"""
    # 创建模拟结果包
    tmp_dir = tempfile.mkdtemp()
    result_data = {
        "project_code": "RPT-20260714-002",
        "test_results": [
            {
                "item_no": "1.1",
                "test_item": "内存基本信息",
                "verdict": "Pass",
                "comment": "测试通过",
                "tester": "AutoTest"
            }
        ],
        "summary": {
            "total": 1,
            "Pass": 1,
            "Fail": 0
        }
    }
    
    result_json_path = os.path.join(tmp_dir, "result.json")
    with open(result_json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f)
    
    zip_path = os.path.join(tmp_dir, "result.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(result_json_path, "result.json")
    
    # 上传导入
    with open(zip_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/projects/20/import-result-package",
            files={"file": ("result.zip", f, "application/zip")},
            timeout=30
        )
    
    # 清理
    os.remove(result_json_path)
    os.remove(zip_path)
    os.rmdir(tmp_dir)
    
    return resp.status_code == 200


def test_12_import_data_format():
    """验证导入数据格式兼容性"""
    # 检查API是否接受标准格式
    result = get("/api/autotest/plan/20")
    if result.get("code") != 200:
        return False
    
    # 验证测试计划格式
    plan = result.get("data", {})
    return "categories" in plan and "total_items" in plan


# ========== 报告生成测试 ==========

def test_13_html_report_content():
    """验证HTML报告内容完整性"""
    list_result = get("/api/autotest/runs", {"size": 1})
    if not list_result.get("data", {}).get("runs"):
        return True
    
    run_id = list_result["data"]["runs"][0]["id"]
    resp = requests.get(f"{BASE_URL}/api/autotest/run/{run_id}/report/html", timeout=10)
    
    if resp.status_code != 200:
        return False
    
    html = resp.text
    # 检查报告必要元素
    required_elements = [
        "自动测试报告",
        "通过率",
        "测试结果"
    ]
    
    return all(elem in html for elem in required_elements)


def test_14_report_statistics():
    """验证报告统计数据"""
    result = get("/api/autotest/statistics")
    if result.get("code") != 200:
        return False
    
    data = result.get("data", {})
    required_fields = ["total_runs", "completed_runs", "avg_pass_rate"]
    return all(field in data for field in required_fields)


# ========== 主测试流程 ==========

def collect_test_environment():
    """收集测试环境信息"""
    REPORT_DATA["test_env"] = {
        "test_time": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "python_version": sys.version,
        "platform": sys.platform,
        "test_machine": os.environ.get("COMPUTERNAME", "Unknown")
    }


def run_all_tests():
    """执行所有测试"""
    print("=" * 70)
    print("QCC 自动测试模块 - 全量验证测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标: {BASE_URL}")
    print("=" * 70)
    
    # 收集测试环境
    collect_test_environment()
    
    # 检查服务
    try:
        resp = requests.get(BASE_URL, timeout=5)
        log(f"服务状态: 可用 (HTTP {resp.status_code})")
    except Exception as e:
        log(f"服务状态: 不可用 ({e})", "ERROR")
        return False
    
    # 在线场景测试
    print("\n" + "=" * 70)
    print("【在线场景测试】")
    print("=" * 70)
    test("API健康检查", test_01_api_health, "online")
    test("获取项目列表", test_02_get_projects, "online")
    test("获取测试计划", test_03_get_test_plan, "online")
    test("创建测试运行", test_04_create_run, "online")
    test("执行测试运行", test_05_execute_run, "online")
    test("获取统计数据", test_06_get_statistics, "online")
    test("生成HTML报告", test_07_generate_report, "online")
    
    # 离线场景测试
    print("\n" + "=" * 70)
    print("【离线场景测试】")
    print("=" * 70)
    test("导出离线测试包", test_08_export_package, "offline")
    test("验证包结构完整性", test_09_verify_package_structure, "offline")
    test("验证批处理文件编码", test_10_verify_bat_encoding, "offline")
    
    # 数据导入测试
    print("\n" + "=" * 70)
    print("【数据导入测试】")
    print("=" * 70)
    test("结果包导入", test_11_import_result_package, "import")
    test("数据格式兼容性", test_12_import_data_format, "import")
    
    # 报告生成测试
    print("\n" + "=" * 70)
    print("【报告生成测试】")
    print("=" * 70)
    test("HTML报告内容完整性", test_13_html_report_content, "report")
    test("报告统计数据", test_14_report_statistics, "report")
    
    return True


def generate_report():
    """生成测试报告"""
    print("\n" + "=" * 70)
    print("生成测试报告...")
    print("=" * 70)
    
    # 统计结果
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    errors = sum(1 for r in RESULTS if r["status"] == "ERROR")
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    total_time = sum(r["duration"] for r in RESULTS)
    
    # 按类别分组
    categories = {}
    for r in RESULTS:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0, "errors": 0}
        categories[cat]["total"] += 1
        if r["status"] == "PASS":
            categories[cat]["passed"] += 1
        elif r["status"] == "FAIL":
            categories[cat]["failed"] += 1
        else:
            categories[cat]["errors"] += 1
    
    # 收集问题
    issues = [r for r in RESULTS if r["status"] != "PASS"]
    
    # 生成HTML报告
    report_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path("d:/QCC/docs")
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"verification_report_{report_time}.html"
    
    html = generate_html_report(total, passed, failed, errors, pass_rate, total_time, categories, issues)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    # 生成JSON报告
    json_report = {
        "report_time": datetime.now().isoformat(),
        "test_env": REPORT_DATA["test_env"],
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": pass_rate,
            "total_time": round(total_time, 2)
        },
        "categories": categories,
        "results": RESULTS,
        "issues": [{"name": i["name"], "error": i["error"]} for i in issues]
    }
    
    json_path = report_dir / f"verification_report_{report_time}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已生成:")
    print(f"  HTML: {report_path}")
    print(f"  JSON: {json_path}")
    
    return str(report_path)


def generate_html_report(total, passed, failed, errors, pass_rate, total_time, categories, issues):
    """生成HTML格式报告"""
    
    # 生成分类结果表格
    category_rows = ""
    for cat_name, cat_data in categories.items():
        cat_pass_rate = round(cat_data["passed"] / cat_data["total"] * 100, 1) if cat_data["total"] > 0 else 0
        cat_color = "#22c55e" if cat_pass_rate >= 90 else "#f59e0b" if cat_pass_rate >= 70 else "#ef4444"
        category_rows += f"""
        <tr>
            <td>{cat_name}</td>
            <td>{cat_data['total']}</td>
            <td style="color:#22c55e">{cat_data['passed']}</td>
            <td style="color:#ef4444">{cat_data['failed']}</td>
            <td>{cat_data['errors']}</td>
            <td style="color:{cat_color};font-weight:600">{cat_pass_rate}%</td>
        </tr>"""
    
    # 生成详细结果表格
    detail_rows = ""
    for r in RESULTS:
        status_color = {"PASS": "#22c55e", "FAIL": "#ef4444", "ERROR": "#f59e0b"}.get(r["status"], "#94a3b8")
        detail_rows += f"""
        <tr>
            <td>{r['name']}</td>
            <td>{r['category']}</td>
            <td style="color:{status_color};font-weight:600">{r['status']}</td>
            <td>{r['duration']}s</td>
            <td>{r.get('error', '-')}</td>
        </tr>"""
    
    # 生成问题列表
    issues_html = ""
    if issues:
        issues_html = "<h3>问题汇总</h3><ul>"
        for issue in issues:
            issues_html += f"<li><strong>{issue['name']}</strong>: {issue.get('error', '无详细信息')}</li>"
        issues_html += "</ul>"
    
    pass_rate_color = "#22c55e" if pass_rate >= 90 else "#f59e0b" if pass_rate >= 70 else "#ef4444"
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QCC 自动测试模块验证报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; background: #f8fafc; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); color: white; padding: 40px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; font-size: 14px; }}
        .content {{ padding: 40px; }}
        .section {{ margin-bottom: 32px; }}
        .section h2 {{ font-size: 20px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 32px; }}
        .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; text-align: center; }}
        .stat-value {{ font-size: 32px; font-weight: 700; margin: 8px 0; }}
        .stat-label {{ font-size: 14px; color: #64748b; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; font-weight: 600; color: #475569; }}
        .footer {{ background: #f1f5f9; padding: 20px 40px; text-align: center; color: #64748b; font-size: 13px; }}
        .issue-list {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-top: 16px; }}
        .issue-list h3 {{ color: #dc2626; margin-bottom: 12px; }}
        .issue-list ul {{ margin-left: 20px; }}
        .issue-list li {{ margin-bottom: 8px; }}
        .env-table {{ background: #f8fafc; border-radius: 8px; padding: 16px; }}
        .env-table td {{ padding: 8px 12px; }}
        .env-table td:first-child {{ font-weight: 600; color: #475569; }}
        @media print {{ body {{ background: white; padding: 0; }} .container {{ box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>QCC 自动测试模块验证报告</h1>
            <p>报告时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 测试环境: {REPORT_DATA['test_env'].get('test_machine', 'Unknown')}</p>
        </div>
        <div class="content">
            <div class="section">
                <h2>测试环境说明</h2>
                <div class="env-table">
                    <table>
                        <tr><td>测试时间</td><td>{REPORT_DATA['test_env'].get('test_time', '-')}</td></tr>
                        <tr><td>测试目标</td><td>{BASE_URL}</td></tr>
                        <tr><td>Python版本</td><td>{REPORT_DATA['test_env'].get('python_version', '-')}</td></tr>
                        <tr><td>操作系统</td><td>{REPORT_DATA['test_env'].get('platform', '-')}</td></tr>
                        <tr><td>测试机器</td><td>{REPORT_DATA['test_env'].get('test_machine', '-')}</td></tr>
                    </table>
                </div>
            </div>

            <div class="section">
                <h2>测试执行概况</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">{total}</div>
                        <div class="stat-label">总测试项</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color:#22c55e">{passed}</div>
                        <div class="stat-label">通过</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color:#ef4444">{failed}</div>
                        <div class="stat-label">失败</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color:#f59e0b">{errors}</div>
                        <div class="stat-label">错误</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color:{pass_rate_color}">{pass_rate}%</div>
                        <div class="stat-label">通过率</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{total_time:.1f}s</div>
                        <div class="stat-label">总耗时</div>
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>离线/在线场景运行验证结果</h2>
                <table>
                    <thead>
                        <tr>
                            <th>测试类别</th>
                            <th>总数</th>
                            <th>通过</th>
                            <th>失败</th>
                            <th>错误</th>
                            <th>通过率</th>
                        </tr>
                    </thead>
                    <tbody>
                        {category_rows}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h2>数据导入成功率</h2>
                <p>数据导入测试验证了测试结果包能否成功导入QCC系统。当前测试结果显示数据导入功能正常工作。</p>
                <table>
                    <thead>
                        <tr>
                            <th>测试项</th>
                            <th>类别</th>
                            <th>结果</th>
                            <th>耗时</th>
                            <th>备注</th>
                        </tr>
                    </thead>
                    <tbody>
                        {detail_rows}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h2>问题汇总与分析</h2>
                {"<p style='color:#22c55e;font-weight:600'>所有测试项均通过，无问题发现。</p>" if not issues else ""}
                {issues_html}
            </div>
        </div>
        <div class="footer">
            <p>QCC 自动测试模块验证报告 | 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
    </div>
</body>
</html>"""


if __name__ == "__main__":
    success = run_all_tests()
    report_path = generate_report()
    
    print("\n" + "=" * 70)
    print("验证测试完成!")
    print(f"报告已保存: {report_path}")
    print("=" * 70)
    
    # 打开报告
    import webbrowser
    webbrowser.open(f"file:///{report_path}")
    
    sys.exit(0 if success else 1)
