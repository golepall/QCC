import json
import os
import re
import sys
import time
from datetime import datetime
from .runtime_env import get_resource_root
from .script_runner import ScriptRunner


class TestEngine:

    def __init__(self):
        self.runner = ScriptRunner()
        self.base_dir = get_resource_root(__file__)
        built_in_registry = self._build_registry()
        external_registry = self._load_external_registry()
        self.test_registry = {**built_in_registry, **external_registry}

    def _build_registry(self) -> dict:
        return {
            "bios_version_check": {
                "name": "BIOS版本检查",
                "category": "bios_check",
                "auto": True,
                "script": self.runner.run_powershell if self.runner.is_windows else None,
                "command": (
                    "$b = Get-WmiObject Win32_BIOS; "
                    "$d = if($b.ReleaseDate){[Management.ManagementDateTimeConverter]::ToDateTime($b.ReleaseDate).ToString('yyyy-MM-dd')}else{''}; "
                    "'BIOS_VENDOR={0}|BIOS_VERSION={1}|BIOS_DATE={2}' -f $b.Manufacturer, $b.SMBIOSBIOSVersion, $d"
                ) if self.runner.is_windows else "echo BIOS_VERSION=$(sudo dmidecode -s bios-version)",
                "parse": self._parse_key_value,
                "judge": lambda parsed, spec: "Pass" if parsed.get("BIOS_VERSION") == spec.get("bios_version") else "Fail" if spec.get("bios_version") else "Pass",
            },
            "device_manager_check": {
                "name": "设备管理器检查",
                "category": "basic_function",
                "auto": True,
                "command": (
                    "$devs = Get-PnpDevice | Where-Object {$_.Status -ne 'OK' -and $_.Class -ne '' -and $_.Class -notmatch 'Printer|Net|SoftwareDevice'}; "
                    "if($devs){$devs | ForEach-Object {'{0}|{1}|{2}' -f $_.FriendlyName,$_.Status,$_.Problem}}else{'ALL_OK'}"
                ) if self.runner.is_windows else "echo ALL_OK",
                "parse": lambda o: {"has_problem": "ALL_OK" not in o, "raw": o},
                "judge": lambda p, s: "Fail" if p.get("has_problem") else "Pass",
            },
            "cpu_info_check": {
                "name": "CPU信息检查",
                "category": "cpu",
                "auto": True,
                "command": (
                    "$c = Get-WmiObject Win32_Processor; "
                    "'CPU_MODEL={0}|CPU_FREQ={1}MHz|CORES={2}|THREADS={3}' -f $c.Name.Trim(), $c.MaxClockSpeed, $c.NumberOfCores, $c.NumberOfLogicalProcessors"
                ) if self.runner.is_windows else "lscpu | grep 'Model name' | sed 's/.*:\\s*/CPU_MODEL=/'",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass" if not s.get("cpu_model") or s["cpu_model"].lower() in p.get("CPU_MODEL", "").lower() else "Fail",
            },
            "memory_check": {
                "name": "内存信息检查",
                "category": "memory",
                "auto": True,
                "command": (
                    "$m = Get-WmiObject Win32_PhysicalMemory; "
                    "$t = ($m | Measure-Object -Property Capacity -Sum).Sum / 1MB; "
                    "'MEMORY_TOTAL={0}MB|SLOTS={1}|FREQ={2}MHz' -f [math]::Round($t), $m.Count, $m[0].Speed"
                ) if self.runner.is_windows else "free -m | awk '/Mem:/{print \"MEMORY_TOTAL=\"$2\"MB\"}'",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass",
            },
            "disk_check": {
                "name": "硬盘信息检查",
                "category": "hdd_ssd",
                "auto": True,
                "command": (
                    "Get-PhysicalDisk | Select-Object FriendlyName, Size, MediaType, BusType | "
                    "ForEach-Object {'DISK={0}|SIZE={1}GB|TYPE={2}|IF={3}' -f $_.FriendlyName, [math]::Round($_.Size/1GB), $_.MediaType, $_.BusType}"
                ) if self.runner.is_windows else "lsblk -d -o NAME,SIZE,MODEL | tail -n +2",
                "parse": lambda o: {"disks": o.split("\n")},
                "judge": lambda p, s: "Pass" if p.get("disks") else "Fail",
            },
            "gpu_check": {
                "name": "显卡信息检查",
                "category": "vga",
                "auto": True,
                "command": (
                    "Get-CimInstance Win32_VideoController | "
                    "ForEach-Object {'GPU={0}|DRIVER={1}' -f $_.Name, $_.DriverVersion}"
                ) if self.runner.is_windows else "lspci | grep -i vga",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass",
            },
            "network_lan_check": {
                "name": "有线网络检查",
                "category": "lan",
                "auto": True,
                "command": (
                    "$a = Get-NetAdapter | Where-Object {$_.InterfaceDescription -match 'Ethernet|GbE' -and $_.Status -eq 'Up'} | Select-Object -First 1; "
                    "if($a){'LAN=' + $a.InterfaceDescription + '|STATUS=' + $a.Status + '|SPEED=' + $a.LinkSpeed}else{'LAN_DOWN'}"
                ) if self.runner.is_windows else "ip link show | grep -i 'state UP' | head -1",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass" if "LAN" in p and "DOWN" not in str(p) else "Fail",
            },
            "network_wlan_check": {
                "name": "无线网络检查",
                "category": "wlan",
                "auto": True,
                "command": (
                    "$w = Get-NetAdapter | Where-Object {$_.InterfaceDescription -match 'Wi-Fi|Wireless'} | Select-Object -First 1; "
                    "if($w){'WLAN=' + $w.InterfaceDescription + '|STATUS=' + $w.Status + '|SPEED=' + $w.LinkSpeed}else{'WLAN_DOWN'}"
                ) if self.runner.is_windows else "iwgetid -r 2>/dev/null || echo WLAN_DOWN",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass" if "WLAN" in p and "DOWN" not in str(p) else "Fail",
            },
            "audio_check": {
                "name": "音频设备检查",
                "category": "audio",
                "auto": True,
                "command": (
                    "Get-CimInstance Win32_SoundDevice | ForEach-Object {'AUDIO={0}|STATUS={1}' -f $_.Name, $_.Status}"
                ) if self.runner.is_windows else "aplay -l 2>/dev/null | head -3 || echo NO_AUDIO",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass" if "AUDIO" in p else "Fail",
            },
            "usb_check": {
                "name": "USB设备检查",
                "category": "usb",
                "auto": True,
                "command": (
                    "$u = Get-PnpDevice | Where-Object {$_.InstanceId -match 'USB' -and $_.Class -match 'USB|HID|DiskDrive|Media'}; "
                    "'USB_COUNT={0}' -f $u.Count"
                ) if self.runner.is_windows else "lsusb 2>/dev/null | wc -l",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass" if int(p.get("USB_COUNT", 0)) > 0 else "Fail",
            },
            "boot_time_check": {
                "name": "开机时间检查",
                "category": "basic_function",
                "auto": True,
                "command": (
                    "$b = Get-CimInstance Win32_OperatingSystem; "
                    "$u = (Get-Date) - $b.LastBootUpTime; "
                    "'BOOT_SECONDS={0}|LAST_BOOT={1}' -f [math]::Round($u.TotalSeconds), $b.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')"
                ) if self.runner.is_windows else "echo BOOT_SECONDS=$(awk '{printf \"%.0f\", $1}' /proc/uptime)",
                "parse": self._parse_key_value,
                "judge": lambda p, s: "Pass",
            },
            "s3_support_check": {
                "name": "S3睡眠支持检查",
                "category": "power_mgmt",
                "auto": True,
                "command": "powercfg /a | Select-String 'S3'" if self.runner.is_windows else "cat /sys/power/state | grep mem",
                "parse": lambda o: {"s3_supported": "S3" in o or "mem" in o},
                "judge": lambda p, s: "Pass" if p.get("s3_supported") else "Fail",
            },
            "ping_test": {
                "name": "网络连通性测试",
                "category": "lan",
                "auto": True,
                "command": "Test-Connection -ComputerName 8.8.8.8 -Count 2 -Quiet" if self.runner.is_windows else "ping -c 2 -W 3 8.8.8.8",
                "parse": lambda o: {"ping_ok": "True" in o or "bytes from" in o.lower()},
                "judge": lambda p, s: "Pass" if p.get("ping_ok") else "Fail",
            },
        }

    def _load_external_registry(self) -> dict:
        registry_path = os.path.join(self.base_dir, "script_registry.json")
        if not os.path.exists(registry_path):
            return {}

        with open(registry_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        registry = {}
        for item in payload.get("scripts", []):
            script_id = item.get("id")
            entry = item.get("entry")
            if not script_id or not entry:
                continue

            registry[script_id] = {
                "name": item.get("name", script_id),
                "category": item.get("category", "custom"),
                "auto": item.get("auto", True),
                "runtime": item.get("runtime", "python"),
                "entry": os.path.abspath(os.path.join(self.base_dir, entry)),
                "judge": item.get("judge"),
                "description": item.get("description", ""),
                "source": "external",
            }

        return registry

    def _evaluate_judge(self, judge_config, parsed: dict, spec: dict) -> str:
        if callable(judge_config):
            return judge_config(parsed, spec)

        if not isinstance(judge_config, dict):
            return "Manual"

        judge_type = judge_config.get("type", "manual")
        if judge_type == "always_pass":
            return "Pass"

        if judge_type == "field_equals":
            parsed_field = judge_config.get("parsed_field")
            spec_field = judge_config.get("spec_field")
            actual_value = parsed.get(parsed_field)
            expected_value = spec.get(spec_field)

            if expected_value in (None, ""):
                return judge_config.get("when_spec_missing", "Pass")

            return "Pass" if str(actual_value) == str(expected_value) else judge_config.get("fail_verdict", "Fail")

        if judge_type == "field_contains":
            parsed_field = judge_config.get("parsed_field")
            spec_field = judge_config.get("spec_field")
            actual_value = str(parsed.get(parsed_field) or "")
            expected_value = str(spec.get(spec_field) or "")

            if not expected_value:
                return judge_config.get("when_spec_missing", "Pass")

            actual_compare = actual_value.lower() if judge_config.get("case_insensitive", True) else actual_value
            expected_compare = expected_value.lower() if judge_config.get("case_insensitive", True) else expected_value
            return "Pass" if expected_compare in actual_compare else judge_config.get("fail_verdict", "Fail")

        return "Manual"

    def _parse_python_payload(self, stdout: str) -> dict:
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw_output": stdout, "parsed": {}, "parse_error": "invalid_json_output"}

    def _execute_python_test(self, test_id: str, test_def: dict, spec: dict, timeout: int) -> dict:
        entry = test_def.get("entry")
        if not entry or not os.path.exists(entry):
            return {
                "success": False,
                "test_id": test_id,
                "test_name": test_def.get("name", test_id),
                "category": test_def.get("category", "custom"),
                "verdict": "Error",
                "raw_output": "",
                "parsed": {},
                "duration_ms": 0,
                "timestamp": datetime.now().isoformat(),
                "error": f"脚本不存在: {entry}",
            }

        runner_result = self.runner.run_python(
            entry,
            payload={"test_id": test_id, "spec": spec},
            timeout=timeout,
            cwd=self.base_dir,
        )
        script_payload = self._parse_python_payload(runner_result.get("stdout", ""))

        parsed = script_payload.get("parsed") if isinstance(script_payload.get("parsed"), dict) else {}
        raw_output = script_payload.get("raw_output", runner_result.get("stdout", ""))
        if not raw_output and parsed:
            raw_output = json.dumps(parsed, ensure_ascii=False)

        verdict = script_payload.get("verdict")
        if not verdict:
            try:
                verdict = self._evaluate_judge(test_def.get("judge"), parsed, spec)
            except Exception:
                verdict = "Error"

        success = bool(runner_result.get("success", False))
        if "success" in script_payload:
            success = success and bool(script_payload.get("success"))

        if not verdict:
            verdict = "Error" if not success else "Manual"
        elif not success and "verdict" not in script_payload:
            verdict = "Error"

        result = {
            "success": success,
            "test_id": test_id,
            "script_id": test_id,
            "test_name": test_def.get("name", test_id),
            "category": test_def.get("category", "custom"),
            "raw_output": raw_output,
            "parsed": parsed,
            "metrics": script_payload.get("metrics", {}),
            "verdict": verdict,
            "duration_ms": runner_result.get("duration_ms", 0),
            "timestamp": datetime.now().isoformat(),
        }

        error_message = script_payload.get("error") or runner_result.get("stderr") or script_payload.get("parse_error")
        if error_message:
            result["error"] = error_message

        return result

    def _parse_key_value(self, output: str) -> dict:
        result = {}
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            for part in line.split("|"):
                if "=" in part:
                    key, _, value = part.partition("=")
                    result[key.strip()] = value.strip()
        return result

    def get_test_list(self) -> list:
        return [
            {
                "id": tid,
                "name": t["name"],
                "category": t["category"],
                "auto": t["auto"],
                "runtime": t.get("runtime", "command"),
                "source": t.get("source", "built_in"),
                "description": t.get("description", ""),
                "entry": t.get("entry", ""),
                "judge": t.get("judge"),
            }
            for tid, t in self.test_registry.items()
        ]

    def execute(self, test_id: str, spec: dict = None, timeout: int = 30) -> dict:
        spec = spec or {}
        test_def = self.test_registry.get(test_id)
        if not test_def:
            return {"success": False, "test_id": test_id, "error": f"未知测试项: {test_id}"}

        if test_def.get("runtime") == "python":
            return self._execute_python_test(test_id, test_def, spec, timeout)

        result = self.runner.run(test_def["command"], timeout=timeout)

        output = result.get("stdout", "")
        parsed = {}
        if test_def.get("parse"):
            try:
                parsed = test_def["parse"](output)
            except Exception as e:
                parsed = {"raw": output, "parse_error": str(e)}

        verdict = "Manual"
        if test_def.get("judge"):
            try:
                verdict = self._evaluate_judge(test_def["judge"], parsed, spec)
            except Exception:
                verdict = "Error"

        return {
            "success": result.get("success", False),
            "test_id": test_id,
            "script_id": test_id,
            "test_name": test_def["name"],
            "category": test_def["category"],
            "raw_output": output,
            "parsed": parsed,
            "verdict": verdict,
            "duration_ms": result.get("duration_ms", 0),
            "timestamp": datetime.now().isoformat(),
        }

    def execute_batch(self, test_ids: list, spec: dict = None, timeout: int = 30) -> list:
        return [self.execute(tid, spec, timeout) for tid in test_ids]

    def execute_all(self, spec: dict = None, timeout: int = 30) -> list:
        return self.execute_batch(list(self.test_registry.keys()), spec, timeout)
