import json
import platform
import subprocess
import sys
from typing import Dict, Tuple


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_input_payload() -> Dict:
    if sys.stdin.closed:
        return {}
    try:
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def run_command(args, timeout: int = 30) -> Tuple[str, str]:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def run_powershell(command: str, timeout: int = 30) -> Tuple[str, str]:
    return run_command(["powershell", "-NoProfile", "-Command", command], timeout=timeout)


def run_bash(command: str, timeout: int = 30) -> Tuple[str, str]:
    return run_command(["bash", "-lc", command], timeout=timeout)


def emit_payload(success: bool, raw_output: str, parsed: Dict, verdict: str = "", error: str = "") -> int:
    payload = {
        "success": success,
        "raw_output": raw_output,
        "parsed": parsed or {},
    }
    if verdict:
        payload["verdict"] = verdict
    if error:
        payload["error"] = error
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if success else 1
