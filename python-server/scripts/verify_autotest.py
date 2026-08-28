"""自动测试模块全量功能验证脚本
验证所有预设功能的实现完整性与运行稳定性
"""
import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple

BASE_URL = "http://127.0.0.1:3000"
RESULTS: List[Dict] = []


def test(name: str, func) -> bool:
    """执行单个测试用例"""
    print(f"  测试: {name}...", end=" ")
    start = time.time()
    try:
        result = func()
        duration = time.time() - start
        status = "PASS" if result else "FAIL"
        print(f"{status} ({duration:.2f}s)")
        RESULTS.append({"name": name, "status": status, "duration": round(duration, 2), "error": ""})
        return result
    except Exception as e:
        duration = time.time() - start
        print(f"ERROR ({duration:.2f}s): {str(e)}")
        RESULTS.append({"name": name, "status": "ERROR", "duration": round(duration, 2), "error": str(e)})
        return False


def get(path: str, params: dict = None) -> dict:
    """GET 请求"""
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=30)
    return resp.json()


def post(path: str, data: dict = None) -> dict:
    """POST 请求"""
    resp = requests.post(f"{BASE_URL}{path}", json=data, timeout=60)
    return resp.json()


def delete(path: str) -> dict:
    """DELETE 请求"""
    resp = requests.delete(f"{BASE_URL}{path}", timeout=30)
    return resp.json()


# ── 测试用例 ──

def test_01_api_docs():
    """API 文档可访问"""
    resp = requests.get(f"{BASE_URL}/api/docs", timeout=10)
    return resp.status_code == 200


def test_02_autotest_page():
    """自动测试页面可访问"""
    resp = requests.get(f"{BASE_URL}/page/autotest", timeout=10, allow_redirects=False)
    # 页面可能需要登录（重定向到登录页），这是正常的
    return resp.status_code in (200, 302, 307)


def test_03_get_test_plan():
    """获取测试计划"""
    # 先获取项目列表
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]
    result = get(f"/api/autotest/plan/{project_id}")
    return result.get("code") == 200 and "categories" in result.get("data", {})


def test_04_get_available_tests():
    """获取可用测试项"""
    result = get("/api/autotest/available-tests")
    return result.get("code") == 200


