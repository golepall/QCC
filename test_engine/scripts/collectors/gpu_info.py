import json
import platform
import subprocess
import sys
from typing import Tuple


def collect_windows_gpu() -> Tuple[str, str]:
    command = (
        "Get-CimInstance Win32_VideoController | "
        "ForEach-Object {'GPU={0}|DRIVER={1}' -f $_.Name, $_.DriverVersion}"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def collect_linux_gpu() -> Tuple[str, str]:
    command = r"""
python - <<'PY'
import subprocess

proc = subprocess.run(['bash', '-lc', "lspci | grep -i 'vga\\|3d\\|display'"], capture_output=True, text=True)
lines = []
for raw_line in proc.stdout.splitlines():
    text = raw_line.strip()
    if not text:
        continue
    lines.append('GPU={0}|DRIVER='.format(text))
print('\n'.join(lines))
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
            stdout, stderr = collect_windows_gpu()
        else:
            stdout, stderr = collect_linux_gpu()

        gpus = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload = {
            "success": bool(gpus),
            "raw_output": stdout,
            "parsed": {
                "gpus": gpus,
                "gpu_count": len(gpus),
            },
        }
        if stderr:
            payload["error"] = stderr

        print(json.dumps(payload, ensure_ascii=False))
        return 0 if gpus else 1
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
