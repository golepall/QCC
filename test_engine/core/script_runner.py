import json
import importlib.util
import io
import os
import platform
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout


class ScriptRunner:

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def run(self, command: str, timeout: int = 60, cwd: str = None, shell: str = None) -> dict:
        start = time.time()
        try:
            if self.is_windows:
                shell_cmd = shell or "powershell"
                if shell_cmd == "powershell":
                    args = ["powershell", "-NoProfile", "-Command", command]
                else:
                    args = ["cmd", "/c", command]
            else:
                shell_cmd = shell or "bash"
                args = [shell_cmd, "-c", command]

            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                creationflags=subprocess.CREATE_NO_WINDOW if self.is_windows else 0,
            )

            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "duration_ms": int((time.time() - start) * 1000),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "duration_ms": int((time.time() - start) * 1000),
                "error": "timeout",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration_ms": int((time.time() - start) * 1000),
                "error": str(e),
            }

    def run_powershell(self, script: str, timeout: int = 60) -> dict:
        return self.run(script, timeout=timeout, shell="powershell")

    def run_cmd(self, command: str, timeout: int = 60) -> dict:
        return self.run(command, timeout=timeout, shell="cmd")

    def _load_python_module(self, script_path: str):
        module_name = f"qcc_collector_{abs(hash(os.path.abspath(script_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载脚本模块: {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run_python_in_process(self, script_path: str, payload: dict = None, cwd: str = None) -> dict:
        payload = payload or {}
        script_dir = os.path.dirname(os.path.abspath(script_path))
        old_cwd = os.getcwd()
        old_stdin = sys.stdin
        old_argv = list(sys.argv)
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        exit_code = 0

        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
            added_sys_path = True
        else:
            added_sys_path = False

        try:
            if cwd:
                os.chdir(cwd)
            sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
            sys.argv = [script_path]
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                module = self._load_python_module(script_path)
                main = getattr(module, "main", None)
                if not callable(main):
                    raise AttributeError(f"脚本未提供 main() 入口: {script_path}")
                result = main()
                if isinstance(result, int):
                    exit_code = result
        except SystemExit as exc:
            if isinstance(exc.code, int):
                exit_code = exc.code
            elif exc.code is None:
                exit_code = 0
            else:
                exit_code = 1
                if exc.code:
                    print(str(exc.code), file=stderr_buffer)
        finally:
            if added_sys_path:
                try:
                    sys.path.remove(script_dir)
                except ValueError:
                    pass
            sys.stdin = old_stdin
            sys.argv = old_argv
            os.chdir(old_cwd)

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout_buffer.getvalue().strip(),
            "stderr": stderr_buffer.getvalue().strip(),
        }

    def run_python(self, script_path: str, payload: dict = None, timeout: int = 60, cwd: str = None) -> dict:
        start = time.time()
        try:
            result = self._run_python_in_process(script_path, payload=payload, cwd=cwd)
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration_ms": int((time.time() - start) * 1000),
                "error": str(e),
            }
