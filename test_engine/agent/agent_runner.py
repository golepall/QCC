#!/usr/bin/env python3
"""
QCC 离线测试 Agent
读取 QCC 导出的测试包，在被测设备上完成：
1. 系统信息采集
2. 自动化测试执行
3. 人工测试结果填写
4. 标准结果包导出（manifest.json / result.json / system_info.json）
"""

import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Tuple

# 确保能导入 core 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.system_collector import SystemCollector
from core.runtime_env import get_gui_launcher_path, get_launcher_path, is_frozen_app
from core.stress_manager import StressManager
from core.test_engine import TestEngine

AGENT_VERSION = "1.1.0"
VALID_VERDICTS = ["NotTested", "Pass", "Fail", "NA", "Blocked", "Manual"]
LONG_TASK_TEMPLATES = [
    {
        "key": "s3_cycle",
        "task_type": "s3",
        "title": "S3 睡眠循环",
        "description": "用于记录睡眠恢复类测试的轮次、结果和失败证据。",
        "default_count": 20,
        "default_interval": 60,
        "requires_admin": True,
        "supports_resume": True,
        "supports_runtime": False,
        "supports_resume_workflow": True,
    },
    {
        "key": "s4_cycle",
        "task_type": "s4",
        "title": "S4 休眠循环",
        "description": "用于记录休眠恢复类测试的轮次、结果和失败证据。",
        "default_count": 20,
        "default_interval": 90,
        "requires_admin": True,
        "supports_resume": True,
        "supports_runtime": False,
        "supports_resume_workflow": True,
    },
    {
        "key": "reboot_cycle",
        "task_type": "reboot",
        "title": "重启循环",
        "description": "用于记录重启类测试轮次、恢复情况和异常信息。",
        "default_count": 10,
        "default_interval": 120,
        "requires_admin": True,
        "supports_resume": True,
        "supports_runtime": False,
        "supports_resume_workflow": True,
    },
    {
        "key": "memory_stress",
        "task_type": "memory_stress",
        "title": "内存压力测试",
        "description": "用于记录压力测试时长、轮次和失败日志。",
        "default_count": 12,
        "default_interval": 300,
        "requires_admin": False,
        "supports_resume": False,
        "supports_runtime": True,
        "supports_resume_workflow": False,
    },
    {
        "key": "burnin",
        "task_type": "burnin",
        "title": "BurnInTest",
        "description": "用于记录外部工具封装类长任务的执行和结果。",
        "default_count": 1,
        "default_interval": 43200,
        "requires_admin": False,
        "supports_resume": False,
        "supports_runtime": True,
        "supports_resume_workflow": False,
    },
]


def load_json(file_path: str, fallback=None):
    if not os.path.exists(file_path):
        return fallback
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def print_banner():
    print("=" * 72)
    print("  QCC 离线测试工作台")
    print("  Offline Test Workbench - Collect / Execute / Fill / Export")
    print("=" * 72)
    print()


def prompt_text(label: str, default: str = "", required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return ""
        print("  该项不能为空，请重新输入。")


def prompt_choice(label: str, options: list, default: str = "") -> str:
    normalized = {opt.lower(): opt for opt in options}
    default_label = default or options[0]
    while True:
        raw = input(f"{label} ({'/'.join(options)}) [{default_label}]: ").strip()
        if not raw:
            return default_label
        value = normalized.get(raw.lower())
        if value:
            return value
        print("  输入无效，请按给定选项输入。")


def prompt_yes_no(label: str, default: bool = True) -> bool:
    default_label = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{default_label}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "1"):
            return True
        if raw in ("n", "no", "0"):
            return False
        print("  请输入 y 或 n。")


def normalize_test_items(config: dict, test_plan: dict) -> list:
    if test_plan and test_plan.get("categories"):
        items = []
        for category in test_plan.get("categories", []):
            for item in category.get("items", []):
                normalized = dict(item)
                normalized["category"] = normalized.get("category") or category.get("category_name", "")
                normalized["category_code"] = normalized.get("category_code") or category.get("category_code", "")
                items.append(normalized)
        return items
    return config.get("test_items", [])


def load_package_context(config_path: str) -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"找不到配置文件: {config_path}")

    base_dir = os.path.dirname(os.path.abspath(config_path))
    config = load_json(config_path, {})
    manifest = load_json(os.path.join(base_dir, "manifest.json"), {})
    test_plan = load_json(os.path.join(base_dir, "test_plan.json"), {})
    expected_config = load_json(os.path.join(base_dir, "expected_config.json"), {})
    script_mapping = load_json(os.path.join(base_dir, "script_mapping.json"), [])

    project_info = config.get("project_info") or manifest.get("project", {})
    test_items = normalize_test_items(config, test_plan)

    return {
        "base_dir": base_dir,
        "config": config,
        "manifest": manifest or {},
        "test_plan": test_plan or {},
        "expected_config": expected_config or config.get("spec", {}) or {},
        "script_mapping": script_mapping or [],
        "project_info": project_info or {},
        "test_items": test_items,
        "test_config": config.get("test_config", {}),
    }


