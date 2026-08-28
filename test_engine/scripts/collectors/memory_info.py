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


def collect_windows_memory() -> Tuple[str, str]:
    command = (
        "$m = Get-CimInstance Win32_PhysicalMemory; "
        "$t = ($m | Measure-Object -Property Capacity -Sum).Sum / 1MB; "
        "$f = ''; if($m.Count -gt 0){$f = $m[0].Speed}; "
        "'MEMORY_TOTAL={0}MB|SLOTS={1}|FREQ={2}MHz' -f [math]::Round($t), $m.Count, $f"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def collect_linux_memory() -> Tuple[str, str]:
    command = r"""
python - <<'PY'
import re

memory_total = ''
slots = ''
freq = ''

try:
    with open('/proc/meminfo', 'r') as handle:
        for raw_line in handle:
            if raw_line.startswith('MemTotal:'):
                parts = raw_line.split()
                if len(parts) >= 2:
                    memory_total = str(int(int(parts[1]) / 1024))
                break
except Exception:
    pass

print('MEMORY_TOTAL={0}MB|SLOTS={1}|FREQ={2}MHz'.format(memory_total, slots, freq))
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
            stdout, stderr = collect_windows_memory()
        else:
            stdout, stderr = collect_linux_memory()

        parsed = parse_key_value(stdout)
        success = bool(parsed.get("MEMORY_TOTAL"))
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