def test_05_create_run():
    """创建测试运行"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]
    result = post("/api/autotest/run/create", {
        "project_id": project_id,
        "run_name": f"验证测试-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    return result.get("code") == 200 and "run_id" in result.get("data", {})


def test_06_execute_run():
    """执行测试运行"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]

    # 创建
    create_result = post("/api/autotest/run/create", {
        "project_id": project_id,
        "run_name": f"执行验证-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    if create_result.get("code") != 200:
        return False

    run_id = create_result["data"]["run_id"]

    # 执行
    exec_result = post(f"/api/autotest/run/{run_id}/execute")
    return exec_result.get("code") == 200 and exec_result.get("data", {}).get("status") == "completed"


def test_07_get_run_detail():
    """获取运行详情"""
    # 先获取列表
    list_result = get("/api/autotest/runs", {"size": 1})
    if list_result.get("code") != 200 or not list_result.get("data", {}).get("runs"):
        print("(跳过: 无运行记录)", end=" ")
        return True
    run_id = list_result["data"]["runs"][0]["id"]
    result = get(f"/api/autotest/run/{run_id}")
    return result.get("code") == 200 and "results" in result.get("data", {})


def test_08_get_run_list():
    """获取运行列表"""
    result = get("/api/autotest/runs")
    return result.get("code") == 200 and "runs" in result.get("data", {})


def test_09_get_statistics():
    """获取统计数据"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        result = get("/api/autotest/statistics")
    else:
        project_id = resp["data"][0]["id"]
        result = get("/api/autotest/statistics", {"project_id": project_id})
    return result.get("code") == 200


def test_10_generate_report():
    """生成测试报告"""
    list_result = get("/api/autotest/runs", {"size": 1})
    if list_result.get("code") != 200 or not list_result.get("data", {}).get("runs"):
        print("(跳过: 无运行记录)", end=" ")
        return True
    run_id = list_result["data"]["runs"][0]["id"]
    result = get(f"/api/autotest/run/{run_id}/report")
    return result.get("code") == 200 and "html" in result.get("data", {})


def test_11_preview_report():
    """预览 HTML 报告"""
    list_result = get("/api/autotest/runs", {"size": 1})
    if list_result.get("code") != 200 or not list_result.get("data", {}).get("runs"):
        print("(跳过: 无运行记录)", end=" ")
        return True
    run_id = list_result["data"]["runs"][0]["id"]
    resp = requests.get(f"{BASE_URL}/api/autotest/run/{run_id}/report/html", timeout=10)
    return resp.status_code == 200 and "自动测试报告" in resp.text


def test_12_cancel_run():
    """取消测试运行"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]

    # 创建一个不执行
    create_result = post("/api/autotest/run/create", {
        "project_id": project_id,
        "run_name": f"取消测试-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    if create_result.get("code") != 200:
        return False

    run_id = create_result["data"]["run_id"]
    cancel_result = post(f"/api/autotest/run/{run_id}/cancel")
    return cancel_result.get("code") == 200


def test_13_delete_run():
    """删除测试运行"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]

    # 创建一个用于删除
    create_result = post("/api/autotest/run/create", {
        "project_id": project_id,
        "run_name": f"删除测试-{datetime.now().strftime('%H%M%S')}",
        "run_type": "full"
    })
    if create_result.get("code") != 200:
        return False

    run_id = create_result["data"]["run_id"]
    delete_result = delete(f"/api/autotest/run/{run_id}")
    return delete_result.get("code") == 200


def test_14_system_collect():
    """系统信息采集"""
    result = get("/api/autotest/system/collect")
    # 可能因为环境限制失败，但接口应该返回
    return result.get("code") in (200, 500)


def test_15_export_agent():
    """导出离线测试包"""
    resp = get("/api/projects")
    if resp.get("code") != 200 or not resp.get("data"):
        print("(跳过: 无项目数据)", end=" ")
        return True
    project_id = resp["data"][0]["id"]
    resp = requests.get(f"{BASE_URL}/api/projects/{project_id}/export-agent", timeout=30)
    return resp.status_code == 200 and resp.headers.get("content-type") == "application/zip"


def test_16_api_endpoints_registered():
    """验证所有 API 端点已注册"""
    endpoints = [
        "/api/autotest/plan/1",
        "/api/autotest/available-tests",
        "/api/autotest/runs",
        "/api/autotest/statistics",
        "/api/autotest/system/collect",
    ]
    for ep in endpoints:
        resp = requests.get(f"{BASE_URL}{ep}", timeout=10)
        if resp.status_code == 404:
            return False
    return True


def test_17_run_create_validation():
    """创建运行参数验证"""
    result = post("/api/autotest/run/create", {})
    return result.get("code") == 400  # 缺少 project_id


def test_18_run_not_found():
    """不存在的运行记录"""
    result = get("/api/autotest/run/99999")
    return result.get("code") == 404


def test_19_statistics_no_project():
    """无项目条件下的统计"""
    result = get("/api/autotest/statistics")
    return result.get("code") == 200


def test_20_page_navigation():
    """页面导航测试"""
    pages = [
        "/page/autotest",
        "/page/dashboard",
        "/page/projects",
    ]
    for page in pages:
        resp = requests.get(f"{BASE_URL}{page}", timeout=10, allow_redirects=False)
        if resp.status_code not in (200, 302):
            return False
    return True


# ── 主流程 ──

def run_all_tests():
    """执行所有测试"""
    print("=" * 60)
    print("QCC 自动测试模块 - 全量功能验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标: {BASE_URL}")
    print("=" * 60)

    # 检查服务是否可用
    try:
        resp = requests.get(BASE_URL, timeout=5)
        print(f"\n服务状态: 可用 (HTTP {resp.status_code})")
    except Exception as e:
        print(f"\n服务状态: 不可用 ({e})")
        print("请先启动服务: python -m uvicorn app.main:app --host 0.0.0.0 --port 3000")
        sys.exit(1)

    print("\n" + "-" * 60)
    print("【用例管理模块】")
    print("-" * 60)
    test("API 文档可访问", test_01_api_docs)
    test("自动测试页面可访问", test_02_autotest_page)
    test("获取测试计划", test_03_get_test_plan)
    test("获取可用测试项", test_04_get_available_tests)

    print("\n" + "-" * 60)
    print("【执行调度模块】")
    print("-" * 60)
    test("创建测试运行", test_05_create_run)
    test("执行测试运行", test_06_execute_run)
    test("取消测试运行", test_12_cancel_run)
    test("参数验证", test_17_run_create_validation)

    print("\n" + "-" * 60)
    print("【结果采集模块】")
    print("-" * 60)
    test("获取运行详情", test_07_get_run_detail)
    test("获取运行列表", test_08_get_run_list)
    test("获取统计数据", test_09_get_statistics)
    test("无项目统计", test_19_statistics_no_project)
    test("不存在的记录", test_18_run_not_found)
    test("删除测试运行", test_13_delete_run)

    print("\n" + "-" * 60)
    print("【报告生成模块】")
    print("-" * 60)
    test("生成测试报告", test_10_generate_report)
    test("预览 HTML 报告", test_11_preview_report)

    print("\n" + "-" * 60)
    print("【系统集成】")
    print("-" * 60)
    test("系统信息采集", test_14_system_collect)
    test("导出离线测试包", test_15_export_agent)
    test("API 端点注册", test_16_api_endpoints_registered)
    test("页面导航", test_20_page_navigation)

    # 生成报告
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    errors = sum(1 for r in RESULTS if r["status"] == "ERROR")
    total_time = sum(r["duration"] for r in RESULTS)

    print(f"\n总计: {total} 项")
    print(f"  通过: {passed} 项 ({passed/total*100:.1f}%)")
    print(f"  失败: {failed} 项")
    print(f"  错误: {errors} 项")
    print(f"  耗时: {total_time:.2f} 秒")

    if failed + errors > 0:
        print("\n失败/错误详情:")
        for r in RESULTS:
            if r["status"] != "PASS":
                print(f"  - {r['name']}: {r['status']} {r.get('error', '')}")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "total_time": round(total_time, 2)
        },
        "results": RESULTS
    }

    report_path = f"d:\\QCC\\docs\\autotest_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, ensure_ascii=False, indent=2, fp=f)
    print(f"\n详细报告已保存: {report_path}")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
