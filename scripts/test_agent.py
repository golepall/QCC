"""测试 Agent 运行环境"""
import os
import shutil
import json
import subprocess

# 创建测试目录
test_dir = 'd:/QCC/test_run'
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)
os.makedirs(test_dir)

# 复制 Agent
agent_src = 'd:/QCC/test_engine/QCC_Test_Agent_Portable/Agent'
agent_dst = os.path.join(test_dir, 'Agent')
shutil.copytree(agent_src, agent_dst)

# 创建 TestData 目录
data_dir = os.path.join(test_dir, 'TestData')
os.makedirs(data_dir)

# 创建测试数据文件
manifest = {
    'project_code': 'TEST-001',
    'project_id': 1,
    'product_model': 'Test Model',
    'product_name': 'Test Product',
    'template_id': 1,
    'generated_at': '2026-07-15',
    'package_type': 'full',
    'agent_version': '1.1.0'
}

with open(os.path.join(data_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

with open(os.path.join(data_dir, 'config.json'), 'w', encoding='utf-8') as f:
    json.dump({}, f)

with open(os.path.join(data_dir, 'test_plan.json'), 'w', encoding='utf-8') as f:
    json.dump([], f)

with open(os.path.join(data_dir, 'script_mapping.json'), 'w', encoding='utf-8') as f:
    json.dump([], f)

# 创建启动脚本
lines = [
    '@echo off',
    'title QCC Test Agent',
    'echo Starting Agent...',
    'start "" "Agent\\QCC_Test_Agent.exe"',
    'pause',
]

with open(os.path.join(test_dir, 'start.bat'), 'wb') as f:
    for line in lines:
        f.write((line + '\r\n').encode('ascii'))

print('Test directory created:', test_dir)
print('Contents:')
for item in os.listdir(test_dir):
    print(f'  {item}')

# 测试运行 Agent
print()
print('Testing Agent...')
exe_path = os.path.join(test_dir, 'Agent', 'QCC_Test_Agent.exe')
if os.path.exists(exe_path):
    try:
        # 运行 Agent 并捕获输出
        result = subprocess.run(
            [exe_path],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=test_dir  # 在测试目录中运行
        )
        print('Return code:', result.returncode)
        if result.stdout:
            print('STDOUT:', result.stdout[:500])
        if result.stderr:
            print('STDERR:', result.stderr[:500])
    except subprocess.TimeoutExpired:
        print('Agent is running (timeout after 5 seconds - GUI mode)')
    except Exception as e:
        print('Error:', e)
else:
    print('EXE not found:', exe_path)
