import subprocess
import threading
import uuid
import time
from datetime import datetime
from .script_runner import ScriptRunner


class StressTask:

    def __init__(self, task_id: str, task_type: str, count: int, interval: int):
        self.id = task_id
        self.type = task_type
        self.count = count
        self.interval = interval
        self.status = "running"
        self.current = 0
        self.success = 0
        self.fail = 0
        self.start_time = time.time()
        self.end_time = None
        self.error = None
        self.logs = []
        self.process = None

    def to_dict(self):
        elapsed = (self.end_time or time.time()) - self.start_time
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "count": self.count,
            "current": self.current,
            "success": self.success,
            "fail": self.fail,
            "progress": round(self.current / self.count * 100) if self.count > 0 else 0,
            "duration_s": round(elapsed),
            "error": self.error,
            "logs": self.logs[-100:],
        }


class StressManager:

    def __init__(self):
        self.tasks: dict[str, StressTask] = {}
        self.runner = ScriptRunner()

    def start(self, task_type: str, count: int = 100, interval: int = 60) -> dict:
        task_id = uuid.uuid4().hex[:8]
        task = StressTask(task_id, task_type, count, interval)
        self.tasks[task_id] = task

        thread = threading.Thread(target=self._run_stress, args=(task,), daemon=True)
        thread.start()

        return {"task_id": task_id, "status": "started"}

    def stop(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"error": "任务不存在"}
        task.status = "stopped"
        if task.process:
            try:
                task.process.kill()
            except Exception:
                pass
        task.end_time = time.time()
        return {"task_id": task_id, "status": "stopped"}

    def get_status(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"error": "任务不存在"}
        return task.to_dict()

    def get_all_tasks(self) -> list:
        return [t.to_dict() for t in self.tasks.values()]

    def _run_stress(self, task: StressTask):
        try:
            if task.type == "s3":
                self._run_s3(task)
            elif task.type == "s4":
                self._run_s4(task)
            elif task.type == "reboot":
                self._run_reboot(task)
            elif task.type == "memory_stress":
                self._run_memory_stress(task)
            elif task.type == "burnin":
                self._run_burnin(task)
            else:
                task.status = "error"
                task.error = f"不支持的测试类型: {task.type}"
                task.end_time = time.time()
        except Exception as e:
            task.status = "error"
            task.error = str(e)
            task.end_time = time.time()

    def _run_s3(self, task: StressTask):
        for i in range(1, task.count + 1):
            if task.status != "running":
                break
            task.current = i
            task.logs.append({"time": datetime.now().isoformat(), "msg": f"S3 第{i}次循环开始"})

            result = self.runner.run(
                f"powercfg /h off; rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                timeout=task.interval + 30,
            )

            if result["success"]:
                task.success += 1
                task.logs.append({"time": datetime.now().isoformat(), "msg": f"S3 第{i}次: PASS"})
            else:
                task.fail += 1
                task.logs.append({"time": datetime.now().isoformat(), "msg": f"S3 第{i}次: FAIL - {result.get('stderr', '')}"})

            time.sleep(min(task.interval, 10))

        task.status = "completed"
        task.end_time = time.time()

    def _run_s4(self, task: StressTask):
        for i in range(1, task.count + 1):
            if task.status != "running":
                break
            task.current = i
            task.logs.append({"time": datetime.now().isoformat(), "msg": f"S4 第{i}次循环开始"})

            result = self.runner.run("shutdown /h", timeout=task.interval + 30)

            if result["success"]:
                task.success += 1
            else:
                task.fail += 1

            time.sleep(min(task.interval, 10))

        task.status = "completed"
        task.end_time = time.time()

    def _run_reboot(self, task: StressTask):
        for i in range(1, task.count + 1):
            if task.status != "running":
                break
            task.current = i
            task.logs.append({"time": datetime.now().isoformat(), "msg": f"重启 第{i}次循环开始"})

            result = self.runner.run(f"shutdown /r /t {task.interval}", timeout=task.interval + 60)

            if result["success"]:
                task.success += 1
            else:
                task.fail += 1

            time.sleep(task.interval + 30)

        task.status = "completed"
        task.end_time = time.time()

    def _run_memory_stress(self, task: StressTask):
        script = f"""
$endTime = (Get-Date).AddSeconds({task.count * task.interval})
while ((Get-Date) -lt $endTime) {{
    try {{
        $arr = New-Object byte[] (256MB)
        [System.GC]::Collect()
        $elapsed = [math]::Round(((Get-Date) - (Get-Date).AddSeconds(-{task.count * task.interval})).TotalSeconds)
        Write-Output "CYCLE:$elapsed"
        Start-Sleep -Seconds {task.interval}
    }} catch {{
        Write-Output "ERROR:$($_.Exception.Message)"
        break
    }}
}}
Write-Output "COMPLETED"
"""
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        task.process = proc

        for line in proc.stdout:
            line = line.strip()
            if line.startswith("CYCLE:"):
                task.current += 1
                task.success += 1
                task.logs.append({"time": datetime.now().isoformat(), "msg": line})
            elif line.startswith("ERROR:"):
                task.fail += 1
                task.logs.append({"time": datetime.now().isoformat(), "msg": line})

        proc.wait()
        task.status = "completed" if task.status == "running" else task.status
        task.end_time = time.time()

    def _run_burnin(self, task: StressTask):
        result = self.runner.run(
            "Get-Command burnintest.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source",
            timeout=10,
        )
        if result["success"] and result["stdout"]:
            task.logs.append({"time": datetime.now().isoformat(), "msg": "BurnInTest 已启动"})
            burnin_result = self.runner.run("burnintest.exe -d 12 -r -x", timeout=43200)
            if burnin_result["success"]:
                task.success = 1
            else:
                task.fail = 1
                task.error = burnin_result.get("stderr", "")
        else:
            task.status = "error"
            task.error = "BurnInTest 未安装"
            task.fail = 1

        task.current = task.count
        task.end_time = time.time()
        if task.status == "running":
            task.status = "completed"