def normalize_identifier(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _mapping_value(mapping: dict, *keys: str) -> str:
    for key in keys:
        value = normalize_identifier(mapping.get(key))
        if value:
            return value
    return ""


def resolve_execution_mode(item: dict, matched_mapping: dict = None) -> str:
    for candidate in (
        item.get("execution_mode"),
        item.get("executionMode"),
        (matched_mapping or {}).get("execution_mode"),
        (matched_mapping or {}).get("executionMode"),
    ):
        normalized = normalize_identifier(candidate).lower()
        if normalized in ("auto", "semi_auto", "manual"):
            return normalized
    resolved_script_id = (
        normalize_identifier(item.get("script_id"))
        or _mapping_value(matched_mapping or {}, "script_id", "scriptId")
    )
    return "manual" if not resolved_script_id else "auto"


def format_execution_mode(mode: str) -> str:
    mapping = {
        "auto": "自动",
        "semi_auto": "半自动",
        "manual": "人工",
    }
    return mapping.get(normalize_identifier(mode).lower(), "人工")


def resolve_mapping_source(item: dict, matched_mapping: dict = None) -> str:
    for candidate in (
        item.get("mapping_source"),
        item.get("mappingSource"),
        item.get("source"),
        (matched_mapping or {}).get("mapping_source"),
        (matched_mapping or {}).get("mappingSource"),
        (matched_mapping or {}).get("source"),
    ):
        normalized = normalize_identifier(candidate)
        if normalized:
            return normalized
    return ""


def resolve_script_mapping(item: dict, script_mapping: list) -> dict:
    best_match = {}
    best_score = 0
    item_script_id = normalize_identifier(item.get("script_id"))
    item_test_id = normalize_identifier(item.get("test_id"))
    item_test_case = normalize_identifier(item.get("test_case"))
    item_item_no = normalize_identifier(item.get("item_no"))
    item_category_code = normalize_identifier(item.get("category_code"))

    for mapping in script_mapping or []:
        score = 0
        mapping_script_id = _mapping_value(mapping, "script_id", "scriptId")
        mapping_test_id = _mapping_value(mapping, "test_id", "testId")
        mapping_test_case = _mapping_value(mapping, "test_case", "testCase")
        mapping_item_no = _mapping_value(mapping, "item_no", "itemNo")
        mapping_category_code = _mapping_value(mapping, "category_code", "categoryCode")

        if item_script_id and mapping_script_id and item_script_id == mapping_script_id:
            score += 100
        if item_test_id and mapping_test_id and item_test_id == mapping_test_id:
            score += 90
        if item_test_case and mapping_test_case and item_test_case == mapping_test_case:
            score += 90
        if item_item_no and mapping_item_no and item_item_no == mapping_item_no:
            score += 30
        if item_category_code and mapping_category_code and item_category_code == mapping_category_code:
            score += 10

        if score > best_score:
            best_score = score
            best_match = mapping

    return best_match


def resolve_item_identity(item: dict, script_mapping: list = None) -> dict:
    matched_mapping = resolve_script_mapping(item, script_mapping or [])
    script_id = (
        normalize_identifier(item.get("script_id"))
        or _mapping_value(matched_mapping, "script_id", "scriptId")
    )
    test_id = (
        normalize_identifier(item.get("test_id"))
        or _mapping_value(matched_mapping, "test_id", "testId")
    )
    test_case = (
        normalize_identifier(item.get("test_case"))
        or _mapping_value(matched_mapping, "test_case", "testCase")
    )
    engine_test_id = script_id or test_id or test_case
    display_id = script_id or test_id or test_case or "-"
    return {
        "engine_test_id": engine_test_id,
        "display_id": display_id,
        "script_id": script_id,
        "test_id": test_id or test_case or script_id,
        "test_case": test_case or test_id,
        "execution_mode": resolve_execution_mode(item, matched_mapping),
        "mapping_source": resolve_mapping_source(item, matched_mapping),
        "matched_mapping": matched_mapping,
    }


def print_project_summary(context: dict):
    project_info = context["project_info"]
    print(f"  项目编号: {project_info.get('project_code', 'N/A')}")
    print(f"  产品型号: {project_info.get('product_model', 'N/A')}")
    print(f"  产品名称: {project_info.get('product_name', 'N/A')}")
    print(f"  模板名称: {project_info.get('template_name', 'N/A')}")
    print(f"  测试项数: {len(context['test_items'])}")
    print(f"  设备主机: {socket.gethostname()}")
    print(f"  操作系统: {platform.system()} {platform.release()}")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


def build_auto_result(item: dict, engine: TestEngine, spec: dict, timeout: int, script_mapping: list = None) -> dict:
    resolved = resolve_item_identity(item, script_mapping)
    engine_test_id = resolved["engine_test_id"]
    execution_mode = resolved["execution_mode"]
    if execution_mode == "manual":
        return {
            "test_id": resolved["test_id"],
            "script_id": resolved["script_id"],
            "test_name": item.get("test_name", ""),
            "execution_mode": execution_mode,
            "mapping_source": resolved["mapping_source"],
            "auto_executed": False,
            "suggested_verdict": "Manual",
            "raw_output": "",
            "metrics": {},
            "duration_ms": 0,
            "note": "当前测试项配置为人工项，不执行自动脚本，请人工确认结果。",
        }
    if not engine_test_id or engine_test_id not in engine.test_registry:
        return {
            "test_id": resolved["test_id"],
            "script_id": resolved["script_id"],
            "test_name": item.get("test_name", ""),
            "execution_mode": execution_mode,
            "mapping_source": resolved["mapping_source"],
            "auto_executed": False,
            "suggested_verdict": "Manual",
            "raw_output": "",
            "metrics": {},
            "duration_ms": 0,
            "note": "当前测试项没有自动脚本，需人工确认。",
        }

    result = engine.execute(engine_test_id, spec=spec, timeout=timeout)
    note = "自动脚本执行完成，可直接采用建议结果。"
    if execution_mode == "semi_auto":
        note = "半自动脚本执行完成，请结合现场现象人工确认最终结果。"
    return {
        "test_id": resolved["test_id"],
        "script_id": resolved["script_id"] or engine_test_id,
        "test_name": item.get("test_name", engine_test_id),
        "execution_mode": execution_mode,
        "mapping_source": resolved["mapping_source"],
        "auto_executed": True,
        "suggested_verdict": result.get("verdict", "Error"),
        "raw_output": result.get("raw_output", ""),
        "metrics": result.get("parsed", {}),
        "duration_ms": result.get("duration_ms", 0),
        "note": note,
    }


def collect_item_result(index: int, total: int, item: dict, auto_result: dict) -> dict:
    resolved = resolve_item_identity(item)
    print("-" * 72)
    print(f"[{index}/{total}] {item.get('test_name', '未命名测试项')}")
    print(f"  分类: {item.get('category', '-')}")
    print(f"  分类编码: {item.get('category_code', '-')}")
    print(f"  序号: {item.get('item_no', '-')}")
    print(f"  脚本ID: {auto_result.get('script_id') or resolved['display_id']}")
    print(f"  执行模式: {auto_result.get('execution_mode') or resolved.get('execution_mode', 'manual')}")
    if item.get("condition_desc"):
        print(f"  测试步骤: {item.get('condition_desc')}")
    if item.get("criteria"):
        print(f"  判定标准: {item.get('criteria')}")
    print()

    suggested = auto_result.get("suggested_verdict", "Manual")
    if auto_result.get("note"):
        print(f"  自动建议: {auto_result['note']}")
    if auto_result.get("metrics"):
        print("  自动采集结果:")
        for key, value in auto_result["metrics"].items():
            print(f"    - {key}: {value}")
    if auto_result.get("raw_output"):
        preview = auto_result["raw_output"][:400]
        print(f"  原始输出预览: {preview}")
    print()

    verdict = prompt_choice("  最终结果", VALID_VERDICTS, suggested if suggested in VALID_VERDICTS else "Manual")
    comment_required = verdict in ("Fail", "Blocked")
    comment_default = ""
    if verdict == suggested and auto_result.get("note"):
        comment_default = auto_result.get("note", "")
    comment = prompt_text("  备注", comment_default, required=comment_required)
    evidence = prompt_text("  证据文件路径（多个用英文逗号分隔，可留空）")
    log_files = prompt_text("  关联日志路径（多个用英文逗号分隔，可留空）")

    return {
        "test_id": resolved["test_id"],
        "script_id": auto_result.get("script_id") or resolved["script_id"],
        "test_case": resolved["test_case"],
        "execution_mode": auto_result.get("execution_mode") or resolved["execution_mode"],
        "mapping_source": auto_result.get("mapping_source") or resolved["mapping_source"],
        "auto_executed": auto_result.get("auto_executed", False),
        "item_no": item.get("item_no", ""),
        "test_name": item.get("test_name", ""),
        "category": item.get("category", ""),
        "category_code": item.get("category_code", ""),
        "verdict": verdict,
        "comment": comment,
        "evidence": [p.strip() for p in evidence.split(",") if p.strip()],
        "log_files": [p.strip() for p in log_files.split(",") if p.strip()],
        "raw_output": auto_result.get("raw_output", ""),
        "metrics": auto_result.get("metrics", {}),
        "duration_ms": auto_result.get("duration_ms", 0),
        "executed_at": datetime.now().isoformat(),
    }


def build_summary(results: list) -> dict:
    summary = {
        "total": len(results),
        "Pass": 0,
        "Fail": 0,
        "NA": 0,
        "Blocked": 0,
        "Manual": 0,
        "NotTested": 0,
    }
    for item in results:
        verdict = item.get("verdict", "Manual")
        summary[verdict] = summary.get(verdict, 0) + 1
    return summary


def build_precheck(results: list) -> dict:
    not_tested = []
    fail_without_comment = []
    fail_without_evidence = []
    blocked_without_comment = []

    for item in results:
        verdict = item.get("verdict", "NotTested")
        comment = (item.get("comment") or "").strip()
        evidence = item.get("evidence") or []

        if verdict == "NotTested":
            not_tested.append(item)
        if verdict == "Fail" and not comment:
            fail_without_comment.append(item)
        if verdict == "Fail" and not evidence:
            fail_without_evidence.append(item)
        if verdict == "Blocked" and not comment:
            blocked_without_comment.append(item)

    ready = not (not_tested or fail_without_comment or blocked_without_comment)
    return {
        "ready": ready,
        "not_tested": not_tested,
        "fail_without_comment": fail_without_comment,
        "fail_without_evidence": fail_without_evidence,
        "blocked_without_comment": blocked_without_comment,
    }


def collect_package_artifacts(results: list) -> dict:
    attachments = {
        "logs": [],
        "screenshots": [],
        "artifacts": [],
    }
    screenshot_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
    artifact_exts = {".csv", ".txt", ".html", ".json", ".xml", ".log"}

    for item in results:
        for file_path in item.get("evidence", []):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in screenshot_exts:
                attachments["screenshots"].append(file_path)
            elif ext in artifact_exts:
                attachments["artifacts"].append(file_path)
            else:
                attachments["artifacts"].append(file_path)
        for file_path in item.get("log_files", []):
            attachments["logs"].append(file_path)

    return attachments


def collect_runtime_artifacts(base_dir: str) -> list:
    runtime_dir = os.path.join(base_dir, "agent_runtime")
    if not os.path.exists(runtime_dir):
        return []
    files = []
    for root, _, names in os.walk(runtime_dir):
        for name in names:
            files.append(os.path.join(root, name))
    return files


def copy_attachment(src_path: str, target_dir: str, source_base: str):
    if not src_path:
        return None
    absolute_path = src_path
    if not os.path.isabs(absolute_path):
        absolute_path = os.path.join(source_base, src_path)
    absolute_path = os.path.abspath(absolute_path)
    if not os.path.exists(absolute_path):
        print(f"  [警告] 附件不存在，已跳过: {absolute_path}")
        return None

    ensure_dir(target_dir)
    target_path = os.path.join(target_dir, os.path.basename(absolute_path))
    if os.path.abspath(absolute_path) != os.path.abspath(target_path):
        shutil.copy2(absolute_path, target_path)
    return target_path


def capture_windows_screenshot(save_path: str) -> dict:
    script = rf"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save('{save_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return {"success": True, "path": save_path}
    except subprocess.CalledProcessError as exc:
        return {"success": False, "error": exc.stderr.strip() or exc.stdout.strip() or str(exc)}


def export_result_bundle(context: dict, system_info: dict, validation: dict, results: list, tester_name: str, long_task_state: dict = None) -> dict:
    project = context["project_info"]
    base_dir = context["base_dir"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_code = project.get("project_code", "QCC_RESULT")
    host_name = socket.gethostname()

    export_root = os.path.join(base_dir, "offline_results", f"{project_code}_{timestamp}")
    logs_dir = os.path.join(export_root, "logs")
    screenshots_dir = os.path.join(export_root, "screenshots")
    artifacts_dir = os.path.join(export_root, "artifacts")

    ensure_dir(export_root)
    ensure_dir(logs_dir)
    ensure_dir(screenshots_dir)
    ensure_dir(artifacts_dir)

    attachments = collect_package_artifacts(results)
    attachments["artifacts"].extend(collect_runtime_artifacts(base_dir))
    copied_logs = [copy_attachment(item, logs_dir, base_dir) for item in attachments["logs"]]
    copied_shots = [copy_attachment(item, screenshots_dir, base_dir) for item in attachments["screenshots"]]
    copied_artifacts = [copy_attachment(item, artifacts_dir, base_dir) for item in attachments["artifacts"]]

    manifest = {
        "package_type": "qcc_offline_result_package",
        "package_version": "1.1.0",
        "tool_version": AGENT_VERSION,
        "project_code": project.get("project_code", ""),
        "product_model": project.get("product_model", ""),
        "template_code": project.get("template_code", ""),
        "tester": tester_name,
        "hostname": host_name,
        "os_info": {
            "platform": platform.system(),
            "release": platform.release(),
            "arch": platform.machine(),
        },
        "started_at": system_info.get("collect_time", ""),
        "finished_at": datetime.now().isoformat(),
        "exported_at": datetime.now().isoformat(),
        "files": [
            "manifest.json",
            "result.json",
            "system_info.json",
            "logs/",
            "screenshots/",
            "artifacts/",
        ],
        "file_checksums": {},
    }

    if long_task_state and long_task_state.get("tasks"):
        manifest["files"].append("long_task_summary.json")

    mode_counts = {"auto": 0, "semi_auto": 0, "manual": 0}
    source_counts = {}
    for item in results:
        mode = normalize_identifier(item.get("execution_mode")).lower() or "manual"
        if mode not in mode_counts:
            mode_counts[mode] = 0
        mode_counts[mode] += 1
        source = normalize_identifier(item.get("mapping_source")) or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    result_json = {
        "manifest": {
            "project_code": project.get("project_code", ""),
            "template_code": project.get("template_code", ""),
            "tool_version": AGENT_VERSION,
            "hostname": host_name,
        },
        "summary": build_summary(results),
        "execution_mode_summary": mode_counts,
        "mapping_source_summary": source_counts,
        "validation": validation,
        "test_results": results,
    }

    manifest_path = os.path.join(export_root, "manifest.json")
    result_path = os.path.join(export_root, "result.json")
    system_info_path = os.path.join(export_root, "system_info.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)
    with open(system_info_path, "w", encoding="utf-8") as f:
        json.dump(system_info, f, ensure_ascii=False, indent=2)

    if long_task_state and long_task_state.get("tasks"):
        long_task_summary_path = os.path.join(export_root, "long_task_summary.json")
        long_task_summary = {
            "project_code": long_task_state.get("project_code", project_code),
            "updated_at": long_task_state.get("updated_at", ""),
            "tasks": long_task_state.get("tasks", []),
            "active_task_key": long_task_state.get("active_task_key", ""),
        }
        with open(long_task_summary_path, "w", encoding="utf-8") as f:
            json.dump(long_task_summary, f, ensure_ascii=False, indent=2)

    def build_file_checksum(file_path: str) -> dict:
        digest = hashlib.sha256()
        with open(file_path, "rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
        return {
            "size": os.path.getsize(file_path),
            "sha256": digest.hexdigest(),
        }

    manifest["file_checksums"]["result.json"] = build_file_checksum(result_path)
    manifest["file_checksums"]["system_info.json"] = build_file_checksum(system_info_path)
    if long_task_state and long_task_state.get("tasks"):
        manifest["file_checksums"]["long_task_summary.json"] = build_file_checksum(long_task_summary_path)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    zip_path = os.path.join(base_dir, f"QCC_Result_{project_code}_{timestamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(export_root):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                archive_name = os.path.relpath(file_path, export_root)
                zf.write(file_path, archive_name)

    # 生成本地 HTML 报告
    report_path = generate_local_report(export_root, project, result_json, system_info, tester_name)

    return {
        "export_dir": export_root,
        "zip_path": zip_path,
        "report_path": report_path,
        "summary": result_json["summary"],
        "copied_logs": [p for p in copied_logs if p],
        "copied_screenshots": [p for p in copied_shots if p],
        "copied_artifacts": [p for p in copied_artifacts if p],
        "has_long_task_summary": bool(long_task_state and long_task_state.get("tasks")),
    }


def generate_local_report(export_dir: str, project: dict, result_data: dict, system_info: dict, tester_name: str) -> str:
    """生成本地 HTML 测试报告"""
    project_code = project.get("project_code", "Unknown")
    product_model = project.get("product_model", "")
    product_name = project.get("product_name", "")
    summary = result_data.get("summary", {})
    results = result_data.get("test_results", [])
    hostname = socket.gethostname()

    # 计算通过率
    total = summary.get("total", 0)
    passed = summary.get("Pass", 0)
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    pass_rate_color = "#22c55e" if pass_rate >= 90 else "#f59e0b" if pass_rate >= 70 else "#ef4444"

    # 按分类分组结果
    categories = {}
    for r in results:
        cat = r.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    # 生成结果行
    result_rows = ""
    for cat_name, items in categories.items():
        result_rows += f'<tr><td colspan="6" style="background:#f1f5f9;font-weight:600;padding:10px;">{cat_name}</td></tr>\n'
        for item in items:
            verdict = item.get("verdict", "NotTested")
            verdict_colors = {"Pass": "#22c55e", "Fail": "#ef4444", "NA": "#94a3b8", "Blocked": "#f59e0b", "NotTested": "#94a3b8"}
            color = verdict_colors.get(verdict, "#94a3b8")
            result_rows += f'''<tr>
    <td>{item.get("item_no", "")}</td>
    <td>{item.get("test_name", "")}</td>
    <td style="color:{color};font-weight:600;">{verdict}</td>
    <td>{item.get("comment", "")}</td>
    <td>{item.get("tester_name", tester_name)}</td>
    <td>{item.get("executed_at", "")[:19] if item.get("executed_at") else ""}</td>
</tr>\n'''

    # 系统信息
    sys_info_html = ""
    if system_info:
        sys_info_items = [
            ("操作系统", system_info.get("os_version", "")),
            ("主机名", hostname),
            ("处理器", system_info.get("cpu_model", "")),
            ("内存", system_info.get("memory_total", "")),
            ("磁盘", system_info.get("disk_model", "")),
            ("BIOS", system_info.get("bios_version", "")),
        ]
        for label, value in sys_info_items:
            if value:
                sys_info_html += f"<tr><td><strong>{label}</strong></td><td>{value}</td></tr>\n"

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {project_code}</title>
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
        @media print {{ body {{ background: white; padding: 0; }} .container {{ box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>QCC 测试报告</h1>
            <p>项目: {project_code} | 型号: {product_model} | 产品: {product_name}</p>
        </div>
        <div class="content">
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{total}</div>
                    <div class="stat-label">总项数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:#22c55e">{passed}</div>
                    <div class="stat-label">通过</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:#ef4444">{summary.get("Fail", 0)}</div>
                    <div class="stat-label">失败</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{summary.get("NA", 0)}</div>
                    <div class="stat-label">不适用</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:{pass_rate_color}">{pass_rate}%</div>
                    <div class="stat-label">通过率</div>
                </div>
            </div>

            {"<div class='section'><h2>系统信息</h2><table>" + sys_info_html + "</table></div>" if sys_info_html else ""}

            <div class="section">
                <h2>测试结果明细</h2>
                <table>
                    <thead>
                        <tr>
                            <th>编号</th>
                            <th>测试项</th>
                            <th>结果</th>
                            <th>备注</th>
                            <th>测试人</th>
                            <th>时间</th>
                        </tr>
                    </thead>
                    <tbody>
                        {result_rows}
                    </tbody>
                </table>
            </div>
        </div>
        <div class="footer">
            <p>测试人员: {tester_name} | 主机: {hostname} | 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p style="margin-top:8px;">QCC 测试报告自动化平台</p>
        </div>
    </div>
</body>
</html>'''

    report_path = os.path.join(export_dir, f"report_{project_code}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path


def make_default_result(item: dict, script_mapping: list = None) -> dict:
    resolved = resolve_item_identity(item, script_mapping)
    return {
        "test_id": resolved["test_id"],
        "script_id": resolved["script_id"],
        "test_case": resolved["test_case"],
        "execution_mode": resolved["execution_mode"],
        "mapping_source": resolved["mapping_source"],
        "auto_executed": False,
        "item_no": item.get("item_no", ""),
        "test_name": item.get("test_name", ""),
        "category": item.get("category", ""),
        "category_code": item.get("category_code", ""),
        "verdict": "NotTested",
        "comment": "",
        "evidence": [],
        "log_files": [],
        "raw_output": "",
        "metrics": {},
        "duration_ms": 0,
        "executed_at": "",
    }


def make_default_long_task_state(project_code: str = "") -> dict:
    return {
        "project_code": project_code,
        "active_task_key": "",
        "updated_at": "",
        "tasks": [],
    }


class OfflineWorkbenchApp:
    def __init__(self, root: tk.Tk, config_path: str, auto_resume_task_key: str = ""):
        self.root = root
        self.root.title("QCC 离线测试工作台")
        self.root.geometry("1480x900")
        self.root.minsize(1200, 760)

        self.config_path = config_path
        self.auto_resume_task_key = auto_resume_task_key
        self.context = load_package_context(config_path)
        self.collector = SystemCollector()
        self.engine = TestEngine()
        self.stress_manager = StressManager()
        self.system_info = {}
        self.validation = {}
        self.results = [make_default_result(item, self.context.get("script_mapping")) for item in self.context["test_items"]]
        self.auto_results = {}
        self.current_index = None
        self.long_task_templates = [dict(item) for item in LONG_TASK_TEMPLATES]
        self.long_task_state = self._load_long_task_state()
        self.current_long_task_key = self.long_task_state.get("active_task_key") or self.long_task_templates[0]["key"]
        self.long_task_poll_job = None

        default_tester = self.context["project_info"].get("tester") or socket.gethostname()
        self.tester_var = tk.StringVar(value=default_tester)
        self.status_var = tk.StringVar(value="离线工作台已就绪，请先采集系统信息，再开始执行测试。")
        self.summary_var = tk.StringVar(value="")
        self.precheck_var = tk.StringVar(value="")
        self.detail_auto_var = tk.StringVar(value="尚未执行自动化建议。")
        self.detail_validation_var = tk.StringVar(value="尚未完成环境校验。")
        self.verdict_var = tk.StringVar(value="NotTested")
        self.evidence_var = tk.StringVar(value="")
        self.logs_var = tk.StringVar(value="")
        self.attachment_hint_var = tk.StringVar(value="当前未选择证据或日志文件。")
        self.attachment_preview_var = tk.StringVar(value="附件预览：暂无")
        self.overview_var = tk.StringVar(value="")
        self.system_info_summary_var = tk.StringVar(value="尚未采集系统信息。")
        self.validation_summary_var = tk.StringVar(value="尚未执行环境校验。")
        self.summary_page_var = tk.StringVar(value="")
        self.summary_issue_var = tk.StringVar(value="")
        self.export_page_var = tk.StringVar(value="")
        self.export_checklist_var = tk.StringVar(value="")
        self.export_result_var = tk.StringVar(value="尚未导出结果包。")
        self.last_export_result = None
        self.long_task_count_var = tk.StringVar(value="")
        self.long_task_interval_var = tk.StringVar(value="")
        self.long_task_status_var = tk.StringVar(value="尚未创建计划。")
        self.long_task_summary_var = tk.StringVar(value="")
        self.long_task_state_path_var = tk.StringVar(value="")
        self.long_task_resume_var = tk.StringVar(value="恢复继续：当前未进入等待恢复状态。")

        self._build_ui()
        self.tester_var.trace_add("write", self._on_tester_change)
        self._refresh_project_info()
        self._refresh_tree()
        self._refresh_long_task_tree()
        if self.context["test_items"]:
            self.tree.selection_set("item-0")
            self.on_tree_select()
        if self.auto_resume_task_key:
            self.root.after(600, lambda: self._auto_resume_on_launch(self.auto_resume_task_key))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)

        title_label = ttk.Label(header, text="QCC 离线测试工作台", font=("Microsoft YaHei", 18, "bold"))
        title_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="现场执行端：读取测试包、采集环境、执行测试、人工确认并导出标准结果包",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        info_frame = ttk.Frame(header)
        info_frame.grid(row=2, column=0, sticky="ew")
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)

        self.project_info_labels = {}
        info_keys = [
            ("项目编号", "project_code"),
            ("产品型号", "product_model"),
            ("模板", "template_name"),
            ("测试项", "total_items"),
        ]
        for idx, (label, key) in enumerate(info_keys):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(info_frame, text=f"{label}：").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=2)
            value = ttk.Label(info_frame, text="-", font=("Microsoft YaHei", 10, "bold"))
            value.grid(row=row, column=col + 1, sticky="w", pady=2)
            self.project_info_labels[key] = value

        ttk.Label(info_frame, text="测试人员：").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        ttk.Entry(info_frame, textvariable=self.tester_var, width=28).grid(row=2, column=1, sticky="w", pady=(8, 0))

        button_bar = ttk.Frame(header)
        button_bar.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        for idx in range(6):
            button_bar.columnconfigure(idx, weight=0)
        ttk.Button(button_bar, text="切换测试包", command=self.choose_package).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_bar, text="采集系统信息", command=self.collect_system_info).grid(row=0, column=1, padx=8)
        ttk.Button(button_bar, text="自动执行当前项", command=self.run_selected_auto).grid(row=0, column=2, padx=8)
        ttk.Button(button_bar, text="自动执行全部可执行项", command=self.run_all_auto).grid(row=0, column=3, padx=8)
        ttk.Button(button_bar, text="保存当前项", command=self.save_current_item).grid(row=0, column=4, padx=8)
        ttk.Button(button_bar, text="结果汇总/检查", command=self.open_summary_window).grid(row=0, column=5, padx=8)
        ttk.Button(button_bar, text="导出结果包", command=self.export_bundle).grid(row=0, column=6, padx=(8, 0))

        ttk.Label(header, textvariable=self.summary_var, foreground="#1f3b5b").grid(row=4, column=0, sticky="w", pady=(10, 4))
        ttk.Label(header, textvariable=self.precheck_var, foreground="#8a5a00").grid(row=5, column=0, sticky="w", pady=(0, 4))
        ttk.Label(header, textvariable=self.status_var, foreground="#555").grid(row=6, column=0, sticky="w")

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        overview_tab = ttk.Frame(notebook, padding=16)
        system_tab = ttk.Frame(notebook, padding=16)
        execution_tab = ttk.Frame(notebook, padding=0)
        summary_tab = ttk.Frame(notebook, padding=16)
        long_task_tab = ttk.Frame(notebook, padding=16)
        export_tab = ttk.Frame(notebook, padding=16)
        notebook.add(overview_tab, text="项目概览")
        notebook.add(system_tab, text="系统信息")
        notebook.add(execution_tab, text="测试执行")
        notebook.add(summary_tab, text="结果汇总")
        notebook.add(long_task_tab, text="压力/循环测试")
        notebook.add(export_tab, text="导出结果")

        overview_tab.columnconfigure(0, weight=3)
        overview_tab.columnconfigure(1, weight=2)
        ttk.Label(overview_tab, text="项目首页", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(overview_tab, text="查看项目上下文、整体进度和当前建议操作。", foreground="#666").grid(row=1, column=0, sticky="w", pady=(4, 14))
        overview_main = ttk.LabelFrame(overview_tab, text="项目与流程概览", padding=14)
        overview_main.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        overview_main.columnconfigure(0, weight=1)
        ttk.Label(overview_main, textvariable=self.overview_var, wraplength=760, justify="left").grid(row=0, column=0, sticky="w")
        overview_actions = ttk.Frame(overview_main)
        overview_actions.grid(row=1, column=0, sticky="w", pady=(14, 0))
        ttk.Button(overview_actions, text="切换测试包", command=self.choose_package).pack(side="left")
        ttk.Button(overview_actions, text="采集系统信息", command=self.collect_system_info).pack(side="left", padx=8)
        ttk.Button(overview_actions, text="进入测试执行", command=lambda: notebook.select(execution_tab)).pack(side="left", padx=8)
        ttk.Button(overview_actions, text="查看结果汇总", command=lambda: notebook.select(summary_tab)).pack(side="left", padx=8)
        ttk.Button(overview_actions, text="长任务工作台", command=lambda: notebook.select(long_task_tab)).pack(side="left", padx=8)
        ttk.Button(overview_actions, text="前往导出页", command=lambda: notebook.select(export_tab)).pack(side="left", padx=8)

        overview_side = ttk.LabelFrame(overview_tab, text="当前建议", padding=14)
        overview_side.grid(row=2, column=1, sticky="nsew")
        ttk.Label(
            overview_side,
            text=(
                "1. 先采集系统信息，确认环境校验是否通过。\n"
                "2. 在测试执行页逐项确认自动建议或人工填写结果。\n"
                "3. 在结果汇总页检查未测项、Fail 缺备注和缺证据项。\n"
                "4. 确认无误后导出标准 ZIP 结果包。"
            ),
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        system_tab.columnconfigure(0, weight=1)
        ttk.Label(system_tab, text="系统信息与环境校验", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(system_tab, textvariable=self.system_info_summary_var, foreground="#1f3b5b").grid(row=1, column=0, sticky="w", pady=(6, 4))
        ttk.Label(system_tab, textvariable=self.validation_summary_var, foreground="#8a5a00").grid(row=2, column=0, sticky="w", pady=(0, 12))
        system_actions = ttk.Frame(system_tab)
        system_actions.grid(row=3, column=0, sticky="w", pady=(0, 12))
        ttk.Button(system_actions, text="重新采集系统信息", command=self.collect_system_info).pack(side="left")
        ttk.Button(system_actions, text="去测试执行页", command=lambda: notebook.select(execution_tab)).pack(side="left", padx=8)
        self.system_info_text = tk.Text(system_tab, wrap="word", height=28)
        self.system_info_text.grid(row=4, column=0, sticky="nsew")
        self.system_info_text.configure(state="disabled")
        system_tab.rowconfigure(4, weight=1)

        execution_tab.columnconfigure(0, weight=1)
        execution_tab.rowconfigure(0, weight=1)
        main = ttk.Panedwindow(execution_tab, orient=tk.HORIZONTAL)
        main.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(main, padding=10)
        center = ttk.Frame(main, padding=10)
        right = ttk.Frame(main, padding=10)
        main.add(left, weight=3)
        main.add(center, weight=4)
        main.add(right, weight=4)

        ttk.Label(left, text="测试项列表", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        self.tree = ttk.Treeview(left, columns=("category", "mode", "verdict"), show="tree headings", height=28)
        self.tree.heading("#0", text="测试项")
        self.tree.heading("category", text="分类")
        self.tree.heading("mode", text="模式")
        self.tree.heading("verdict", text="结果")
        self.tree.column("#0", width=220, stretch=True)
        self.tree.column("category", width=120, stretch=True)
        self.tree.column("mode", width=70, stretch=False, anchor="center")
        self.tree.column("verdict", width=90, stretch=False, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=(8, 0))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.on_tree_select())

        ttk.Label(center, text="测试详情", font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        self.detail_text = tk.Text(center, wrap="word", height=20)
        self.detail_text.pack(fill="both", expand=True, pady=(8, 10))
        self.detail_text.configure(state="disabled")

        ttk.Label(center, text="环境校验结论", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        ttk.Label(center, textvariable=self.detail_validation_var, wraplength=420, justify="left").pack(anchor="w", pady=(4, 10))
        ttk.Label(center, text="自动执行建议", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        ttk.Label(center, textvariable=self.detail_auto_var, wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))

        ttk.Label(right, text="结果填写", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, sticky="w")
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="最终结果").grid(row=1, column=0, sticky="w", pady=(12, 4))
        verdict_box = ttk.Combobox(right, textvariable=self.verdict_var, values=VALID_VERDICTS, state="readonly")
        verdict_box.grid(row=2, column=0, sticky="ew")

        ttk.Label(right, text="备注").grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.comment_text = tk.Text(right, wrap="word", height=8)
        self.comment_text.grid(row=4, column=0, sticky="nsew")

        ttk.Label(right, text="证据路径（英文逗号分隔）").grid(row=5, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(right, textvariable=self.evidence_var).grid(row=6, column=0, sticky="ew")
        evidence_actions = ttk.Frame(right)
        evidence_actions.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(evidence_actions, text="选择证据文件", command=self.choose_evidence_files).pack(side="left")
        ttk.Button(evidence_actions, text="屏幕截图", command=self.capture_screenshot_for_current_item).pack(side="left", padx=8)
        ttk.Button(evidence_actions, text="清空证据", command=self.clear_evidence_files).pack(side="left", padx=8)

        ttk.Label(right, text="日志路径（英文逗号分隔）").grid(row=8, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(right, textvariable=self.logs_var).grid(row=9, column=0, sticky="ew")
        logs_actions = ttk.Frame(right)
        logs_actions.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(logs_actions, text="选择日志文件", command=self.choose_log_files).pack(side="left")
        ttk.Button(logs_actions, text="清空日志", command=self.clear_log_files).pack(side="left", padx=8)
        ttk.Label(right, textvariable=self.attachment_hint_var, foreground="#666").grid(row=11, column=0, sticky="w", pady=(10, 0))
        ttk.Label(right, textvariable=self.attachment_preview_var, foreground="#555", wraplength=420, justify="left").grid(row=12, column=0, sticky="w", pady=(6, 0))

        action_frame = ttk.Frame(right)
        action_frame.grid(row=13, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(action_frame, text="采用自动建议", command=self.apply_suggested_result).pack(side="left")
        ttk.Button(action_frame, text="保存当前项", command=self.save_current_item).pack(side="left", padx=8)
        ttk.Button(action_frame, text="结果汇总/检查", command=self.open_summary_window).pack(side="right")
        ttk.Button(action_frame, text="导出结果包", command=self.export_bundle).pack(side="right", padx=(0, 8))
        right.rowconfigure(4, weight=1)

        summary_tab.columnconfigure(0, weight=1)
        ttk.Label(summary_tab, text="结果汇总与导出准备", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(summary_tab, textvariable=self.summary_page_var, foreground="#1f3b5b").grid(row=1, column=0, sticky="w", pady=(6, 8))
        ttk.Label(summary_tab, textvariable=self.summary_issue_var, foreground="#8a5a00", wraplength=1120, justify="left").grid(row=2, column=0, sticky="w")
        summary_actions = ttk.Frame(summary_tab)
        summary_actions.grid(row=3, column=0, sticky="w", pady=(12, 12))
        ttk.Button(summary_actions, text="打开详细检查窗口", command=self.open_summary_window).pack(side="left")
        ttk.Button(summary_actions, text="返回测试执行", command=lambda: notebook.select(execution_tab)).pack(side="left", padx=8)
        ttk.Button(summary_actions, text="长任务工作台", command=lambda: notebook.select(long_task_tab)).pack(side="left", padx=8)
        ttk.Button(summary_actions, text="前往导出页", command=lambda: notebook.select(export_tab)).pack(side="left", padx=8)

        long_task_tab.columnconfigure(0, weight=2)
        long_task_tab.columnconfigure(1, weight=3)
        long_task_tab.columnconfigure(2, weight=2)
        long_task_tab.rowconfigure(2, weight=1)
        ttk.Label(long_task_tab, text="压力/循环测试工作台", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            long_task_tab,
            text="当前提供长任务计划、状态文件和恢复入口。实际自动执行将在下一阶段接入现有压力测试引擎。",
            foreground="#666",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        long_task_left = ttk.LabelFrame(long_task_tab, text="任务清单", padding=10)
        long_task_left.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        long_task_left.columnconfigure(0, weight=1)
        long_task_left.rowconfigure(1, weight=1)
        ttk.Label(long_task_left, textvariable=self.long_task_summary_var, foreground="#1f3b5b", wraplength=320, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.long_task_tree = ttk.Treeview(long_task_left, columns=("status", "progress"), show="tree headings", height=16)
        self.long_task_tree.heading("#0", text="任务")
        self.long_task_tree.heading("status", text="状态")
        self.long_task_tree.heading("progress", text="进度")
        self.long_task_tree.column("#0", width=180, stretch=True)
        self.long_task_tree.column("status", width=90, anchor="center")
        self.long_task_tree.column("progress", width=90, anchor="center")
        self.long_task_tree.grid(row=1, column=0, sticky="nsew")
        self.long_task_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_long_task_select())

        long_task_center = ttk.LabelFrame(long_task_tab, text="任务详情与状态文件", padding=10)
        long_task_center.grid(row=2, column=1, sticky="nsew", padx=(0, 12))
        long_task_center.columnconfigure(0, weight=1)
        long_task_center.rowconfigure(2, weight=1)
        ttk.Label(long_task_center, textvariable=self.long_task_status_var, foreground="#8a5a00", wraplength=520, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(long_task_center, textvariable=self.long_task_state_path_var, foreground="#555", wraplength=520, justify="left").grid(row=1, column=0, sticky="w", pady=(8, 10))
        self.long_task_detail_text = tk.Text(long_task_center, wrap="word", height=20)
        self.long_task_detail_text.grid(row=2, column=0, sticky="nsew")
        self.long_task_detail_text.configure(state="disabled")
        ttk.Label(long_task_center, textvariable=self.long_task_resume_var, foreground="#1f3b5b", wraplength=520, justify="left").grid(row=3, column=0, sticky="w", pady=(10, 0))

        long_task_right = ttk.LabelFrame(long_task_tab, text="任务操作", padding=10)
        long_task_right.grid(row=2, column=2, sticky="nsew")
        long_task_right.columnconfigure(0, weight=1)
        ttk.Label(long_task_right, text="计划轮次").grid(row=0, column=0, sticky="w")
        ttk.Entry(long_task_right, textvariable=self.long_task_count_var).grid(row=1, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(long_task_right, text="间隔秒数").grid(row=2, column=0, sticky="w")
        ttk.Entry(long_task_right, textvariable=self.long_task_interval_var).grid(row=3, column=0, sticky="ew", pady=(4, 10))
        ttk.Button(long_task_right, text="创建/更新计划", command=self.upsert_long_task_plan).grid(row=4, column=0, sticky="ew", pady=(4, 6))
        ttk.Button(long_task_right, text="标记开始执行", command=self.start_long_task_plan).grid(row=5, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="真实启动任务", command=self.start_long_task_runtime).grid(row=6, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="刷新运行状态", command=self.refresh_long_task_runtime).grid(row=7, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="停止真实任务", command=self.stop_long_task_runtime).grid(row=8, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="标记等待恢复", command=self.mark_long_task_resume_pending).grid(row=9, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="恢复后继续", command=self.resume_long_task_after_recovery).grid(row=10, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="恢复失败留证", command=self.capture_long_task_failure).grid(row=11, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="记录本轮成功", command=lambda: self.record_long_task_step(True)).grid(row=12, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="记录本轮失败", command=lambda: self.record_long_task_step(False)).grid(row=13, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="暂停任务", command=self.pause_long_task_plan).grid(row=14, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="从状态文件恢复", command=self.restore_long_task_state).grid(row=15, column=0, sticky="ew", pady=6)
        ttk.Button(long_task_right, text="清理续跑文件", command=self.clear_long_task_resume_artifacts).grid(row=16, column=0, sticky="ew", pady=6)
        ttk.Label(
            long_task_right,
            text=(
                "说明：\n"
                "1. 当前已接入内存压力测试和 BurnInTest 的真实启动。\n"
                "2. S3 / S4 / 重启循环支持等待恢复、恢复继续和失败留证骨架。\n"
                "3. 当前只生成续跑说明/占位文件，不直接注册系统自启动。\n"
                "4. 当前状态文件和失败证据会自动归档进结果包。"
            ),
            wraplength=300,
            justify="left",
            foreground="#666",
        ).grid(row=17, column=0, sticky="w", pady=(12, 0))

        export_tab.columnconfigure(0, weight=3)
        export_tab.columnconfigure(1, weight=2)
        export_tab.rowconfigure(3, weight=1)
        ttk.Label(export_tab, text="结果导出页", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(export_tab, text="确认导出条件、查看结果包结构，并执行最终导出。", foreground="#666").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))

        export_main = ttk.LabelFrame(export_tab, text="导出状态", padding=14)
        export_main.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        export_main.columnconfigure(0, weight=1)
        ttk.Label(export_main, textvariable=self.export_page_var, wraplength=760, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(export_main, textvariable=self.export_checklist_var, foreground="#8a5a00", wraplength=760, justify="left").grid(row=1, column=0, sticky="w", pady=(12, 0))

        export_result = ttk.LabelFrame(export_tab, text="最近一次导出", padding=14)
        export_result.grid(row=3, column=0, sticky="nsew", padx=(0, 12), pady=(12, 0))
        export_result.columnconfigure(0, weight=1)
        ttk.Label(export_result, textvariable=self.export_result_var, wraplength=760, justify="left").grid(row=0, column=0, sticky="nw")

        export_side = ttk.LabelFrame(export_tab, text="结果包说明", padding=14)
        export_side.grid(row=2, column=1, rowspan=2, sticky="nsew")
        ttk.Label(
            export_side,
            text=(
                "标准结果包 ZIP 结构：\n"
                "- manifest.json：项目、工具版本、主机、时间信息\n"
                "- result.json：测试结果、统计、备注、证据\n"
                "- system_info.json：完整设备环境信息\n"
                "- logs/：日志文件\n"
                "- screenshots/：截图证据\n"
                "- artifacts/：外部工具输出和其他附件"
            ),
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        export_actions = ttk.Frame(export_side)
        export_actions.grid(row=1, column=0, sticky="w", pady=(16, 0))
        ttk.Button(export_actions, text="打开详细检查窗口", command=self.open_summary_window).pack(side="left")
        ttk.Button(export_actions, text="长任务工作台", command=lambda: notebook.select(long_task_tab)).pack(side="left", padx=8)
        ttk.Button(export_actions, text="返回结果汇总", command=lambda: notebook.select(summary_tab)).pack(side="left", padx=8)
        ttk.Button(export_actions, text="导出结果包", command=self.export_bundle).pack(side="left", padx=8)

    def _refresh_project_info(self):
        project = self.context["project_info"]
        self.project_info_labels["project_code"].config(text=project.get("project_code", "-"))
        self.project_info_labels["product_model"].config(text=project.get("product_model", "-"))
        self.project_info_labels["template_name"].config(text=project.get("template_name", "-"))
        self.project_info_labels["total_items"].config(text=str(len(self.context["test_items"])))
        self._update_system_info_panel()
        self._update_summary()
        self._refresh_long_task_tree()

    def _on_tester_change(self, *_args):
        self._update_overview_tab()
        self._update_export_page()

    def _get_execution_mode_buckets(self) -> dict:
        buckets = {
            "auto": [],
            "semi_auto": [],
            "manual": [],
            "semi_auto_pending": [],
            "manual_pending": [],
        }
        for index, item in enumerate(self.context["test_items"]):
            result = self.results[index]
            mode = resolve_item_identity(item, self.context.get("script_mapping")).get("execution_mode", "manual")
            buckets.setdefault(mode, []).append(result)
            if mode == "semi_auto" and result.get("verdict") in ("NotTested", "Manual"):
                buckets["semi_auto_pending"].append(result)
            if mode == "manual" and result.get("verdict") == "NotTested":
                buckets["manual_pending"].append(result)
        return buckets

    def _update_summary(self):
        summary = build_summary(self.results)
        precheck = build_precheck(self.results)
        mode_buckets = self._get_execution_mode_buckets()
        self.summary_var.set(
            "结果汇总："
            f"总数 {summary.get('total', 0)} | "
            f"未测 {summary.get('NotTested', 0)} | "
            f"Pass {summary.get('Pass', 0)} | "
            f"Fail {summary.get('Fail', 0)} | "
            f"NA {summary.get('NA', 0)} | "
            f"Blocked {summary.get('Blocked', 0)} | "
            f"Manual {summary.get('Manual', 0)} | "
            f"自动 {len(mode_buckets['auto'])} | "
            f"半自动 {len(mode_buckets['semi_auto'])} | "
            f"人工 {len(mode_buckets['manual'])}"
        )
        self.precheck_var.set(
            "导出前检查："
            f"未测 {len(precheck['not_tested'])} | "
            f"Fail缺备注 {len(precheck['fail_without_comment'])} | "
            f"Fail缺证据 {len(precheck['fail_without_evidence'])} | "
            f"Blocked缺备注 {len(precheck['blocked_without_comment'])} | "
            f"半自动待确认 {len(mode_buckets['semi_auto_pending'])} | "
            f"人工项未填写 {len(mode_buckets['manual_pending'])}"
        )
        self._update_overview_tab()
        self._update_summary_page(summary, precheck)
        self._update_export_page(summary, precheck)

    def _update_overview_tab(self):
        project = self.context["project_info"]
        summary = build_summary(self.results)
        precheck = build_precheck(self.results)
        mode_buckets = self._get_execution_mode_buckets()
        long_task_summary = self._build_long_task_summary_text()
        lines = [
            f"项目编号：{project.get('project_code', '-')}",
            f"产品型号：{project.get('product_model', '-')}",
            f"模板名称：{project.get('template_name', '-')}",
            f"测试人员：{self.tester_var.get().strip() or '-'}",
            f"测试项总数：{len(self.context['test_items'])}",
            "",
            "当前进度：",
            f"- 未测试 {summary.get('NotTested', 0)} 项",
            f"- 已通过 {summary.get('Pass', 0)} 项",
            f"- 失败 {summary.get('Fail', 0)} 项",
            f"- 阻塞 {summary.get('Blocked', 0)} 项",
            "",
            "当前风险：",
            f"- Fail 缺备注 {len(precheck['fail_without_comment'])} 项",
            f"- Fail 缺证据 {len(precheck['fail_without_evidence'])} 项",
            f"- Blocked 缺备注 {len(precheck['blocked_without_comment'])} 项",
            f"- 半自动待确认 {len(mode_buckets['semi_auto_pending'])} 项",
            f"- 人工项未填写 {len(mode_buckets['manual_pending'])} 项",
            "",
            f"长任务状态：{long_task_summary}",
        ]
        self.overview_var.set("\n".join(lines))

    def _update_text_widget(self, widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _update_system_info_panel(self):
        if not self.system_info:
            self.system_info_summary_var.set("尚未采集系统信息。")
            self.validation_summary_var.set("尚未执行环境校验。")
            self._update_text_widget(self.system_info_text, "请先点击“采集系统信息”，再查看机器环境、设备和配置校验结论。")
            return

        summary_lines = [
            f"主机名：{self.system_info.get('hostname', '-')}",
            f"操作系统：{self.system_info.get('os', '-')}",
            f"BIOS：{self.system_info.get('bios_version', '-')}",
            f"CPU：{self.system_info.get('cpu_model', '-')}",
            f"内存：{self.system_info.get('memory_total', '-')}",
            f"硬盘：{self.system_info.get('disk_model', '-')}",
        ]
        self.system_info_summary_var.set(" | ".join(summary_lines))

        if self.validation:
            self.validation_summary_var.set(
                f"环境校验：{self.validation.get('conclusion', '-')}，"
                f"通过 {self.validation.get('passed', 0)} / {self.validation.get('total', 0)}"
            )
        else:
            self.validation_summary_var.set("尚未执行环境校验。")

        detail_lines = ["系统信息详情："]
        for key, value in self.system_info.items():
            detail_lines.append(f"- {key}: {value}")
        if self.validation:
            detail_lines.append("")
            detail_lines.append("环境校验详情：")
            for item in self.validation.get("items", [])[:50]:
                detail_lines.append(
                    f"- {item.get('key', '-')}: expected={item.get('expected', '-')}, actual={item.get('actual', '-')}, verdict={item.get('verdict', '-')}"
                )
        self._update_text_widget(self.system_info_text, "\n".join(detail_lines))

    def _update_summary_page(self, summary: dict, precheck: dict):
        mode_buckets = self._get_execution_mode_buckets()
        self.summary_page_var.set(
            f"总数 {summary.get('total', 0)} | 未测 {summary.get('NotTested', 0)} | "
            f"Pass {summary.get('Pass', 0)} | Fail {summary.get('Fail', 0)} | "
            f"NA {summary.get('NA', 0)} | Blocked {summary.get('Blocked', 0)} | "
            f"Manual {summary.get('Manual', 0)} | "
            f"自动 {len(mode_buckets['auto'])} | 半自动 {len(mode_buckets['semi_auto'])} | 人工 {len(mode_buckets['manual'])}"
        )
        issue_lines = [
            f"未测试项：{len(precheck['not_tested'])}",
            f"Fail 缺备注：{len(precheck['fail_without_comment'])}",
            f"Fail 缺证据：{len(precheck['fail_without_evidence'])}",
            f"Blocked 缺备注：{len(precheck['blocked_without_comment'])}",
            f"半自动待确认：{len(mode_buckets['semi_auto_pending'])}",
            f"人工项未填写：{len(mode_buckets['manual_pending'])}",
        ]
        if precheck["ready"]:
            issue_lines.append("当前已满足基本导出条件。")
        else:
            issue_lines.append("当前仍有导出风险，建议先打开详细检查窗口逐项处理。")
        self.summary_issue_var.set(" | ".join(issue_lines))

    def _update_export_page(self, summary: dict = None, precheck: dict = None):
        if summary is None:
            summary = build_summary(self.results)
        if precheck is None:
            precheck = build_precheck(self.results)
        mode_buckets = self._get_execution_mode_buckets()

        attachments = collect_package_artifacts(self.results)
        tester_name = self.tester_var.get().strip()
        long_task_state_path = self._get_long_task_state_path(create_dir=False)
        export_lines = [
            f"测试人员：{tester_name or '-'}",
            f"系统信息：{'已采集' if self.system_info else '未采集'}",
            f"结果统计：总数 {summary.get('total', 0)}，未测 {summary.get('NotTested', 0)}，"
            f"Pass {summary.get('Pass', 0)}，Fail {summary.get('Fail', 0)}，"
            f"Blocked {summary.get('Blocked', 0)}，Manual {summary.get('Manual', 0)}",
            f"执行模式：自动 {len(mode_buckets['auto'])}，半自动 {len(mode_buckets['semi_auto'])}，人工 {len(mode_buckets['manual'])}",
            f"待确认项：半自动待确认 {len(mode_buckets['semi_auto_pending'])}，人工项未填写 {len(mode_buckets['manual_pending'])}",
            f"附件统计：日志 {len(attachments['logs'])}，截图 {len(attachments['screenshots'])}，其他附件 {len(attachments['artifacts'])}",
            f"长任务状态文件：{'已生成' if os.path.exists(long_task_state_path) else '未生成'}",
        ]
        if self.last_export_result:
            export_lines.append(f"最近导出 ZIP：{self.last_export_result.get('zip_path', '-')}")
        self.export_page_var.set("\n".join(export_lines))

        checklist = [
            f"{'已完成' if self.system_info else '待处理'}：系统信息采集",
            f"{'已完成' if tester_name else '待处理'}：测试人员信息填写",
            f"{'已完成' if not precheck['not_tested'] else '待处理'}：未测试项处理",
            f"{'已完成' if not precheck['fail_without_comment'] else '待处理'}：Fail 项备注补齐",
            f"{'建议补充' if precheck['fail_without_evidence'] else '已完成'}：Fail 项证据补齐",
            f"{'已完成' if not precheck['blocked_without_comment'] else '待处理'}：Blocked 项备注补齐",
            f"{'建议确认' if mode_buckets['semi_auto_pending'] else '已完成'}：半自动项人工确认",
            f"{'待处理' if mode_buckets['manual_pending'] else '已完成'}：人工项结果填写",
        ]
        final_hint = "当前可以直接导出结果包。" if self.system_info and tester_name and precheck["ready"] else "当前仍建议先处理待办项，再执行导出。"
        self.export_checklist_var.set("\n".join(checklist + ["", final_hint]))

    def _get_long_task_state_path(self, create_dir: bool = True) -> str:
        runtime_dir = os.path.join(self.context["base_dir"], "agent_runtime")
        if create_dir:
            ensure_dir(runtime_dir)
        return os.path.join(runtime_dir, "long_task_state.json")

    def _load_long_task_state(self) -> dict:
        state_path = self._get_long_task_state_path(create_dir=False)
        project_code = self.context["project_info"].get("project_code", "")
        state = load_json(state_path, None)
        if not state:
            return make_default_long_task_state(project_code)
        state.setdefault("project_code", project_code)
        state.setdefault("active_task_key", "")
        state.setdefault("updated_at", "")
        state.setdefault("tasks", [])
        return state

    def _save_long_task_state(self):
        state_path = self._get_long_task_state_path(create_dir=True)
        self.long_task_state["project_code"] = self.context["project_info"].get("project_code", "")
        self.long_task_state["updated_at"] = datetime.now().isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(self.long_task_state, f, ensure_ascii=False, indent=2)

    def _get_long_task_failure_dir(self, create_dir: bool = True) -> str:
        path = os.path.join(self.context["base_dir"], "agent_runtime", "failure_evidence")
        if create_dir:
            ensure_dir(path)
        return path

    def _get_long_task_resume_note_path(self, task_key: str) -> str:
        runtime_dir = os.path.join(self.context["base_dir"], "agent_runtime")
        ensure_dir(runtime_dir)
        return os.path.join(runtime_dir, f"{task_key}_resume_note.txt")

    def _get_long_task_resume_launcher_paths(self, task_key: str) -> Tuple[str, str]:
        runtime_dir = os.path.join(self.context["base_dir"], "agent_runtime")
        ensure_dir(runtime_dir)
        return (
            os.path.join(runtime_dir, f"{task_key}_resume_launcher.cmd"),
            os.path.join(runtime_dir, f"{task_key}_resume_launcher.ps1"),
        )

    def _get_windows_startup_dir(self, create_dir: bool = True) -> str:
        if platform.system() != "Windows":
            return ""
        app_data = os.environ.get("APPDATA", "").strip()
        if not app_data:
            return ""
        startup_dir = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        if create_dir:
            ensure_dir(startup_dir)
        return startup_dir

    def _get_long_task_startup_launcher_path(self, task_key: str) -> str:
        startup_dir = self._get_windows_startup_dir(create_dir=True)
        if not startup_dir:
            return ""
        project_code = self.context["project_info"].get("project_code", "QCC").replace(" ", "_")
        return os.path.join(startup_dir, f"QCC_AutoResume_{project_code}_{task_key}.cmd")

    def _get_preferred_launcher(self) -> str:
        return get_gui_launcher_path(__file__)

    def _write_resume_note(self, record: dict, template: dict):
        note_path = self._get_long_task_resume_note_path(template["key"])
        lines = [
            "QCC Long Task Resume Note",
            f"project_code={self.context['project_info'].get('project_code', '')}",
            f"task_key={template['key']}",
            f"title={template['title']}",
            f"status={record.get('status', '')}",
            f"current={record.get('current', 0)}",
            f"count={record.get('count', 0)}",
            f"resume_count={record.get('resume_count', 0)}",
            f"next_action={record.get('next_action', '')}",
            f"updated_at={record.get('updated_at', '')}",
            f"startup_registered={record.get('startup_registered', False)}",
            f"startup_launcher={record.get('startup_launcher_cmd', '')}",
            "",
            "说明：",
            "1. 标记等待恢复后，Agent 会生成启动脚本，并尝试注册当前用户开机启动。",
            "2. 机器恢复并登录后，Agent 会自动拉起并恢复到对应长任务。",
            "3. 如果自动恢复失败，请进入“压力/循环测试”页检查状态，再决定手动恢复或留证。",
        ]
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        record["resume_note_path"] = note_path
        record["boot_resume_placeholder"] = note_path

    def _write_resume_launchers(self, record: dict, template: dict):
        cmd_path, ps1_path = self._get_long_task_resume_launcher_paths(template["key"])
        launcher_path = self._get_preferred_launcher()
        agent_path = get_launcher_path(__file__)
        config_path = os.path.abspath(self.config_path)
        task_key = template["key"]
        if is_frozen_app():
            cmd_lines = [
                "@echo off",
                "setlocal",
                f"set QCC_AGENT={agent_path}",
                f"set QCC_CONFIG={config_path}",
                f"set QCC_TASK_KEY={task_key}",
                "start \"QCC Auto Resume\" /min \"%QCC_AGENT%\" \"%QCC_CONFIG%\" --resume-long-task \"%QCC_TASK_KEY%\"",
                "exit /b 0",
            ]
            ps1_lines = [
                f"$agent = '{agent_path}'",
                f"$config = '{config_path}'",
                f"$taskKey = '{task_key}'",
                "Start-Process -FilePath $agent -ArgumentList @($config, '--resume-long-task', $taskKey) -WindowStyle Minimized",
            ]
        else:
            cmd_lines = [
                "@echo off",
                "setlocal",
                f"set QCC_PYTHON={launcher_path}",
                f"set QCC_AGENT={agent_path}",
                f"set QCC_CONFIG={config_path}",
                f"set QCC_TASK_KEY={task_key}",
                "start \"QCC Auto Resume\" /min \"%QCC_PYTHON%\" \"%QCC_AGENT%\" \"%QCC_CONFIG%\" --resume-long-task \"%QCC_TASK_KEY%\"",
                "exit /b 0",
            ]
            ps1_lines = [
                f"$python = '{launcher_path}'",
                f"$agent = '{agent_path}'",
                f"$config = '{config_path}'",
                f"$taskKey = '{task_key}'",
                "Start-Process -FilePath $python -ArgumentList @($agent, $config, '--resume-long-task', $taskKey) -WindowStyle Minimized",
            ]
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write("\n".join(cmd_lines))
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ps1_lines))
        record["resume_launcher_cmd"] = cmd_path
        record["resume_launcher_ps1"] = ps1_path
        record["boot_resume_placeholder"] = cmd_path

    def _register_resume_startup(self, record: dict, template: dict):
        startup_cmd = self._get_long_task_startup_launcher_path(template["key"])
        launcher_cmd = record.get("resume_launcher_cmd", "")
        if not startup_cmd or not launcher_cmd:
            record["startup_registered"] = False
            return
        with open(startup_cmd, "w", encoding="utf-8") as f:
            f.write("\n".join([
                "@echo off",
                f"call \"{launcher_cmd}\"",
                "exit /b 0",
            ]))
        record["startup_launcher_cmd"] = startup_cmd
        record["startup_registered"] = True
        record["startup_registered_at"] = datetime.now().isoformat()

    def _remove_if_exists(self, path: str):
        if path and os.path.exists(path):
            os.remove(path)

    def _unregister_resume_startup(self, record: dict):
        startup_cmd = record.get("startup_launcher_cmd", "")
        self._remove_if_exists(startup_cmd)
        record["startup_launcher_cmd"] = ""
        record["startup_registered"] = False
        record["startup_registered_at"] = ""

    def _get_long_task_template(self, task_key: str) -> dict:
        for item in self.long_task_templates:
            if item["key"] == task_key:
                return item
        return self.long_task_templates[0]

    def _supports_runtime_execution(self, template: dict) -> bool:
        return bool(template.get("supports_runtime")) and platform.system() == "Windows"

    def _supports_resume_workflow(self, template: dict) -> bool:
        return bool(template.get("supports_resume_workflow"))

    def _get_long_task_record(self, task_key: str):
        for item in self.long_task_state.get("tasks", []):
            if item.get("key") == task_key:
                return item
        return None

    def _upsert_long_task_record(self, record: dict):
        tasks = self.long_task_state.setdefault("tasks", [])
        for index, item in enumerate(tasks):
            if item.get("key") == record.get("key"):
                tasks[index] = record
                break
        else:
            tasks.append(record)
        self.long_task_state["active_task_key"] = record.get("key", "")
        self._save_long_task_state()

    def _apply_long_task_resume(self, record: dict, template: dict, source: str = "manual"):
        record["status"] = "running"
        record["resume_state"] = "resumed"
        record["resume_count"] = record.get("resume_count", 0) + 1
        record["last_resume_at"] = datetime.now().isoformat()
        record["next_action"] = "record_cycle_result"
        record["current_cycle_started_at"] = record.get("current_cycle_started_at") or datetime.now().isoformat()
        record["current_cycle_error"] = ""
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append(
            {"time": datetime.now().isoformat(), "msg": f"已在恢复后继续任务，来源 {source}。"}
        )
        self._unregister_resume_startup(record)
        self._write_resume_note(record, template)
        self._write_resume_launchers(record, template)
        self._upsert_long_task_record(record)

    def _auto_resume_on_launch(self, task_key: str):
        template = self._get_long_task_template(task_key)
        record = self._get_long_task_record(task_key)
        if not record:
            self.status_var.set(f"自动恢复未执行：未找到任务 {task_key}")
            return
        self.current_long_task_key = task_key
        self.long_task_state["active_task_key"] = task_key
        self._refresh_long_task_tree()
        selected_id = f"longtask-{task_key}"
        if self.long_task_tree.exists(selected_id):
            self.long_task_tree.selection_set(selected_id)
            self.long_task_tree.focus(selected_id)
        if record.get("resume_state") != "waiting_resume":
            self.status_var.set(f"自动恢复跳过：{template['title']} 当前不是等待恢复状态。")
            return
        self._apply_long_task_resume(record, template, source="startup")
        self.status_var.set(f"已自动恢复长任务：{template['title']}")
        self._refresh_long_task_tree()
        messagebox.showinfo(
            "自动续跑已恢复",
            f"{template['title']} 已在开机后自动恢复。\n\n当前进度 {record.get('current', 0)}/{record.get('count', 0)}，请继续现场确认并记录本轮结果。",
        )

    def _build_long_task_summary_text(self) -> str:
        tasks = self.long_task_state.get("tasks", [])
        if not tasks:
            return "尚未创建长任务计划。"
        planned = len([item for item in tasks if item.get("status") == "planned"])
        running = len([item for item in tasks if item.get("status") == "running"])
        paused = len([item for item in tasks if item.get("status") == "paused"])
        completed = len([item for item in tasks if item.get("status") == "completed"])
        runtime_running = len([item for item in tasks if item.get("runtime_status") == "running"])
        return f"已创建 {len(tasks)} 个，计划中 {planned}，执行中 {running}，真实运行 {runtime_running}，暂停 {paused}，完成 {completed}"

    def _schedule_long_task_poll(self):
        if self.long_task_poll_job is not None:
            return
        self.long_task_poll_job = self.root.after(2000, self._poll_long_task_runtime)

    def _cancel_long_task_poll(self):
        if self.long_task_poll_job is None:
            return
        self.root.after_cancel(self.long_task_poll_job)
        self.long_task_poll_job = None

    def _append_runtime_logs(self, record: dict, runtime_logs: list):
        start_index = record.get("runtime_log_count", 0)
        new_logs = runtime_logs[start_index:]
        if not new_logs:
            return
        record.setdefault("logs", [])
        for item in new_logs:
            record["logs"].append({"time": item.get("time", datetime.now().isoformat()), "msg": item.get("msg", "")})
        record["runtime_log_count"] = len(runtime_logs)

    def _sync_runtime_status(self, record: dict) -> bool:
        task_id = record.get("runtime_task_id")
        if not task_id:
            return False
        runtime_status = self.stress_manager.get_status(task_id)
        if runtime_status.get("error"):
            record["runtime_status"] = "missing"
            record["runtime_error"] = runtime_status.get("error", "")
            record["updated_at"] = datetime.now().isoformat()
            return False

        changed = False
        for key in ("status", "current", "success", "fail"):
            new_value = runtime_status.get(key, record.get(key))
            if record.get(key) != new_value:
                record[key] = new_value
                changed = True
        record["runtime_status"] = runtime_status.get("status", "")
        record["runtime_error"] = runtime_status.get("error", "")
        record["runtime_duration_s"] = runtime_status.get("duration_s", 0)
        record["last_result"] = "FAIL" if runtime_status.get("fail", 0) else "PASS" if runtime_status.get("success", 0) else record.get("last_result", "")
        self._append_runtime_logs(record, runtime_status.get("logs", []))
        if runtime_status.get("status") == "completed":
            record["next_action"] = "manual_review"
        record["updated_at"] = datetime.now().isoformat()
        return changed or runtime_status.get("status") == "running"

    def _poll_long_task_runtime(self):
        self.long_task_poll_job = None
        has_running = False
        changed = False
        for record in self.long_task_state.get("tasks", []):
            if not record.get("runtime_task_id"):
                continue
            runtime_status = self.stress_manager.get_status(record["runtime_task_id"])
            if runtime_status.get("error"):
                continue
            if runtime_status.get("status") == "running":
                has_running = True
            if self._sync_runtime_status(record):
                changed = True
        if changed:
            self._save_long_task_state()
            self._refresh_long_task_tree()
        if has_running:
            self._schedule_long_task_poll()

    def _refresh_long_task_tree(self):
        state_path = self._get_long_task_state_path(create_dir=False)
        self.long_task_summary_var.set(self._build_long_task_summary_text())
        self.long_task_state_path_var.set(f"状态文件：{state_path}")
        for item in self.long_task_tree.get_children():
            self.long_task_tree.delete(item)
        for template in self.long_task_templates:
            record = self._get_long_task_record(template["key"])
            status = record.get("status", "未创建") if record else "未创建"
            current = record.get("current", 0) if record else 0
            count = record.get("count", template["default_count"]) if record else template["default_count"]
            self.long_task_tree.insert(
                "",
                "end",
                iid=f"longtask-{template['key']}",
                text=template["title"],
                values=(status, f"{current}/{count}"),
            )
        selected_id = f"longtask-{self.current_long_task_key}"
        if self.long_task_tree.exists(selected_id):
            self.long_task_tree.selection_set(selected_id)
            self.long_task_tree.focus(selected_id)
        self._update_long_task_panel()
        self._update_overview_tab()
        self._update_export_page()

    def on_long_task_select(self):
        selection = self.long_task_tree.selection()
        if not selection:
            return
        self.current_long_task_key = selection[0].replace("longtask-", "", 1)
        self.long_task_state["active_task_key"] = self.current_long_task_key
        self._update_long_task_panel()

    def _update_long_task_panel(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        count = record.get("count", template["default_count"]) if record else template["default_count"]
        interval = record.get("interval", template["default_interval"]) if record else template["default_interval"]
        self.long_task_count_var.set(str(count))
        self.long_task_interval_var.set(str(interval))
        if record:
            runtime_label = record.get("runtime_status", "-")
            resume_label = record.get("resume_state", "-")
            self.long_task_status_var.set(
                f"当前状态：{record.get('status', 'planned')} | 进度 {record.get('current', 0)}/{record.get('count', count)} | "
                f"成功 {record.get('success', 0)} | 失败 {record.get('fail', 0)} | 真实状态 {runtime_label} | 恢复状态 {resume_label}"
            )
        else:
            self.long_task_status_var.set("当前状态：尚未创建计划，可先填写轮次和间隔后创建。")
        if record and record.get("resume_state") == "waiting_resume":
            self.long_task_resume_var.set(
                f"恢复继续：当前等待机器恢复，下一步 {record.get('next_action', 'resume_continue')}，"
                f"续跑说明文件 {record.get('resume_note_path', '-')}，"
                f"开机启动 {'已注册' if record.get('startup_registered') else '未注册'}"
            )
        elif record and record.get("resume_state") == "resume_failed":
            self.long_task_resume_var.set(
                f"恢复继续：最近一次恢复失败，失败证据 {len(record.get('failure_evidence', []))} 个，请检查日志与截图。"
            )
        elif record and record.get("resume_state") == "resumed":
            self.long_task_resume_var.set(
                f"恢复继续：已恢复 {record.get('resume_count', 0)} 次，最近恢复时间 {record.get('last_resume_at', '-')}"
            )
        else:
            self.long_task_resume_var.set("恢复继续：当前未进入等待恢复状态。")

        lines = [
            f"任务名称：{template['title']}",
            f"任务类型：{template['task_type']}",
            f"说明：{template['description']}",
            f"默认轮次：{template['default_count']}",
            f"默认间隔：{template['default_interval']} 秒",
            f"需要管理员权限：{'是' if template['requires_admin'] else '否'}",
            f"支持恢复继续：{'是' if template['supports_resume'] else '否'}",
            f"支持真实启动：{'是' if self._supports_runtime_execution(template) else '否'}",
            f"支持恢复骨架：{'是' if self._supports_resume_workflow(template) else '否'}",
        ]
        if record:
            lines.extend(
                [
                    "",
                    "当前计划：",
                    f"- 计划轮次：{record.get('count', 0)}",
                    f"- 间隔秒数：{record.get('interval', 0)}",
                    f"- 当前轮次：{record.get('current', 0)}",
                    f"- 成功次数：{record.get('success', 0)}",
                    f"- 失败次数：{record.get('fail', 0)}",
                    f"- 最近结果：{record.get('last_result', '-')}",
                    f"- 真实任务ID：{record.get('runtime_task_id', '-')}",
                    f"- 真实运行状态：{record.get('runtime_status', '-')}",
                    f"- 真实运行时长：{record.get('runtime_duration_s', 0)} 秒",
                    f"- 恢复状态：{record.get('resume_state', '-')}",
                    f"- 恢复次数：{record.get('resume_count', 0)}",
                    f"- 下一步动作：{record.get('next_action', '-')}",
                    f"- 续跑占位文件：{record.get('resume_note_path', '-')}",
                    f"- 启动脚本 CMD：{record.get('resume_launcher_cmd', '-')}",
                    f"- 启动脚本 PS1：{record.get('resume_launcher_ps1', '-')}",
                    f"- 开机启动脚本：{record.get('startup_launcher_cmd', '-')}",
                    f"- 已注册开机启动：{'是' if record.get('startup_registered') else '否'}",
                    f"- 当前轮开始：{record.get('current_cycle_started_at', '-')}",
                    f"- 当前轮结束：{record.get('current_cycle_ended_at', '-')}",
                    f"- 当前轮错误：{record.get('current_cycle_error', '-')}",
                ]
            )
            if record.get("runtime_error"):
                lines.append(f"- 运行错误：{record.get('runtime_error')}")
            failure_evidence = record.get("failure_evidence", [])
            if failure_evidence:
                lines.append(f"- 失败证据数：{len(failure_evidence)}")
            logs = record.get("logs", [])
            if logs:
                lines.extend(["", "最近日志："])
                for item in logs[-8:]:
                    lines.append(f"- {item.get('time', '')} {item.get('msg', '')}")
        else:
            lines.extend(["", "当前还没有状态记录。"])
        self._update_text_widget(self.long_task_detail_text, "\n".join(lines))

    def _read_positive_int(self, raw_value: str, field_label: str) -> int:
        try:
            value = int(raw_value)
        except ValueError:
            raise ValueError(f"{field_label}必须是整数。")
        if value <= 0:
            raise ValueError(f"{field_label}必须大于 0。")
        return value

    def upsert_long_task_plan(self):
        template = self._get_long_task_template(self.current_long_task_key)
        try:
            count = self._read_positive_int(self.long_task_count_var.get().strip(), "计划轮次")
            interval = self._read_positive_int(self.long_task_interval_var.get().strip(), "间隔秒数")
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc))
            return

        record = self._get_long_task_record(self.current_long_task_key) or {
            "key": template["key"],
            "task_type": template["task_type"],
            "title": template["title"],
            "created_at": datetime.now().isoformat(),
            "logs": [],
            "current": 0,
            "success": 0,
            "fail": 0,
            "last_result": "",
            "runtime_task_id": "",
            "runtime_status": "",
            "runtime_duration_s": 0,
            "runtime_error": "",
            "runtime_log_count": 0,
            "resume_state": "",
            "resume_count": 0,
            "next_action": "",
            "resume_note_path": "",
            "resume_launcher_cmd": "",
            "resume_launcher_ps1": "",
            "startup_launcher_cmd": "",
            "startup_registered": False,
            "boot_resume_placeholder": "",
            "failure_evidence": [],
            "current_cycle_started_at": "",
            "current_cycle_ended_at": "",
            "current_cycle_error": "",
            "cycle_history": [],
        }
        record.update(
            {
                "count": count,
                "interval": interval,
                "status": "planned" if record.get("current", 0) == 0 else record.get("status", "planned"),
                "updated_at": datetime.now().isoformat(),
            }
        )
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": f"已更新任务计划：轮次 {count}，间隔 {interval} 秒"})
        self._upsert_long_task_record(record)
        self.status_var.set(f"已更新长任务计划：{template['title']}")
        self._refresh_long_task_tree()

    def start_long_task_plan(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return
        if record.get("status") == "completed":
            if not messagebox.askyesno("提示", "该任务已完成，是否重新标记为执行中？"):
                return
        record["status"] = "running"
        record["started_at"] = record.get("started_at") or datetime.now().isoformat()
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": "已标记开始执行，等待记录轮次结果。"})
        self._upsert_long_task_record(record)
        self.status_var.set(f"已开始记录长任务：{template['title']}")
        self._refresh_long_task_tree()

    def start_long_task_runtime(self):
        template = self._get_long_task_template(self.current_long_task_key)
        if not self._supports_runtime_execution(template):
            messagebox.showinfo("提示", "当前任务类型暂未接入真实启动，请继续使用计划记录模式。")
            return
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return
        if record.get("runtime_task_id") and record.get("runtime_status") == "running":
            messagebox.showinfo("提示", "当前任务已在真实运行中，请先刷新状态。")
            return

        result = self.stress_manager.start(template["task_type"], record.get("count", 1), record.get("interval", 60))
        if result.get("error"):
            messagebox.showerror("启动失败", result.get("error", "未知错误"))
            return

        record["status"] = "running"
        record["runtime_task_id"] = result.get("task_id", "")
        record["runtime_status"] = "running"
        record["runtime_duration_s"] = 0
        record["runtime_error"] = ""
        record["runtime_log_count"] = 0
        record["resume_state"] = ""
        record["next_action"] = "runtime_running"
        record["started_at"] = datetime.now().isoformat()
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append(
            {"time": datetime.now().isoformat(), "msg": f"已真实启动任务，task_id={record['runtime_task_id']}"}
        )
        self._upsert_long_task_record(record)
        self.status_var.set(f"已真实启动长任务：{template['title']}")
        self._refresh_long_task_tree()
        self._schedule_long_task_poll()

    def refresh_long_task_runtime(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record or not record.get("runtime_task_id"):
            messagebox.showinfo("提示", "当前任务还没有真实运行实例。")
            return
        self._sync_runtime_status(record)
        self._save_long_task_state()
        self._refresh_long_task_tree()
        self.status_var.set(f"已刷新长任务状态：{template['title']}")
        if record.get("runtime_status") == "running":
            self._schedule_long_task_poll()

    def stop_long_task_runtime(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record or not record.get("runtime_task_id"):
            messagebox.showinfo("提示", "当前任务没有可停止的真实运行实例。")
            return
        result = self.stress_manager.stop(record["runtime_task_id"])
        if result.get("error"):
            messagebox.showerror("停止失败", result.get("error", "未知错误"))
            return
        self._sync_runtime_status(record)
        record["status"] = "stopped"
        record["runtime_status"] = "stopped"
        record["next_action"] = "manual_review"
        record["current_cycle_ended_at"] = datetime.now().isoformat()
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": "已停止真实运行任务。"})
        self._upsert_long_task_record(record)
        self.status_var.set(f"已停止长任务：{template['title']}")
        self._refresh_long_task_tree()

    def mark_long_task_resume_pending(self):
        template = self._get_long_task_template(self.current_long_task_key)
        if not self._supports_resume_workflow(template):
            messagebox.showinfo("提示", "当前任务类型不需要恢复继续流程。")
            return
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return
        next_cycle = min(record.get("current", 0) + 1, record.get("count", 1))
        record["status"] = "waiting_resume"
        record["resume_state"] = "waiting_resume"
        record["next_action"] = f"恢复后继续第 {next_cycle} 轮"
        record["last_resume_request_at"] = datetime.now().isoformat()
        record["current_cycle_started_at"] = datetime.now().isoformat()
        record["current_cycle_ended_at"] = ""
        record["current_cycle_error"] = ""
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append(
            {"time": datetime.now().isoformat(), "msg": f"已标记等待恢复，目标继续第 {next_cycle} 轮。"}
        )
        self._write_resume_note(record, template)
        self._write_resume_launchers(record, template)
        self._register_resume_startup(record, template)
        self._write_resume_note(record, template)
        self._upsert_long_task_record(record)
        self.status_var.set(f"已标记等待恢复：{template['title']}")
        self._refresh_long_task_tree()

    def resume_long_task_after_recovery(self):
        template = self._get_long_task_template(self.current_long_task_key)
        if not self._supports_resume_workflow(template):
            messagebox.showinfo("提示", "当前任务类型不需要恢复继续流程。")
            return
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return
        self._apply_long_task_resume(record, template, source="manual")
        self.status_var.set(f"已恢复继续：{template['title']}")
        self._refresh_long_task_tree()

    def capture_long_task_failure(self):
        template = self._get_long_task_template(self.current_long_task_key)
        if not self._supports_resume_workflow(template):
            messagebox.showinfo("提示", "当前任务类型不需要恢复失败留证。")
            return
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return

        failure_dir = self._get_long_task_failure_dir(create_dir=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        evidence_paths = []
        if platform.system() == "Windows":
            screenshot_path = os.path.join(failure_dir, f"{template['key']}_{timestamp}.png")
            screenshot_result = capture_windows_screenshot(screenshot_path)
            if screenshot_result.get("success"):
                evidence_paths.append(screenshot_path)
        note_path = os.path.join(failure_dir, f"{template['key']}_{timestamp}.txt")
        note_lines = [
            f"task={template['title']}",
            f"time={datetime.now().isoformat()}",
            f"status={record.get('status', '')}",
            f"current={record.get('current', 0)}",
            f"count={record.get('count', 0)}",
            f"next_action={record.get('next_action', '')}",
            f"current_cycle_started_at={record.get('current_cycle_started_at', '')}",
            f"current_cycle_ended_at={datetime.now().isoformat()}",
            f"current_cycle_error={record.get('current_cycle_error', 'recovery_failed') or 'recovery_failed'}",
            "note=恢复失败，请补充现场现象、错误码和设备状态。",
        ]
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("\n".join(note_lines))
        evidence_paths.append(note_path)
        record.setdefault("failure_evidence", []).extend(evidence_paths)
        record["resume_state"] = "resume_failed"
        record["status"] = "blocked"
        record["next_action"] = "manual_investigation"
        record["current_cycle_ended_at"] = datetime.now().isoformat()
        record["current_cycle_error"] = record.get("current_cycle_error") or "recovery_failed"
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": f"已记录恢复失败证据 {len(evidence_paths)} 个。"})
        self._unregister_resume_startup(record)
        self._write_resume_note(record, template)
        self._write_resume_launchers(record, template)
        self._upsert_long_task_record(record)
        self.status_var.set(f"已记录恢复失败证据：{template['title']}")
        self._refresh_long_task_tree()

    def record_long_task_step(self, success: bool):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "请先创建长任务计划。")
            return
        if self._supports_runtime_execution(template) and record.get("runtime_status") == "running":
            messagebox.showinfo("提示", "当前任务正在真实运行，请使用“刷新运行状态”查看结果。")
            return
        if record.get("status") not in ("running", "planned", "paused"):
            messagebox.showwarning("提示", "当前任务状态不允许继续记录，请先检查状态。")
            return
        if record.get("status") != "running":
            record["status"] = "running"
        record["current_cycle_started_at"] = record.get("current_cycle_started_at") or datetime.now().isoformat()
        record["current"] = min(record.get("current", 0) + 1, record.get("count", 1))
        result_label = "PASS" if success else "FAIL"
        if success:
            record["success"] = record.get("success", 0) + 1
        else:
            record["fail"] = record.get("fail", 0) + 1
        record["last_result"] = result_label
        record["current_cycle_ended_at"] = datetime.now().isoformat()
        record["current_cycle_error"] = "" if success else (record.get("current_cycle_error") or "manual_fail")
        record.setdefault("cycle_history", []).append(
            {
                "cycle_no": record["current"],
                "result": result_label,
                "started_at": record.get("current_cycle_started_at", ""),
                "ended_at": record.get("current_cycle_ended_at", ""),
                "error": record.get("current_cycle_error", ""),
            }
        )
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append(
            {"time": datetime.now().isoformat(), "msg": f"第 {record['current']} 轮记录完成，结果 {result_label}"}
        )
        if record["current"] >= record.get("count", 1):
            record["status"] = "completed"
            record["completed_at"] = datetime.now().isoformat()
            record["logs"].append({"time": datetime.now().isoformat(), "msg": "任务计划轮次已全部完成。"})
            record["next_action"] = "manual_review"
            record["resume_state"] = ""
            if self._supports_resume_workflow(template):
                self._unregister_resume_startup(record)
                self._write_resume_note(record, template)
        elif self._supports_resume_workflow(template):
            record["next_action"] = "wait_resume_or_continue"
        record["current_cycle_started_at"] = ""
        if success:
            record["current_cycle_error"] = ""
        self._upsert_long_task_record(record)
        self.status_var.set(f"已记录长任务轮次：{template['title']} {result_label}")
        self._refresh_long_task_tree()

    def pause_long_task_plan(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showwarning("提示", "当前没有可暂停的任务计划。")
            return
        record["status"] = "paused"
        record["updated_at"] = datetime.now().isoformat()
        record["next_action"] = "manual_resume"
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": "任务已暂停，可稍后从状态文件恢复继续。"})
        self._upsert_long_task_record(record)
        self.status_var.set(f"已暂停长任务：{template['title']}")
        self._refresh_long_task_tree()

    def clear_long_task_resume_artifacts(self):
        template = self._get_long_task_template(self.current_long_task_key)
        record = self._get_long_task_record(self.current_long_task_key)
        if not record:
            messagebox.showinfo("提示", "当前没有可清理的续跑信息。")
            return
        self._unregister_resume_startup(record)
        paths = [
            record.get("resume_note_path", ""),
            record.get("resume_launcher_cmd", ""),
            record.get("resume_launcher_ps1", ""),
            record.get("startup_launcher_cmd", ""),
        ]
        for path in paths:
            self._remove_if_exists(path)
        record["resume_note_path"] = ""
        record["resume_launcher_cmd"] = ""
        record["resume_launcher_ps1"] = ""
        record["startup_launcher_cmd"] = ""
        record["startup_registered"] = False
        record["startup_registered_at"] = ""
        record["boot_resume_placeholder"] = ""
        if record.get("resume_state") in ("waiting_resume", "resumed", "resume_failed"):
            record["resume_state"] = ""
        record["updated_at"] = datetime.now().isoformat()
        record.setdefault("logs", []).append({"time": datetime.now().isoformat(), "msg": "已清理续跑文件和开机启动注册。"})
        self._upsert_long_task_record(record)
        self.status_var.set(f"已清理续跑文件：{template['title']}")
        self._refresh_long_task_tree()

    def restore_long_task_state(self):
        self.long_task_state = self._load_long_task_state()
        active_key = self.long_task_state.get("active_task_key")
        if active_key:
            self.current_long_task_key = active_key
        self.status_var.set("已从状态文件恢复长任务计划。")
        self._refresh_long_task_tree()
        if any(item.get("runtime_status") == "running" for item in self.long_task_state.get("tasks", [])):
            self._schedule_long_task_poll()

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, item in enumerate(self.context["test_items"]):
            result = self.results[idx]
            mode_label = format_execution_mode(resolve_item_identity(item, self.context.get("script_mapping")).get("execution_mode"))
            self.tree.insert(
                "",
                "end",
                iid=f"item-{idx}",
                text=item.get("test_name", f"测试项 {idx + 1}"),
                values=(item.get("category", ""), mode_label, result.get("verdict", "NotTested")),
            )
        self._update_summary()

    def _set_detail_text(self, text: str):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _normalize_path_list(self, raw_text: str) -> list:
        unique = []
        seen = set()
        for item in raw_text.split(","):
            value = item.strip()
            if not value:
                continue
            normalized = value.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(value)
        return unique

    def _set_path_var(self, var: tk.StringVar, paths: list):
        var.set(", ".join(self._normalize_path_list(", ".join(paths))))

    def _append_paths(self, var: tk.StringVar, new_paths: tuple):
        existing = self._normalize_path_list(var.get())
        combined = existing + [path for path in new_paths if path]
        self._set_path_var(var, combined)
        self._update_attachment_hint()
        self._update_attachment_preview()

    def _update_attachment_hint(self):
        evidence_count = len(self._normalize_path_list(self.evidence_var.get()))
        logs_count = len(self._normalize_path_list(self.logs_var.get()))
        if not evidence_count and not logs_count:
            self.attachment_hint_var.set("当前未选择证据或日志文件。")
            return
        self.attachment_hint_var.set(f"当前已选择证据 {evidence_count} 个，日志 {logs_count} 个。")

    def _update_attachment_preview(self):
        evidence_names = [os.path.basename(item) for item in self._normalize_path_list(self.evidence_var.get())]
        log_names = [os.path.basename(item) for item in self._normalize_path_list(self.logs_var.get())]

        preview_lines = []
        if evidence_names:
            preview_lines.append("证据: " + "；".join(evidence_names[:4]) + ("；..." if len(evidence_names) > 4 else ""))
        if log_names:
            preview_lines.append("日志: " + "；".join(log_names[:4]) + ("；..." if len(log_names) > 4 else ""))
        if not preview_lines:
            self.attachment_preview_var.set("附件预览：暂无")
        else:
            self.attachment_preview_var.set("附件预览：\n" + "\n".join(preview_lines))

    def _current_tree_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return int(selection[0].split("-")[1])

    def on_tree_select(self):
        new_index = self._current_tree_index()
        if new_index is None:
            return
        if self.current_index is not None and self.current_index != new_index:
            self.save_current_item(silent=True)
        self.current_index = new_index
        self.load_current_item()

    def load_current_item(self):
        if self.current_index is None:
            return
        item = self.context["test_items"][self.current_index]
        result = self.results[self.current_index]
        auto_result = self.auto_results.get(self.current_index, {})
        resolved = resolve_item_identity(item, self.context.get("script_mapping"))
        execution_mode = resolved.get("execution_mode", "manual")

        details = [
            f"名称：{item.get('test_name', '-')}",
            f"分类：{item.get('category', '-')}",
            f"分类编码：{item.get('category_code', '-')}",
            f"序号：{item.get('item_no', '-')}",
            f"脚本ID：{resolved.get('display_id', '-')}",
            f"执行模式：{format_execution_mode(execution_mode)}",
            "",
            "测试步骤：",
            item.get("condition_desc", "未提供"),
            "",
            "判定标准：",
            item.get("criteria", "未提供"),
        ]
        self._set_detail_text("\n".join(details))

        validation_text = "尚未完成环境采集。"
        if self.validation:
            validation_text = (
                f"环境校验结论：{self.validation.get('conclusion', '-')}"
                f"（通过 {self.validation.get('passed', 0)} / {self.validation.get('total', 0)}）"
            )
        self.detail_validation_var.set(validation_text)

        if auto_result:
            auto_text = (
                f"执行模式：{format_execution_mode(auto_result.get('execution_mode', execution_mode))}\n"
                f"是否已执行脚本：{'是' if auto_result.get('auto_executed') else '否'}\n"
                f"建议结果：{auto_result.get('suggested_verdict', '-')}\n"
                f"耗时：{auto_result.get('duration_ms', 0)} ms\n"
                f"说明：{auto_result.get('note', '')}"
            )
            metrics = auto_result.get("metrics") or {}
            if metrics:
                metric_lines = [f"{k}: {v}" for k, v in metrics.items()]
                auto_text += "\n自动数据：\n- " + "\n- ".join(metric_lines[:12])
        else:
            if execution_mode == "manual":
                auto_text = "执行模式：人工\n是否已执行脚本：否\n说明：当前项为人工项，不会自动执行脚本。"
            elif execution_mode == "semi_auto":
                auto_text = "执行模式：半自动\n是否已执行脚本：否\n说明：当前项支持半自动建议，执行后仍需人工确认最终结果。"
            else:
                auto_text = "执行模式：自动\n是否已执行脚本：否\n说明：尚未执行自动化建议。"
        self.detail_auto_var.set(auto_text)

        self.verdict_var.set(result.get("verdict", "NotTested"))
        self.comment_text.delete("1.0", tk.END)
        self.comment_text.insert("1.0", result.get("comment", ""))
        self.evidence_var.set(", ".join(result.get("evidence", [])))
        self.logs_var.set(", ".join(result.get("log_files", [])))
        self._update_attachment_hint()
        self._update_attachment_preview()

    def save_current_item(self, silent: bool = False):
        if self.current_index is None:
            return False
        verdict = self.verdict_var.get() or "NotTested"
        comment = self.comment_text.get("1.0", tk.END).strip()
        if verdict in ("Fail", "Blocked") and not comment:
            if not silent:
                messagebox.showwarning("提示", "Fail 或 Blocked 项必须填写备注。")
            return False

        result = self.results[self.current_index]
        auto_result = self.auto_results.get(self.current_index, {})
        result.update({
            "verdict": verdict,
            "comment": comment,
            "evidence": self._normalize_path_list(self.evidence_var.get()),
            "log_files": self._normalize_path_list(self.logs_var.get()),
            "raw_output": auto_result.get("raw_output", result.get("raw_output", "")),
            "metrics": auto_result.get("metrics", result.get("metrics", {})),
            "duration_ms": auto_result.get("duration_ms", result.get("duration_ms", 0)),
            "executed_at": datetime.now().isoformat(),
        })
        item_id = f"item-{self.current_index}"
        self.tree.set(item_id, "verdict", verdict)
        self._update_summary()
        if not silent:
            self.status_var.set(f"已保存当前测试项：{result.get('test_name', '')}")
        return True

    def choose_evidence_files(self):
        file_paths = filedialog.askopenfilenames(
            title="选择证据文件",
            initialdir=self.context["base_dir"],
            filetypes=[("所有文件", "*.*")],
        )
        if not file_paths:
            return
        self._append_paths(self.evidence_var, file_paths)
        self.status_var.set(f"已追加 {len(file_paths)} 个证据文件。")

    def clear_evidence_files(self):
        self.evidence_var.set("")
        self._update_attachment_hint()
        self._update_attachment_preview()
        self.status_var.set("已清空当前测试项证据文件。")

    def choose_log_files(self):
        file_paths = filedialog.askopenfilenames(
            title="选择日志文件",
            initialdir=self.context["base_dir"],
            filetypes=[("日志与文本", "*.log *.txt *.json *.xml *.csv *.html"), ("所有文件", "*.*")],
        )
        if not file_paths:
            return
        self._append_paths(self.logs_var, file_paths)
        self.status_var.set(f"已追加 {len(file_paths)} 个日志文件。")

    def clear_log_files(self):
        self.logs_var.set("")
        self._update_attachment_hint()
        self._update_attachment_preview()
        self.status_var.set("已清空当前测试项日志文件。")

    def capture_screenshot_for_current_item(self):
        if platform.system() != "Windows":
            messagebox.showinfo("提示", "当前截图按钮仅在 Windows 环境下可用。")
            return
        screenshot_dir = os.path.join(self.context["base_dir"], "captured_screenshots")
        ensure_dir(screenshot_dir)
        item = self.context["test_items"][self.current_index] if self.current_index is not None else {}
        item_no = item.get("item_no", "item")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(screenshot_dir, f"{item_no}_{timestamp}.png")
        result = capture_windows_screenshot(save_path)
        if not result.get("success"):
            messagebox.showerror("截图失败", result.get("error", "未知错误"))
            return
        self._append_paths(self.evidence_var, (save_path,))
        self.status_var.set(f"已保存截图并追加到证据：{os.path.basename(save_path)}")

    def choose_package(self):
        path = filedialog.askopenfilename(
            title="选择 config.json",
            initialdir=os.path.dirname(self.config_path),
            filetypes=[("配置文件", "config.json"), ("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self._cancel_long_task_poll()
            self.config_path = path
            self.context = load_package_context(path)
            self.system_info = {}
            self.validation = {}
            self.results = [make_default_result(item, self.context.get("script_mapping")) for item in self.context["test_items"]]
            self.auto_results = {}
            self.current_index = None
            self.long_task_state = self._load_long_task_state()
            self.current_long_task_key = self.long_task_state.get("active_task_key") or self.long_task_templates[0]["key"]
            self.last_export_result = None
            self.tester_var.set(self.context["project_info"].get("tester") or socket.gethostname())
            self.export_result_var.set("尚未导出结果包。")
            self._refresh_project_info()
            self._refresh_tree()
            if self.context["test_items"]:
                self.tree.selection_set("item-0")
                self.on_tree_select()
            if any(item.get("runtime_status") == "running" for item in self.long_task_state.get("tasks", [])):
                self._schedule_long_task_poll()
            self.status_var.set("已切换测试包。")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def collect_system_info(self):
        self.status_var.set("正在采集系统信息，请稍候...")

        def worker():
            try:
                system_info = self.collector.collect()
                validation = self.collector.validate(system_info, self.context["expected_config"])
                self.root.after(0, lambda: self._after_collect(system_info, validation))
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("采集失败", str(exc)))
                self.root.after(0, lambda: self.status_var.set("系统信息采集失败。"))

        threading.Thread(target=worker, daemon=True).start()

    def _after_collect(self, system_info: dict, validation: dict):
        self.system_info = system_info
        self.validation = validation
        self._update_system_info_panel()
        self._update_summary()
        self.status_var.set("系统信息采集完成，可继续执行测试项。")
        if self.current_index is not None:
            self.load_current_item()

    def run_selected_auto(self):
        if self.current_index is None:
            messagebox.showwarning("提示", "请先选择测试项。")
            return
        current_index = self.current_index
        item = self.context["test_items"][current_index]
        self.status_var.set(f"正在执行：{item.get('test_name', '')}")

        def worker():
            try:
                timeout = self.context["test_config"].get("timeout", 30)
                auto_result = build_auto_result(
                    item,
                    self.engine,
                    self.context["expected_config"],
                    timeout,
                    self.context.get("script_mapping"),
                )
                self.root.after(0, lambda: self._after_auto(current_index, auto_result))
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("执行失败", str(exc)))
                self.root.after(0, lambda: self.status_var.set("自动执行失败。"))

        threading.Thread(target=worker, daemon=True).start()

    def _after_auto(self, index: int, auto_result: dict):
        self.auto_results[index] = auto_result
        if self.current_index == index:
            self.load_current_item()
        self.status_var.set(f"自动执行完成：{self.context['test_items'][index].get('test_name', '')}")

    def run_all_auto(self):
        self.status_var.set("正在批量执行全部可自动执行项，请稍候...")

        def worker():
            timeout = self.context["test_config"].get("timeout", 30)
            total_updated = 0
            semi_auto_pending = 0
            for index, item in enumerate(self.context["test_items"]):
                auto_result = build_auto_result(
                    item,
                    self.engine,
                    self.context["expected_config"],
                    timeout,
                    self.context.get("script_mapping"),
                )
                self.auto_results[index] = auto_result
                if auto_result.get("execution_mode") == "semi_auto":
                    semi_auto_pending += 1
                if auto_result.get("execution_mode") != "auto":
                    continue
                if auto_result.get("suggested_verdict") in ("Pass", "Fail", "NA"):
                    result = self.results[index]
                    if result.get("verdict") in ("NotTested", "Manual"):
                        result["verdict"] = auto_result["suggested_verdict"]
                        result["raw_output"] = auto_result.get("raw_output", "")
                        result["metrics"] = auto_result.get("metrics", {})
                        result["duration_ms"] = auto_result.get("duration_ms", 0)
                        if not result.get("comment"):
                            result["comment"] = auto_result.get("note", "")
                        total_updated += 1
            self.root.after(0, lambda: self._after_run_all(total_updated, semi_auto_pending))

        threading.Thread(target=worker, daemon=True).start()

    def _after_run_all(self, total_updated: int, semi_auto_pending: int):
        self._refresh_tree()
        if self.current_index is not None:
            self.load_current_item()
        self.status_var.set(f"批量自动执行完成，已自动回填 {total_updated} 项，另有 {semi_auto_pending} 项半自动待人工确认。")

    def apply_suggested_result(self):
        if self.current_index is None:
            return
        auto_result = self.auto_results.get(self.current_index)
        if not auto_result:
            messagebox.showinfo("提示", "当前测试项还没有自动建议，请先执行自动测试。")
            return
        suggested = auto_result.get("suggested_verdict", "Manual")
        self.verdict_var.set(suggested if suggested in VALID_VERDICTS else "Manual")
        if not self.comment_text.get("1.0", tk.END).strip():
            self.comment_text.delete("1.0", tk.END)
            self.comment_text.insert("1.0", auto_result.get("note", ""))
        self.status_var.set("已采用自动建议，请确认后保存。")

    def _jump_to_index(self, index: int):
        item_id = f"item-{index}"
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)
            self.on_tree_select()

    def _open_items_window(self, title: str, items: list):
        if not items:
            messagebox.showinfo("提示", f"{title} 当前为空。")
            return
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("880x420")
        win.transient(self.root)

        columns = ("category", "mode", "item_no", "verdict")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.heading("category", text="分类")
        tree.heading("mode", text="模式")
        tree.heading("item_no", text="序号")
        tree.heading("verdict", text="结果")
        tree.column("category", width=140, anchor="w")
        tree.column("mode", width=80, anchor="center")
        tree.column("item_no", width=90, anchor="center")
        tree.column("verdict", width=90, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=12)

        index_map = {}
        for item in items:
            idx = self.results.index(item)
            iid = f"row-{idx}"
            mode_label = format_execution_mode(item.get("execution_mode", "manual"))
            tree.insert(iid=iid, parent="", index="end", values=(item.get("category", ""), mode_label, item.get("item_no", ""), item.get("verdict", "")), text=item.get("test_name", ""))
            tree.set(iid, "category", item.get("category", ""))
            tree.set(iid, "mode", mode_label)
            tree.set(iid, "item_no", item.get("item_no", ""))
            tree.set(iid, "verdict", item.get("verdict", ""))
            tree.item(iid, text=item.get("test_name", ""))
            index_map[iid] = idx

        tree["show"] = "tree headings"
        tree.heading("#0", text="测试项")
        tree.column("#0", width=420, anchor="w")

        button_bar = ttk.Frame(win)
        button_bar.pack(fill="x", padx=12, pady=(0, 12))

        def jump_selected():
            selection = tree.selection()
            if not selection:
                return
            idx = index_map.get(selection[0])
            if idx is None:
                return
            self._jump_to_index(idx)
            win.destroy()

        ttk.Button(button_bar, text="跳转到该测试项", command=jump_selected).pack(side="right")

    def open_summary_window(self):
        self.save_current_item(silent=True)
        precheck = build_precheck(self.results)
        summary = build_summary(self.results)
        mode_buckets = self._get_execution_mode_buckets()

        win = tk.Toplevel(self.root)
        win.title("结果汇总与导出前检查")
        win.geometry("980x640")
        win.transient(self.root)

        container = ttk.Frame(win, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="结果汇总", font=("Microsoft YaHei", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text=(
                f"总数 {summary.get('total', 0)} | 未测 {summary.get('NotTested', 0)} | "
                f"Pass {summary.get('Pass', 0)} | Fail {summary.get('Fail', 0)} | "
                f"NA {summary.get('NA', 0)} | Blocked {summary.get('Blocked', 0)} | "
                f"Manual {summary.get('Manual', 0)} | "
                f"自动 {len(mode_buckets['auto'])} | 半自动 {len(mode_buckets['semi_auto'])} | 人工 {len(mode_buckets['manual'])}"
            ),
            foreground="#1f3b5b",
        ).grid(row=1, column=0, sticky="w", pady=(6, 12))

        ttk.Label(container, text="导出前检查", font=("Microsoft YaHei", 14, "bold")).grid(row=2, column=0, sticky="w")

        issues = [
            ("未测试项", precheck["not_tested"], "导出前建议全部处理或明确设为 NA / Blocked。"),
            ("Fail 缺备注", precheck["fail_without_comment"], "Fail 项建议必须写明现象、步骤或定位信息。"),
            ("Fail 缺证据", precheck["fail_without_evidence"], "Fail 项建议补充截图、日志或外部工具输出。"),
            ("Blocked 缺备注", precheck["blocked_without_comment"], "Blocked 项建议说明阻塞原因。"),
            ("半自动待确认", mode_buckets["semi_auto_pending"], "这些项已拿到脚本建议，但仍需结合现场现象人工确认最终结果。"),
            ("人工项未填写", mode_buckets["manual_pending"], "这些项不会自动执行脚本，建议人工填写最终结果和备注。"),
        ]

        row = 3
        for title, items, tip in issues:
            frame = ttk.LabelFrame(container, text=f"{title}（{len(items)}）", padding=10)
            frame.grid(row=row, column=0, sticky="nsew", pady=(10, 0))
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=tip, foreground="#666").grid(row=0, column=0, sticky="w")
            if items:
                names = "；".join([f"{item.get('item_no', '-')}-{item.get('test_name', '')}" for item in items[:8]])
                if len(items) > 8:
                    names += "；..."
                ttk.Label(frame, text=names, wraplength=880, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 8))
                ttk.Button(frame, text="查看并跳转", command=lambda bucket=items, label=title: self._open_items_window(label, bucket)).grid(row=2, column=0, sticky="e")
            else:
                ttk.Label(frame, text="当前没有该类问题。", foreground="#2f7d32").grid(row=1, column=0, sticky="w", pady=(6, 0))
            row += 1

        final_text = "当前已满足基本导出条件。" if precheck["ready"] else "当前仍有导出风险，建议先处理上述问题。"
        final_color = "#2f7d32" if precheck["ready"] else "#8a5a00"
        ttk.Label(container, text=final_text, foreground=final_color, font=("Microsoft YaHei", 11, "bold")).grid(row=row, column=0, sticky="w", pady=(16, 0))

    def export_bundle(self):
        if not self.system_info:
            messagebox.showwarning("提示", "请先采集系统信息，再导出结果包。")
            return
        if not self.save_current_item(silent=True):
            messagebox.showwarning("提示", "当前测试项填写不完整，请先补齐备注。")
            return
        precheck = build_precheck(self.results)
        if not precheck["ready"]:
            risk_message = (
                f"仍有导出风险：\n"
                f"- 未测试项: {len(precheck['not_tested'])}\n"
                f"- Fail缺备注: {len(precheck['fail_without_comment'])}\n"
                f"- Fail缺证据: {len(precheck['fail_without_evidence'])}\n"
                f"- Blocked缺备注: {len(precheck['blocked_without_comment'])}\n"
                f"- 半自动待确认: {len(self._get_execution_mode_buckets()['semi_auto_pending'])}\n"
                f"- 人工项未填写: {len(self._get_execution_mode_buckets()['manual_pending'])}\n\n"
                "是否仍然继续导出？"
            )
            if not messagebox.askyesno("导出前检查", risk_message):
                self.status_var.set("已取消导出，请先处理导出前检查问题。")
                return
        tester_name = self.tester_var.get().strip() or socket.gethostname()
        try:
            export_result = export_result_bundle(self.context, self.system_info, self.validation, self.results, tester_name, self.long_task_state)
            self.last_export_result = export_result
            self.export_result_var.set(
                "导出完成。\n"
                f"ZIP 路径：{export_result['zip_path']}\n"
                f"报告路径：{export_result.get('report_path', '未生成')}\n"
                f"结果目录：{export_result['export_dir']}\n"
                f"日志：{len(export_result['copied_logs'])} 个\n"
                f"截图：{len(export_result['copied_screenshots'])} 个\n"
                f"附件：{len(export_result['copied_artifacts'])} 个\n"
                f"长任务摘要：{'已包含' if export_result.get('has_long_task_summary', False) else '未包含'}"
            )
            self._update_summary()
            self.status_var.set(f"结果包已导出：{export_result['zip_path']}")

            # 自动打开报告
            report_path = export_result.get('report_path')
            if report_path and os.path.exists(report_path):
                import webbrowser
                webbrowser.open(f"file:///{report_path}")

            messagebox.showinfo(
                "导出成功",
                "结果包导出完成，测试报告已自动打开。\n\n"
                f"ZIP: {export_result['zip_path']}\n"
                f"报告: {export_result.get('report_path', '未生成')}\n"
                f"日志: {len(export_result['copied_logs'])} 个\n"
                f"截图: {len(export_result['copied_screenshots'])} 个\n"
                f"附件: {len(export_result['copied_artifacts'])} 个\n"
                f"长任务摘要: {'已包含' if export_result.get('has_long_task_summary', False) else '未包含'}\n\n"
                "现在可以把 ZIP 带回 QCC，在报告中心导入。",
            )
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))


def run_agent_cli(config_path: str):
    print_banner()
    context = load_package_context(config_path)
    print_project_summary(context)

    tester_name = prompt_text("测试人员", context["project_info"].get("tester", socket.gethostname()))
    print()

    print("[1/3] 采集系统信息...")
    collector = SystemCollector()
    system_info = collector.collect()
    validation = collector.validate(system_info, context["expected_config"])
    print(f"  系统信息采集完成，共 {len(system_info)} 项。")
    print(f"  期望配置校验: {validation.get('passed', 0)}/{validation.get('total', 0)} 通过，结论 {validation.get('conclusion', 'Manual')}")
    print()

    print("[2/3] 执行并填写测试项...")
    engine = TestEngine()
    timeout = context["test_config"].get("timeout", 30)
    results = []
    total = len(context["test_items"])
    for index, item in enumerate(context["test_items"], start=1):
        auto_result = build_auto_result(
            item,
            engine,
            context["expected_config"],
            timeout,
            context.get("script_mapping"),
        )
        final_result = collect_item_result(index, total, item, auto_result)
        results.append(final_result)
        print()

    summary = build_summary(results)
    print("=" * 72)
    print("  测试填写完成")
    print(
        f"  Pass: {summary.get('Pass', 0)}  |  "
        f"Fail: {summary.get('Fail', 0)}  |  "
        f"NA: {summary.get('NA', 0)}  |  "
        f"Blocked: {summary.get('Blocked', 0)}  |  "
        f"Manual: {summary.get('Manual', 0)}"
    )
    print("=" * 72)
    print()

    precheck = build_precheck(results)
    print("[导出前检查]")
    print(f"  未测试项: {len(precheck['not_tested'])}")
    print(f"  Fail缺备注: {len(precheck['fail_without_comment'])}")
    print(f"  Fail缺证据: {len(precheck['fail_without_evidence'])}")
    print(f"  Blocked缺备注: {len(precheck['blocked_without_comment'])}")
    print()
    if not precheck["ready"]:
        print("  当前仍有导出风险，建议先补齐上述问题。")
        if not prompt_yes_no("  是否仍然继续导出结果包", default=False):
            print("  已取消导出。")
            input("按回车键退出...")
            return
        print()

    print("[3/3] 导出结果包...")
    export_result = export_result_bundle(context, system_info, validation, results, tester_name)
    print(f"  结果目录: {export_result['export_dir']}")
    print(f"  ZIP结果包: {export_result['zip_path']}")
    print(f"  测试报告: {export_result.get('report_path', '未生成')}")
    print(f"  已归档日志: {len(export_result['copied_logs'])}")
    print(f"  已归档截图: {len(export_result['copied_screenshots'])}")
    print(f"  已归档附件: {len(export_result['copied_artifacts'])}")
    print()

    # 自动打开报告
    report_path = export_result.get('report_path')
    if report_path and os.path.exists(report_path):
        import webbrowser
        webbrowser.open(f"file:///{report_path}")
        print(f"  测试报告已在浏览器中打开: {report_path}")
    print()
    print("  现在可以把 ZIP 结果包带回 QCC，在报告与离线结果中心中导入。")
    print()
    input("按回车键退出...")


def launch_gui(config_path: str, auto_resume_task_key: str = ""):
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    OfflineWorkbenchApp(root, config_path, auto_resume_task_key=auto_resume_task_key)
    root.mainloop()


if __name__ == "__main__":
    # 修复：打包后正确查找配置文件
    if getattr(sys, 'frozen', False):
        # EXE 打包后，sys.executable 指向 EXE 路径
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # Agent 目录是 exe_dir，测试数据在上一级的 TestData 或当前目录
        base_dir = os.path.dirname(exe_dir)  # 上一级目录（包根目录）
    else:
        # Python 脚本模式
        base_dir = os.path.dirname(os.path.abspath(__file__))
        exe_dir = base_dir

    # 按优先级查找配置文件
    config_path = None
    search_paths = [
        os.path.join(base_dir, "TestData", "config.json"),  # TestData 子目录
        os.path.join(base_dir, "config.json"),               # 包根目录
        os.path.join(os.getcwd(), "config.json"),            # 当前工作目录
        os.path.join(os.getcwd(), "TestData", "config.json"),
    ]

    for path in search_paths:
        if os.path.exists(path):
            config_path = path
            break

    if not config_path:
        # 默认路径
        config_path = os.path.join(base_dir, "TestData", "config.json")
    use_cli = False
    auto_resume_task_key = ""
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--cli":
            use_cli = True
        elif arg == "--resume-long-task":
            if index + 1 >= len(args):
                raise SystemExit("参数错误: --resume-long-task 需要提供 task_key")
            auto_resume_task_key = args[index + 1].strip()
            index += 1
        else:
            config_path = arg
        index += 1

    if use_cli:
        try:
            run_agent_cli(config_path)
        except Exception as exc:
            print(f"[错误] 命令行模式启动失败: {exc}")
            raise SystemExit(1)
    else:
        try:
            launch_gui(config_path, auto_resume_task_key=auto_resume_task_key)
        except Exception as exc:
            print(f"[警告] 图形界面启动失败，已回退到命令行模式: {exc}")
            try:
                run_agent_cli(config_path)
            except Exception as cli_exc:
                print(f"[错误] 回退后的命令行模式也启动失败: {cli_exc}")
                raise SystemExit(1)
