"""
SSH 远程执行器
通过 SSH 连接到被测设备，远程执行测试命令并收集结果
使用 subprocess 调用 ssh 客户端，无需额外依赖
"""

import subprocess
import json
import platform
import tempfile
import os


class RemoteExecutor:

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def _run_ssh(self, host, port, username, password, command, timeout=30):
        """通过 SSH 执行远程命令"""
        # 构建 ssh 命令
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-p", str(port),
        ]

        if self.is_windows:
            # Windows 使用 ssh.exe（OpenSSH）
            ssh_cmd = ["ssh.exe"] + ssh_opts + [f"{username}@{host}", command]
        else:
            ssh_cmd = ["ssh"] + ssh_opts + [f"{username}@{host}", command]

        try:
            # 使用 subprocess，通过 stdin 传入密码
            # 注意：这种方式安全性较低，生产环境建议使用密钥认证
            if password:
                # 尝试使用 sshpass（Linux）或期望脚本（Windows）
                if self.is_windows:
                    return self._run_ssh_with_password_win(host, port, username, password, command, timeout)
                else:
                    return self._run_ssh_with_password_linux(host, port, username, password, command, timeout)
            else:
                result = subprocess.run(
                    ssh_cmd, capture_output=True, text=True,
                    timeout=timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW if self.is_windows else 0,
                )
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "exit_code": result.returncode,
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"SSH连接超时({timeout}s)", "exit_code": -1}
        except FileNotFoundError:
            return {"success": False, "stdout": "", "stderr": "未找到SSH客户端，请确保已安装OpenSSH", "exit_code": -1}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}

    def _run_ssh_with_password_win(self, host, port, username, password, command, timeout):
        """Windows 上通过 PowerShell 使用 SSH（带密码）"""
        # 使用 PowerShell 的 PSSession 或直接调用 ssh
        # 方案：创建临时 expect-like 脚本，或使用 plink
        # 这里使用 PowerShell 的 stdin 方式
        ps_script = f'''
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "ssh.exe"
$psi.Arguments = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p {port} {username}@{host} {self._escape_ps(command)}"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$proc.StandardInput.WriteLine("{password}")
$proc.StandardInput.Close()
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit({timeout * 1000})

Write-Output "EXIT_CODE=$($proc.ExitCode)"
Write-Output "===STDOUT==="
Write-Output $stdout
Write-Output "===STDERR==="
Write-Output $stderr
'''
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=timeout + 5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return self._parse_ps_output(result.stdout, result.stderr, result.returncode)

    def _run_ssh_with_password_linux(self, host, port, username, password, command, timeout):
        """Linux 上使用 sshpass 带密码 SSH"""
        sshpass_cmd = [
            "sshpass", "-p", password,
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-p", str(port), f"{username}@{host}", command
        ]
        result = subprocess.run(
            sshpass_cmd, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }

    def _escape_ps(self, s):
        """转义 PowerShell 字符串"""
        return s.replace('"', '`"').replace("'", "`'")

    def _parse_ps_output(self, stdout, stderr, returncode):
        """解析 PowerShell 包装的输出"""
        exit_code = returncode
        actual_stdout = stdout
        actual_stderr = stderr

        if "EXIT_CODE=" in stdout:
            parts = stdout.split("===STDOUT===")
            header = parts[0]
            for line in header.split("\n"):
                if line.strip().startswith("EXIT_CODE="):
                    try:
                        exit_code = int(line.strip().split("=")[1])
                    except:
                        pass

            if len(parts) > 1:
                stdout_parts = parts[1].split("===STDERR===")
                actual_stdout = stdout_parts[0].strip()
                if len(stdout_parts) > 1:
                    actual_stderr = stdout_parts[1].strip()

        return {
            "success": exit_code == 0,
            "stdout": actual_stdout,
            "stderr": actual_stderr,
            "exit_code": exit_code,
        }

    def test_connection(self, host, port=22, username="", password=""):
        """测试 SSH 连接"""
        result = self._run_ssh(host, port, username, password, "echo CONNECTION_OK", timeout=10)
        return {
            "connected": result["success"] and "CONNECTION_OK" in result.get("stdout", ""),
            "host": host,
            "port": port,
            "error": result.get("stderr", "") if not result["success"] else "",
        }

    def collect_system_info(self, host, port=22, username="", password=""):
        """远程采集系统信息"""
        # 生成一个 Python 脚本，远程执行采集
        script = '''
import platform, socket, json
try:
    import psutil
    mem = psutil.virtual_memory()
    cpu_info = {
        "cpu_model": platform.processor(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
    }
    mem_info = {"total_gb": round(mem.total / (1024**3), 1)}
except:
    cpu_info = {"cpu_model": platform.processor()}
    mem_info = {}

data = {
    "hostname": socket.gethostname(),
    "os": platform.system() + " " + platform.release(),
    "arch": platform.machine(),
    "cpu": cpu_info,
    "memory": mem_info,
}
print(json.dumps(data))
'''
        result = self._run_ssh(host, port, username, password, f'python3 -c "{script}"', timeout=30)

        if not result["success"]:
            # 尝试用 python 命令
            result = self._run_ssh(host, port, username, password, f'python -c "{script}"', timeout=30)

        if result["success"] and result["stdout"]:
            try:
                return {"success": True, "data": json.loads(result["stdout"])}
            except json.JSONDecodeError:
                return {"success": True, "data": {"raw": result["stdout"]}}
        return {"success": False, "error": result.get("stderr", "采集失败")}

    def execute_remote_tests(self, host, port, username, password, test_ids, spec=None, timeout=30):
        """远程执行测试项"""
        # 远程执行 Python 测试引擎
        script = json.dumps({
            "action": "execute_batch",
            "test_ids": test_ids,
            "spec": spec or {},
            "timeout": timeout,
        })

        # 将测试脚本写入临时文件，通过 SSH 传输并执行
        result = self._run_ssh(
            host, port, username, password,
            f'python3 -c "import sys,json; exec(json.loads(sys.argv[1]))" \'{script}\'',
            timeout=timeout * len(test_ids) + 30,
        )

        if result["success"] and result["stdout"]:
            try:
                return {"success": True, "data": json.loads(result["stdout"])}
            except json.JSONDecodeError:
                return {"success": False, "error": "解析结果失败", "raw": result["stdout"]}

        return {"success": False, "error": result.get("stderr", "执行失败")}
