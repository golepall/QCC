import platform

from common import emit_payload, read_input_payload, run_bash, run_powershell


def collect_windows_usb():
    command = (
        "$items = Get-PnpDevice | "
        "Where-Object {$_.InstanceId -match 'USB' -and $_.Class -match 'USB|HID|DiskDrive|Media'} | "
        "Select-Object FriendlyName, Status, Class, InstanceId; "
        "if($items){$items | ForEach-Object {'USB={0}|STATUS={1}|CLASS={2}|ID={3}' -f $_.FriendlyName,$_.Status,$_.Class,$_.InstanceId}}"
    )
    return run_powershell(command)


def collect_linux_usb():
    command = r"""
python - <<'PY'
import subprocess

proc = subprocess.run(['bash', '-lc', 'lsusb 2>/dev/null'], capture_output=True, text=True)
lines = []
for raw in proc.stdout.splitlines():
    text = raw.strip()
    if not text:
        continue
    lines.append('USB={0}|STATUS=OK|CLASS=USB|ID='.format(text))
print('\n'.join(lines))
PY
"""
    return run_bash(command)


def main():
    read_input_payload()
    try:
        if platform.system() == "Windows":
            stdout, stderr = collect_windows_usb()
        else:
            stdout, stderr = collect_linux_usb()

        devices = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            item = {}
            for part in line.split("|"):
                if "=" not in part:
                    continue
                key, _, value = part.partition("=")
                item[key.strip()] = value.strip()
            if item:
                devices.append(item)

        parsed = {
            "devices": devices,
            "USB_COUNT": len(devices),
            "device_count": len(devices),
            "USB": devices[0].get("USB", "") if devices else "",
            "STATUS": devices[0].get("STATUS", "") if devices else "",
        }
        verdict = "Pass" if len(devices) > 0 else "Fail"
        return emit_payload(True, stdout, parsed, verdict=verdict, error=stderr)
    except Exception as exc:
        return emit_payload(False, "", {}, verdict="Error", error=str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
