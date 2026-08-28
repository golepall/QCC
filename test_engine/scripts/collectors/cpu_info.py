import json
import platform
import subprocess
import sys
from typing import Tuple


def parse_key_value(output: str) -> dict:
    result = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        for part in line.split("|"):
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            result[key.strip()] = value.strip()
    return result


def collect_windows_cpu() -> Tuple[str, str]:
    command = (
        "$c = Get-CimInstance Win32_Processor | Select-Object -First 1; "
        "'CPU_MODEL={0}|CPU_FREQ={1}MHz|CORES={2}|THREADS={3}' -f "
        "$c.Name.Trim(), $c.MaxClockSpeed, $c.NumberOfCores, $c.NumberOfLogicalProcessors"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def collect_linux_cpu() -> Tuple[str, str]:
    command = r"""
python - <<'PY'
import json
import os

fields = {}
try:
    with open('/proc/cpuinfo', 'r') as handle:
        for raw_line in handle:
            if ':' not in raw_line:
                continue
            key, value = raw_line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key == 'model name' and 'CPU_MODEL' not in fields:
                fields['CPU_MODEL'] = value
            elif key == 'cpu MHz' and 'CPU_FREQ' not in fields:
                fields['CPU_FREQ'] = value
            elif key == 'cpu cores' and 'CORES' not in fields:
                fields['CORES'] = value
except Exception:
    pass

fields['THREADS'] = str(os.cpu_count() or '')
print('CPU_MODEL={0}|CPU_FREQ={1}MHz|CORES={2}|THREADS={3}'.format(
    fields.get('CPU_MODEL', ''),
    fields.get('CPU_FREQ', ''),
    fields.get('CORES', ''),
    fields.get('THREADS', ''),
))
PY
"""
    proc = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def main() -> int:
    try:
        if not sys.stdin.closed:
            sys.stdin.read()

        if platform.system() == "Windows":
            stdout, stderr = collect_windows_cpu()
        else:
            stdout, stderr = collect_linux_cpu()

        parsed = parse_key_value(stdout)
        success = bool(parsed.get("CPU_MODEL"))
        payload = {
            "success": success,
            "raw_output": stdout,
            "parsed": parsed,
        }
        if stderr:
            payload["error"] = stderr

        print(json.dumps(payload, ensure_ascii=False))
        return 0 if success else 1
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "error": str(exc),
            "raw_output": "",
            "parsed": {},
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
