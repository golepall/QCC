import platform

from common import emit_payload, read_input_payload, run_bash, run_powershell


def collect_windows_audio():
    command = (
        "Get-CimInstance Win32_SoundDevice | "
        "ForEach-Object {'AUDIO={0}|STATUS={1}|PNP={2}' -f $_.Name, $_.Status, $_.PNPDeviceID}"
    )
    return run_powershell(command)


def collect_linux_audio():
    command = r"""
python - <<'PY'
import subprocess

proc = subprocess.run(['bash', '-lc', 'aplay -l 2>/dev/null'], capture_output=True, text=True)
lines = []
for raw in proc.stdout.splitlines():
    text = raw.strip()
    if not text or not text.lower().startswith('card '):
        continue
    lines.append('AUDIO={0}|STATUS=OK|PNP='.format(text))
print('\n'.join(lines))
PY
"""
    return run_bash(command)


def main():
    read_input_payload()
    try:
        if platform.system() == "Windows":
            stdout, stderr = collect_windows_audio()
        else:
            stdout, stderr = collect_linux_audio()

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
            "device_count": len(devices),
            "AUDIO": devices[0].get("AUDIO", "") if devices else "",
            "STATUS": devices[0].get("STATUS", "") if devices else "",
        }
        verdict = "Pass" if len(devices) > 0 else "Fail"
        return emit_payload(True, stdout, parsed, verdict=verdict, error=stderr)
    except Exception as exc:
        return emit_payload(False, "", {}, verdict="Error", error=str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
