import re
import json
import os
from .script_runner import ScriptRunner


class PerfRunner:

    def __init__(self):
        self.runner = ScriptRunner()
        self.tools = {
            "crystaldiskmark": {
                "name": "CrystalDiskMark",
                "detect_cmd": 'Get-Command DiskMark64.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source',
                "run_cmd": 'DiskMark64.exe /C{count} /S{size} /Q{queue} /T{threads}',
                "parse": self._parse_crystaldiskmark,
            },
            "fio": {
                "name": "FIO",
                "detect_cmd": 'fio --version',
                "run_cmd": 'fio --name={name} --rw={rw} --bs={bs} --size={size} --numjobs={jobs} --runtime={runtime} --time_based --output-format=json',
                "parse": self._parse_fio,
            },
            "iperf3": {
                "name": "iperf3",
                "detect_cmd": 'iperf3 --version',
                "run_cmd": 'iperf3 -c {server} -t {duration} -J',
                "parse": self._parse_iperf3,
            },
            "stream": {
                "name": "STREAM",
                "detect_cmd": 'stream.exe',
                "run_cmd": 'stream.exe',
                "parse": self._parse_stream,
            },
            "spec_cpu": {
                "name": "SPEC CPU 2006",
                "detect_cmd": 'Test-Path "C:\\SPEC\\bin\\runspec"',
                "run_cmd": 'cd C:\\SPEC; .\\bin\\runspec --config={config} --rate --noreportable int fp',
                "parse": self._parse_spec_cpu,
            },
            "unixbench": {
                "name": "UnixBench",
                "detect_cmd": 'Test-Path "/opt/unixbench/Run"',
                "run_cmd": '/opt/unixbench/Run -c 1 -c $(nproc)',
                "parse": self._parse_unixbench,
            },
        }

    def get_tool_list(self) -> list:
        return [{"id": tid, "name": t["name"]} for tid, t in self.tools.items()]

    def detect(self, tool_id: str) -> dict:
        tool = self.tools.get(tool_id)
        if not tool:
            return {"available": False, "error": "未知工具"}
        result = self.runner.run(tool["detect_cmd"], timeout=10)
        return {"available": result["success"] and bool(result["stdout"].strip())}

    def run(self, tool_id: str, params: dict = None) -> dict:
        params = params or {}
        tool = self.tools.get(tool_id)
        if not tool:
            return {"success": False, "error": "未知工具"}

        detected = self.detect(tool_id)
        if not detected["available"]:
            return {"success": False, "error": f"{tool['name']} 未安装或不可用"}

        defaults = {
            "name": "test", "rw": "randread", "bs": "4k", "size": "1G",
            "jobs": 4, "runtime": 60, "server": "192.168.1.1", "duration": 10,
            "count": 3, "queue": 32, "threads": 1, "config": "qcc.cfg",
        }
        defaults.update(params)

        try:
            cmd = tool["run_cmd"].format(**defaults)
        except KeyError as e:
            return {"success": False, "error": f"缺少参数: {e}"}

        timeout = params.get("timeout", 600)
        result = self.runner.run(cmd, timeout=timeout)

        parsed = {}
        if result["success"] and tool.get("parse"):
            try:
                parsed = tool["parse"](result["stdout"])
            except Exception as e:
                parsed = {"parse_error": str(e)}

        return {
            "success": result["success"],
            "tool": tool_id,
            "tool_name": tool["name"],
            "raw_output": result["stdout"][:5000],
            "parsed": parsed,
            "duration_ms": result.get("duration_ms", 0),
        }

    def _parse_crystaldiskmark(self, output: str) -> dict:
        results = []
        for line in output.split("\n"):
            m = re.match(r"(SEQ\w+|RND\w+)\s+[\w:]+\s+([\d.]+)\s+(\w+/s)\s+([\d.]+)\s+(\w+/s)", line)
            if m:
                results.append({
                    "test": m.group(1), "read": float(m.group(2)), "read_unit": m.group(3),
                    "write": float(m.group(4)), "write_unit": m.group(5),
                })
        return {"tool": "CrystalDiskMark", "results": results}

    def _parse_fio(self, output: str) -> dict:
        try:
            data = json.loads(output)
            jobs = data.get("jobs", [])
            results = []
            for job in jobs:
                results.append({
                    "name": job.get("jobname"),
                    "read_iops": round(job.get("read", {}).get("iops", 0)),
                    "read_bw_kbps": round(job.get("read", {}).get("bw", 0)),
                    "read_lat_us": round(job.get("read", {}).get("lat_ns", {}).get("mean", 0) / 1000),
                    "write_iops": round(job.get("write", {}).get("iops", 0)),
                    "write_bw_kbps": round(job.get("write", {}).get("bw", 0)),
                    "write_lat_us": round(job.get("write", {}).get("lat_ns", {}).get("mean", 0) / 1000),
                })
            return {"tool": "FIO", "results": results}
        except (json.JSONDecodeError, KeyError):
            return {"tool": "FIO", "error": "parse_failed", "raw": output[:500]}

    def _parse_iperf3(self, output: str) -> dict:
        try:
            data = json.loads(output)
            bps = data.get("end", {}).get("sum_sent", {}).get("bits_per_second", 0)
            return {"tool": "iperf3", "throughput_mbps": round(bps / 1000000), "unit": "Mbps"}
        except (json.JSONDecodeError, KeyError):
            return {"tool": "iperf3", "error": "parse_failed"}

    def _parse_stream(self, output: str) -> dict:
        results = []
        for line in output.split("\n"):
            m = re.match(r"(Copy|Scale|Add|Triad):\s+([\d.]+)\s+([\d.]+)", line)
            if m:
                results.append({"test": m.group(1), "bandwidth": float(m.group(2)), "unit": m.group(3)})
        return {"tool": "STREAM", "results": results}

    def _parse_spec_cpu(self, output: str) -> dict:
        int_m = re.search(r"SPECint.*?(\d+\.\d+)", output)
        fp_m = re.search(r"SPECfp.*?(\d+\.\d+)", output)
        return {
            "tool": "SPEC CPU 2006",
            "spec_int": float(int_m.group(1)) if int_m else None,
            "spec_fp": float(fp_m.group(1)) if fp_m else None,
        }

    def _parse_unixbench(self, output: str) -> dict:
        single = re.search(r"Benchmarks.*?(\d+\.\d+)\s+(\d+\.\d+)", output, re.DOTALL)
        multi = re.search(r"System Benchmarks.*?(\d+\.\d+)\s+(\d+\.\d+)", output, re.DOTALL)
        return {
            "tool": "UnixBench",
            "single_process": float(single.group(1)) if single else None,
            "multi_process": float(multi.group(1)) if multi else None,
        }
