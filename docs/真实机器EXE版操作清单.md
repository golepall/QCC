# QCC 真实机器 EXE 版操作清单

生成日期：2026-06-12

## 1. 使用目的

本文用于指导现场人员在真实测试机器上使用 EXE 版 Agent 执行一次最小可用的“真实开机自动续跑”验收。

本文默认你已经拿到了以下两样：

- `QCC_Test_Agent` 目录
- 测试包目录，例如 `tmp_stage2_resultmeta_check`

本文不要求目标机器安装 Python。

## 2. 你要带到真实机器的东西

从当前开发机复制以下两个目录到 U 盘：

- `d:\QCC\test_engine\dist\QCC_Test_Agent`
- `d:\QCC\artifacts\test_packages\tmp_stage2_resultmeta_check`

不要只复制 `QCC_Test_Agent.exe` 单个文件。

必须复制整个目录，因为其中还包含：

- `core`
- `scripts`
- `script_registry.json`

## 3. 到真实机器后的目录摆放

把 U 盘里的两个目录复制到真实机器本地硬盘。

建议放成如下结构：

```text
D:\QCC_TEST\
  QCC_Test_Agent\
  tmp_stage2_resultmeta_check\
```

注意：

- 不要直接在 U 盘里运行
- 不要在启动后再随意改目录名
- 不要把测试包挪到别的盘符

原因：

- 自动续跑会把当前 exe 路径和测试包路径写入恢复脚本
- 中途改路径会导致恢复启动失败

## 4. 第一次启动前检查

到真实机器后，先确认以下 4 件事：

1. 当前机器是 Windows
2. 你能登录到待测试的同一用户桌面
3. `%APPDATA%` 可访问
4. `D:\QCC_TEST\QCC_Test_Agent\QCC_Test_Agent.exe` 和 `D:\QCC_TEST\tmp_stage2_resultmeta_check\config.json` 都存在

建议手工打开并检查：

- `D:\QCC_TEST\QCC_Test_Agent`
- `D:\QCC_TEST\tmp_stage2_resultmeta_check`
- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

## 5. 启动 Agent

在真实机器打开 PowerShell，执行：

```powershell
D:\QCC_TEST\QCC_Test_Agent\QCC_Test_Agent.exe D:\QCC_TEST\tmp_stage2_resultmeta_check\config.json
```

正常现象：

- Agent GUI 能打开
- 能进入测试工作台
- 不会提示缺少 Python

如果 GUI 没打开，先检查：

- exe 目录是否完整复制
- 测试包目录是否完整复制
- `config.json` 是否存在

## 6. 第一次建议先测什么

第一次现场验收，优先使用：

- `reboot_cycle`

原因：

- 最容易复现
- 最容易判断是否真的发生了“自动拉起”和“自动恢复”

第一次不建议直接先跑：

- `s3_cycle`
- `s4_cycle`

## 7. 实际操作步骤

### 7.1 创建任务

1. 打开 Agent 后进入“压力/循环测试”页
2. 创建一个 `reboot_cycle`
3. 记录当前任务名称
4. 记下任务的 `task_key`

完成后检查测试包目录中是否出现：

- `D:\QCC_TEST\tmp_stage2_resultmeta_check\agent_runtime\long_task_state.json`

### 7.2 标记等待恢复

1. 在该任务详情里点击“标记等待恢复”
2. 点击后先不要马上重启机器
3. 先去检查是否生成了续跑文件

检查目录：

- `D:\QCC_TEST\tmp_stage2_resultmeta_check\agent_runtime`

此时应该看到：

- `<task_key>_resume_note.txt`
- `<task_key>_resume_launcher.cmd`
- `<task_key>_resume_launcher.ps1`

### 7.3 检查状态文件

打开：

- `D:\QCC_TEST\tmp_stage2_resultmeta_check\agent_runtime\long_task_state.json`

找到当前任务，确认至少有这些值：

- `resume_state = waiting_resume`
- `startup_registered = true`
- `startup_launcher_cmd` 不为空

### 7.4 检查 Startup 注册

打开：

- `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

确认是否出现类似文件：

- `QCC_AutoResume_<project_code>_<task_key>.cmd`

再打开这个文件，确认它会 `call` 到测试包目录下的恢复脚本。

### 7.5 检查恢复脚本内容

打开：

- `D:\QCC_TEST\tmp_stage2_resultmeta_check\agent_runtime\<task_key>_resume_launcher.cmd`

确认其中至少有这些内容：

- `QCC_AGENT`
- `QCC_CONFIG`
- `QCC_TASK_KEY`
- `--resume-long-task`

并且 `QCC_AGENT` 指向：

- `D:\QCC_TEST\QCC_Test_Agent\QCC_Test_Agent.exe`

## 8. 真正执行恢复验收

### 8.1 执行一次重启

确认上面的检查都通过后，再执行一次重启。

重启后必须：

- 登录同一个测试用户

这是关键条件。

### 8.2 登录后观察

登录完成后重点看 3 件事：

1. Agent 是否自动启动
2. 是否自动定位到对应长任务
3. 是否弹出或显示“已自动恢复长任务”的提示

只要这 3 件事都发生，说明自动恢复主链路已经基本跑通。

## 9. 恢复后怎么判定成功

重新打开：

- `D:\QCC_TEST\tmp_stage2_resultmeta_check\agent_runtime\long_task_state.json`

确认当前任务变成：

- `resume_state = resumed`
- `status = running`
- `resume_count` 增加
- `last_resume_at` 有值

再检查 Startup 目录，确认：

- 刚才的 `QCC_AutoResume_*.cmd` 已经被移除

如果这两部分都成立，就说明：

- 已自动拉起 Agent
- 已自动执行恢复动作
- 已自动清理 Startup 注册

## 10. 完成态检查

回到 Agent 后，继续把这个任务记录到完成。

任务完成后再检查：

- `status = completed`
- `resume_state` 已清空
- Startup 目录中没有残留启动脚本

## 11. 手工清理检查

为了补最后一条验收链路，再做一次：

1. 新建一个 `reboot_cycle`
2. 再次点击“标记等待恢复”
3. 这次不要重启
4. 直接点击“清理续跑文件”

然后检查：

- `resume_note`
- `resume_launcher.cmd`
- `resume_launcher.ps1`
- Startup 目录中的 `QCC_AutoResume_*.cmd`

这些都应该被删除。

## 12. 建议保留的证据

建议至少保留以下截图或文件摘录：

- `long_task_state.json` 恢复前
- `long_task_state.json` 恢复后
- `agent_runtime` 目录下生成的续跑文件
- Startup 目录注册前后
- Agent 自动恢复成功提示
- 完成态或手工清理后的目录状态

## 13. 现场最容易卡住的地方

如果失败，优先排查：

1. 是否真的登录了同一个用户
2. `%APPDATA%` 是否可写
3. `QCC_Test_Agent` 或测试包目录是否被改名或移动
4. `config.json` 是否仍在原路径
5. Windows 安全策略是否拦截 Startup 启动
6. 标记恢复前任务是否真的进入了 `waiting_resume`

## 14. 推荐配套文档

建议现场同时打开以下两份文档：

- `d:\QCC\docs\真实开机自动续跑现场验收步骤.md`
- `d:\QCC\docs\真实开机自动续跑现场验收记录模板.md`
