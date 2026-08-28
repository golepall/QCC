import platform
import socket
import json
import time
from datetime import datetime
from .script_runner import ScriptRunner


class SystemCollector:

    def __init__(self):
        self.runner = ScriptRunner()
        self.is_windows = platform.system() == "Windows"

    def collect(self) -> dict:
        data = {
            "source": "python_collector",
            "collect_time": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "os_arch": platform.machine(),
        }

        safe_methods = [
            ("_collect_cpu", self._collect_cpu),
            ("_collect_memory", self._collect_memory),
            ("_collect_disk", self._collect_disk),
            ("_collect_bios", self._collect_bios),
            ("_collect_network", self._collect_network),
            ("_collect_gpu", self._collect_gpu),
            ("_collect_audio", self._collect_audio),
            ("_collect_peripherals", self._collect_peripherals),
        ]

        for name, method in safe_methods:
            try:
                data.update(method())
            except Exception as e:
                data[f"{name}_error"] = str(e)

        if self.is_windows:
            try:
                data.update(self._collect_windows_extra())
            except Exception as e:
                data["windows_extra_error"] = str(e)
            try:
                data["problem_devices"] = self._check_device_manager()
            except Exception as e:
                data["problem_devices"] = []
                data["device_check_error"] = str(e)

        return data

    def _collect_cpu(self) -> dict:
        try:
            import psutil
            freq = psutil.cpu_freq()
            return {
                "cpu_model": platform.processor() or "Unknown",
                "cpu_cores_physical": psutil.cpu_count(logical=False),
                "cpu_cores_logical": psutil.cpu_count(logical=True),
                "cpu_freq_current": round(freq.current, 0) if freq else 0,
                "cpu_freq_max": round(freq.max, 0) if freq else 0,
            }
        except Exception:
            return {"cpu_model": platform.processor(), "cpu_cores_physical": 0, "cpu_cores_logical": 0}

    def _collect_memory(self) -> dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            modules = []

            if self.is_windows:
                result = self.runner.run_powershell(
                    "Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer, PartNumber, Capacity, Speed, DeviceLocator | ConvertTo-Json",
                    timeout=15,
                )
                if result["success"] and result["stdout"]:
                    raw = json.loads(result["stdout"])
                    if isinstance(raw, dict):
                        raw = [raw]
                    for m in raw:
                        modules.append({
                            "vendor": m.get("Manufacturer", ""),
                            "model": (m.get("PartNumber") or "").strip(),
                            "capacity_mb": round(m.get("Capacity", 0) / 1048576),
                            "frequency": m.get("Speed", 0),
                            "slot": m.get("DeviceLocator", ""),
                        })

            return {
                "memory_total_mb": round(mem.total / 1048576),
                "memory_available_mb": round(mem.available / 1048576),
                "memory_modules": modules,
            }
        except Exception as e:
            return {"memory_total_mb": 0, "memory_modules": [], "memory_error": str(e)}

    def _collect_disk(self) -> dict:
        try:
            import psutil
            disks = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total_gb": round(usage.total / 1073741824, 1),
                        "used_gb": round(usage.used / 1073741824, 1),
                    })
                except (PermissionError, OSError):
                    continue

            physical_disks = []
            if self.is_windows:
                result = self.runner.run_powershell(
                    "Get-PhysicalDisk | Select-Object FriendlyName, Manufacturer, Size, MediaType, BusType | ConvertTo-Json",
                    timeout=15,
                )
                if result["success"] and result["stdout"]:
                    raw = json.loads(result["stdout"])
                    if isinstance(raw, dict):
                        raw = [raw]
                    for d in raw:
                        physical_disks.append({
                            "model": d.get("FriendlyName", ""),
                            "vendor": d.get("Manufacturer", ""),
                            "capacity_gb": round(d.get("Size", 0) / 1073741824),
                            "media_type": d.get("MediaType", ""),
                            "interface": d.get("BusType", ""),
                        })

            return {"disk_partitions": disks, "physical_disks": physical_disks}
        except Exception as e:
            return {"disk_partitions": [], "physical_disks": [], "disk_error": str(e)}

    def _collect_bios(self) -> dict:
        if not self.is_windows:
            return {}
        result = self.runner.run_powershell(
            "$b = Get-WmiObject Win32_BIOS; "
            "$d = if($b.ReleaseDate){[Management.ManagementDateTimeConverter]::ToDateTime($b.ReleaseDate).ToString('yyyy-MM-dd')}else{''}; "
            "ConvertTo-Json @{vendor=$b.Manufacturer; version=$b.SMBIOSBIOSVersion; date=$d}",
            timeout=15,
        )
        if result["success"] and result["stdout"]:
            try:
                d = json.loads(result["stdout"])
                return {"bios_vendor": d.get("vendor", ""), "bios_version": d.get("version", ""), "bios_date": d.get("date", "")}
            except json.JSONDecodeError:
                pass
        return {}

    def _collect_network(self) -> dict:
        try:
            import psutil
            adapters = []
            for name, addrs in psutil.net_if_addrs().items():
                name = name or ""
                stats = psutil.net_if_stats().get(name)
                ips = [a.address for a in addrs if a.family.name == "AF_INET"]
                macs = [a.address for a in addrs if a.family.name == "AF_LINK"]
                adapters.append({
                    "name": name,
                    "mac": macs[0] if macs else "",
                    "ip": ips[0] if ips else "",
                    "is_up": stats.isup if stats else False,
                    "speed_mbps": stats.speed if stats else 0,
                })

            lan = next((a for a in adapters if a["name"] and "ethernet" in a["name"].lower() and a["is_up"]), None)
            wlan = next((a for a in adapters if a["name"] and ("wi-fi" in a["name"].lower() or "wireless" in a["name"].lower())), None)

            return {
                "network_adapters": adapters,
                "lan_model": lan["name"] if lan else "",
                "lan_ip": lan["ip"] if lan else "",
                "wlan_model": wlan["name"] if wlan else "",
                "wlan_ip": wlan["ip"] if wlan else "",
            }
        except Exception:
            return {"network_adapters": []}

    def _collect_gpu(self) -> dict:
        if not self.is_windows:
            return {}
        result = self.runner.run_powershell(
            "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name, DriverVersion | ConvertTo-Json",
            timeout=15,
        )
        if result["success"] and result["stdout"]:
            try:
                d = json.loads(result["stdout"])
                return {"gpu_model": d.get("Name", ""), "gpu_driver": d.get("DriverVersion", "")}
            except json.JSONDecodeError:
                pass
        return {}

    def _collect_audio(self) -> dict:
        if not self.is_windows:
            return {}
        result = self.runner.run_powershell(
            "Get-CimInstance Win32_SoundDevice | Select-Object -First 1 Name, DriverVersion | ConvertTo-Json",
            timeout=15,
        )
        if result["success"] and result["stdout"]:
            try:
                d = json.loads(result["stdout"])
                return {"audio_codec": d.get("Name", ""), "audio_driver": d.get("DriverVersion", "")}
            except json.JSONDecodeError:
                pass
        return {}

    def _collect_peripherals(self) -> dict:
        if not self.is_windows:
            return {}
        result = self.runner.run_powershell(
            "Get-PnpDevice | Where-Object {$_.Status -eq 'OK'} | Select-Object FriendlyName, Class, InstanceId | ConvertTo-Json",
            timeout=20,
        )
        peripherals = {}
        if result["success"] and result["stdout"]:
            try:
                devices = json.loads(result["stdout"])
                if isinstance(devices, dict):
                    devices = [devices]
                for d in devices:
                    name = d.get("FriendlyName") or ""
                    if not name:
                        continue
                    lower = name.lower()
                    if any(k in lower for k in ["camera", "webcam"]):
                        peripherals.setdefault("camera", []).append(name)
                    elif any(k in lower for k in ["fingerprint", "指纹"]):
                        peripherals.setdefault("fingerprint", []).append(name)
                    elif any(k in lower for k in ["touchpad", "触摸"]):
                        peripherals.setdefault("touchpad", []).append(name)
                    elif any(k in lower for k in ["bluetooth"]):
                        peripherals.setdefault("bluetooth", []).append(name)
            except json.JSONDecodeError:
                pass
        return {"peripherals": peripherals}

    def _collect_windows_extra(self) -> dict:
        result = self.runner.run_powershell(
            "$mb = Get-WmiObject Win32_BaseBoard; "
            "ConvertTo-Json @{motherboard=$mb.Product; manufacturer=$mb.Manufacturer}",
            timeout=10,
        )
        extra = {}
        if result["success"] and result["stdout"]:
            try:
                d = json.loads(result["stdout"])
                extra["motherboard"] = d.get("motherboard", "")
                extra["motherboard_manufacturer"] = d.get("manufacturer", "")
            except json.JSONDecodeError:
                pass
        return extra

    def _check_device_manager(self) -> list:
        result = self.runner.run_powershell(
            "Get-PnpDevice | Where-Object {$_.Status -ne 'OK' -and $_.Class -ne '' -and $_.Class -notmatch 'Printer|Net|SoftwareDevice'} "
            "| Select-Object FriendlyName, Class, Status, ConfigManagerErrorCode | ConvertTo-Json",
            timeout=15,
        )
        problems = []
        if result["success"] and result["stdout"]:
            try:
                raw = json.loads(result["stdout"])
                if isinstance(raw, dict):
                    raw = [raw]
                for d in raw:
                    problems.append({
                        "name": d.get("FriendlyName") or "",
                        "class": d.get("Class") or "",
                        "status": d.get("Status") or "",
                        "error_code": d.get("ConfigManagerErrorCode") or "",
                    })
            except json.JSONDecodeError:
                pass
        return problems

    def validate(self, collected: dict, spec: dict) -> dict:
        checks = []

        def check(field, label, match_type="contains"):
            actual = str(collected.get(field) or "")
            expected = str(spec.get(field) or "")
            if not expected:
                return
            if match_type == "contains":
                passed = expected.lower() in actual.lower()
            elif match_type == "exact":
                passed = actual == expected
            elif match_type == "gte":
                try:
                    passed = float(actual) >= float(expected)
                except ValueError:
                    passed = False
            else:
                passed = True
            checks.append({
                "field": field, "label": label,
                "expected": expected, "actual": actual,
                "passed": passed,
                "detail": "一致" if passed else f"不一致: 期望 '{expected}', 实际 '{actual}'",
            })

        check("cpu_model", "CPU型号")
        check("cpu_cores_logical", "CPU逻辑核心数", "gte")
        check("memory_total_mb", "内存总量(MB)", "gte")
        check("bios_version", "BIOS版本")
        check("os_version", "操作系统")
        check("gpu_model", "显卡")
        check("audio_codec", "声卡")
        check("motherboard", "主板")

        for dev in collected.get("problem_devices", []):
            checks.append({
                "field": "device_manager", "label": f"设备: {dev['name']}",
                "expected": "正常", "actual": f"{dev['status']}",
                "passed": False, "detail": f"设备异常: {dev['name']}",
            })

        if not collected.get("problem_devices"):
            checks.append({
                "field": "device_manager", "label": "设备管理器",
                "expected": "无异常", "actual": "无异常",
                "passed": True, "detail": "所有设备正常",
            })

        passed = sum(1 for c in checks if c["passed"])
        return {
            "total": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "items": checks,
            "conclusion": "Pass" if all(c["passed"] for c in checks) else "Fail",
        }
