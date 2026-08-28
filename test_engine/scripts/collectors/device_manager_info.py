import platform

from common import emit_payload, read_input_payload, run_bash, run_powershell


def collect_windows_problem_devices():
    command = (
        "$items = Get-PnpDevice | "
        "Where-Object {$_.Status -ne 'OK' -and $_.Class -ne '' -and $_.Class -notmatch 'Printer|Net|SoftwareDevice'} | "
        "Select-Object FriendlyName, Status, Problem, Class, InstanceId; "
        "if($items){$items | ForEach-Object {'DEVICE={0}|STATUS={1}|PROBLEM={2}|CLASS={3}|ID={4}' -f $_.FriendlyName,$_.Status,$_.Problem,$_.Class,$_.InstanceId}}else{'ALL_OK'}"
    )
    return run_powershell(command)


def collect_linux_problem_devices():
    return run_bash("echo ALL_OK")


def main():
    read_input_payload()
    try:
        if platform.system() == "Windows":
            stdout, stderr = collect_windows_problem_devices()
        else:
            stdout, stderr = collect_linux_problem_devices()

        problems = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line == "ALL_OK":
                continue
            item = {}
            for part in line.split("|"):
                if "=" not in part:
                    continue
                key, _, value = part.partition("=")
                item[key.strip()] = value.strip()
            if item:
                problems.append(item)

        parsed = {
            "has_problem": len(problems) > 0,
            "problem_count": len(problems),
            "problem_devices": problems,
        }
        verdict = "Fail" if problems else "Pass"
        return emit_payload(True, stdout, parsed, verdict=verdict, error=stderr)
    except Exception as exc:
        return emit_payload(False, "", {}, verdict="Error", error=str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
