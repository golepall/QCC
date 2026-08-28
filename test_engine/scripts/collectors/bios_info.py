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


def collect_windows_bios() -> Tuple[str, str]:
    command = (
        "$b = Get-CimInstance Win32_BIOS | Select-Object -First 1; "
        "$d = ''; "
        "if($b.ReleaseDate){try{$d = [Management.ManagementDateTimeConverter]::ToDateTime($b.ReleaseDate).ToString('yyyy-MM-dd')}catch{$d = ''}}; "
        "'BIOS_VENDOR={0}|BIOS_VERSION={1}|BIOS_DATE={2}' -f $b.Manufacturer, $b.SMBIOSBIOSVersion, $d"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def collect_linux_bios() -> Tuple[str, str]:
    version_proc = subprocess.run(
        ["bash", "-lc", "cat /sys/class/dmi/id/bios_version 2>/dev/null || dmidecode -s bios-version 2>/dev/null"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    vendor_proc = subprocess.run(
        ["bash", "-lc", "cat /sys/class/dmi/id/bios_vendor 2>/dev/null || dmidecode -s bios-vendor 2>/dev/null"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    date_proc = subprocess.run(
        ["bash", "-lc", "cat /sys/class/dmi/id/bios_date 2>/dev/null || dmidecode -s bios-release-date 2>/dev/null"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    stdout = "BIOS_VENDOR={0}|BIOS_VERSION={1}|BIOS_DATE={2}".format(
        vendor_proc.stdout.strip(),
        version_proc.stdout.strip(),
        date_proc.stdout.strip(),
    )
    stderr = "\n".join(
        part for part in [vendor_proc.stderr.strip(), version_proc.stderr.strip(), date_proc.stderr.strip()] if part
    )
    return stdout, stderr


def main() -> int:
    try:
        if not sys.stdin.closed:
            sys.stdin.read()

        if platform.system() == "Windows":
            stdout, stderr = collect_windows_bios()
        else:
            stdout, stderr = collect_linux_bios()

        parsed = parse_key_value(stdout)
        success = bool(parsed.get("BIOS_VERSION"))
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
