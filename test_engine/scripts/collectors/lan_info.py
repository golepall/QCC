import platform

from common import emit_payload, read_input_payload, run_bash, run_powershell


def collect_windows_lan():
    command = (
        "$items = Get-NetAdapter | "
        "Where-Object {$_.InterfaceDescription -match 'Ethernet|GbE|LAN' -or $_.Name -match 'Ethernet|LAN'} | "
        "Select-Object InterfaceDescription, Name, Status, LinkSpeed; "
        "if($items){$items | ForEach-Object {'LAN={0}|NAME={1}|STATUS={2}|SPEED={3}' -f $_.InterfaceDescription,$_.Name,$_.Status,$_.LinkSpeed}}"
    )
    return run_powershell(command)


def collect_linux_lan():
    command = r"""
python - <<'PY'
import os

names = []
base_path = '/sys/class/net'
if os.path.isdir(base_path):
    for name in sorted(os.listdir(base_path)):
        if name == 'lo' or name.startswith('wl'):
            continue
        names.append('LAN={0}|NAME={0}|STATUS=UNKNOWN|SPEED='.format(name))
print('\n'.join(names))
PY
"""
    return run_bash(command)


def main():
    read_input_payload()
    try:
        if platform.system() == "Windows":
            stdout, stderr = collect_windows_lan()
        else:
            stdout, stderr = collect_linux_lan()

        adapters = []
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
                adapters.append(item)

        up_count = sum(1 for item in adapters if str(item.get("STATUS", "")).lower() == "up")
        parsed = {
            "adapters": adapters,
            "adapter_count": len(adapters),
            "up_count": up_count,
            "LAN": adapters[0].get("LAN", "") if adapters else "",
            "STATUS": adapters[0].get("STATUS", "") if adapters else "",
            "SPEED": adapters[0].get("SPEED", "") if adapters else "",
        }
        verdict = "Pass" if up_count > 0 else "Fail"
        return emit_payload(True, stdout, parsed, verdict=verdict, error=stderr)
    except Exception as exc:
        return emit_payload(False, "", {}, verdict="Error", error=str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
