import json
import platform
import subprocess
import sys
from typing import Tuple


def collect_windows_disk() -> Tuple[str, str]:
    command = (
        "Get-PhysicalDisk | Select-Object FriendlyName, Size, MediaType, BusType | "
        "ForEach-Object {'DISK={0}|SIZE={1}GB|TYPE={2}|IF={3}' -f "
        "$_.FriendlyName, [math]::Round($_.Size/1GB), $_.MediaType, $_.BusType}"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def collect_linux_disk() -> Tuple[str, str]:
    command = r"""
python - <<'PY'
import json
import subprocess

proc = subprocess.run(
    ['lsblk', '-d', '-b', '-o', 'NAME,SIZE,MODEL,ROTA,TRAN'],
    capture_output=True,
    text=True,
)

lines = []
for raw_line in proc.stdout.splitlines()[1:]:
    parts = raw_line.split(None, 4)
    if len(parts) < 2:
        continue
    name = parts[0]
    size_bytes = parts[1]
    model = parts[2] if len(parts) > 2 else ''
    rota = parts[3] if len(parts) > 3 else ''
    bus = parts[4] if len(parts) > 4 else ''
    try:
        size_gb = round(int(size_bytes) / (1024 ** 3))
    except Exception:
        size_gb = ''
    media_type = 'HDD' if rota == '1' else 'SSD' if rota == '0' else ''
    lines.append('DISK={0}|SIZE={1}GB|TYPE={2}|IF={3}'.format(model or name, size_gb, media_type, bus))

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
            stdout, stderr = collect_windows_disk()
        else:
            stdout, stderr = collect_linux_disk()

        disks = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload = {
            "success": bool(disks),
            "raw_output": stdout,
            "parsed": {
                "disks": disks,
                "disk_count": len(disks),
            },
        }
        if stderr:
            payload["error"] = stderr

        print(json.dumps(payload, ensure_ascii=False))
        return 0 if disks else 1
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
