# 基线与并发实验操作说明

本页用于复现已经归档的短输入实验。已有结论见 [总报告](../reports/project-report.md)；仅分析数据不用启动服务。新实验放 runs/，不要覆盖 results/。

## 1. 先准备两个终端

Windows PowerShell 先执行 wsl -d Ubuntu-24.04 进入 Ubuntu。后面都是 Bash 命令，每个终端逐行执行：

```bash
cd /home/administrator/vllm-lab-1
source /home/administrator/ai-infra/.venv-vllm/bin/activate
pwd
which python
```

cd 进入仓库；source 激活已安装 vLLM 的环境。路径是本机示例，其他机器改为自己的目录。不要在未激活环境时启动服务，否则会出现 vllm: command not found。

终端 A 负责服务，运行时保持打开：

```bash
bash scripts/serve.sh off /mnt/d/models/Qwen2.5-1.5B-Instruct
```

off 表示 APC 关闭。模型路径必须与后面压测命令相同；固定配置与参数含义见 [APC 复现说明](reproduction.md)。

终端 B 等待服务就绪：

```bash
curl --noproxy '*' -i http://127.0.0.1:8000/health
```

看到 200 OK 后继续。每次只运行一个压测进程。新机器先用 6 条小数据检查链路，方法见 APC 说明；不能把小测试放进正式批次。

## 2. W6：两种基线，各三轮

固定输入已经在 data/baseline.jsonl，共 200 条，实际模板输入为 159–161 tokens，输出 64。无需重新生成。

低到达率第 1 轮：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/baseline.jsonl --output-dir runs/next-baseline/low_rate_run1 --apc off --cache-state cold --concurrency 1 --request-rate 1
```

连续单并发第 1 轮：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/baseline.jsonl --output-dir runs/next-baseline/serial_run1 --apc off --cache-state cold --concurrency 1 --request-rate inf
```

| 参数 | 含义 |
|---|---|
| --dataset | 本轮读取固定数据；不在轮次间重新生成 |
| --output-dir | 本轮独立保存目录，必须不存在 |
| --apc off | 核验 A 已关闭缓存，不会自动切换服务 |
| --cache-state cold | 不做同前缀预填充，仍会进行三次服务预热 |
| --concurrency 1 | 最多一个正式请求同时执行 |
| --request-rate 1 | 设置期望到达率 1 req/s，不是精确整秒间隔 |
| --request-rate inf | 不主动加入到达间隔；并发仍受 1 限制 |

第 2 轮先 serial 再 low_rate，第 3 轮恢复顺序；只把保存目录 run1 改为 run2/run3。最终有 6 个目录。

成功后会打印 result.json 路径。检查一轮：

```bash
python -m json.tool runs/next-baseline/low_rate_run1/manifest.json
tail -n 40 runs/next-baseline/low_rate_run1/benchmark.log
```

manifest 应为 completed；每轮 200 成功、0 失败、输出均为 64。6 轮完成后：

```bash
python scripts/audit_load.py --section baseline --results-dir runs/next-baseline --output-dir runs/next-baseline-report
```

section 指协议，results-dir 指原始批次，output-dir 指报告目录。汇总与原始批次分开放。检查失败时先解决问题，不改标签或删慢请求来通过校验。

## 3. W7：先理解这是短批次实验

data/concurrency.jsonl 固定 512 条输入，三种并发都使用它。每个并发测三轮。新批次可按下面顺序执行，但不要把这个建议顺序当成旧批次的实际顺序：

| 轮次 | 建议顺序 |
|---|---|
| 1 | 32 → 64 → 128 |
| 2 | 128 → 64 → 32 |
| 3 | 64 → 32 → 128 |

为了记录 GPU，需要第三个终端 C。同样进入仓库，先执行：

```bash
mkdir -p runs/next-telemetry
set -o noclobber
nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm --format=csv -l 1 > runs/next-telemetry/c032_run1-gpu.csv
```

mkdir 创建保存目录；noclobber 阻止覆盖已有文件；-l 1 请求约每秒采样一次。该命令持续运行，输出重定向到 CSV，所以终端暂时不显示数据是正常的。确认文件开始出现采样后，在 B 执行：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/concurrency.jsonl --output-dir runs/next-concurrency/c032_run1 --apc off --cache-state cold --concurrency 32 --request-rate inf
```

B 完成后，再等 C 记录一条末尾采样，按 Ctrl+C 结束 C。把采样放入本轮目录：

```bash
cp -n runs/next-telemetry/c032_run1-gpu.csv runs/next-concurrency/c032_run1/gpu.csv
```

-n 避免覆盖已有目标文件。每轮都更换 GPU 文件名和结果目录，保持一致。C64 改 --concurrency 64 和 c064_run1；C128 改为 128 和 c128_run1；其余轮次改 run2/run3。

这里的 GPU CSV 按 UTC+08 时间解释。若机器时区不同，先记录时区并修改分析协议，不能直接套用默认解析。N/A 保持未知；采样可能超过 1 秒，不应假装没有缺口。

9 轮全部成功、各有 gpu.csv 后：

```bash
python scripts/audit_load.py --section concurrency --results-dir runs/next-concurrency --output-dir runs/next-concurrency-report
```

应有 9 轮、4608 条请求，实际输出都是 64。校验会检查 GPU 文件覆盖 runner 起止时间，但该窗口包含服务预热，并非精确正式测量窗口。

## 4. 从短测走向真正的性能优化

当前发布数据测量不足 15 秒，只用于有限批次对照。若目标是持续容量，下一批要增加请求数，让测量至少约 60 秒，并同步采集客户端/engine CPU、服务指标时序和 GPU。增加请求数后必须显式制定新协议与校验参数，当前 audit_load.py 固定验收 200/512 请求，不能静默混入更长测试。

先定义可接受的 P95，再比较满足该目标的并发。inf 的队列是客户端批量积压，不等同于线上稳定到达过程。不要直接挑吞吐最大的 C128 当“最佳并发”。

若继续研究历史 C64 或 copy_to_uva：
- 保存最小修改 diff、环境和恢复方式。
- 先固定 C32，原版本/修改版本各 3 轮并交替执行。
- 用短 profiler 片段定位，再关闭 profiler 做正式计时。
- 收益小于轮间波动时写“尚不能确认”，不挑最快一次。
- 只有观察到相关指标，才讨论 KV、CPU、热状态等假设；GPU 已分配显存高不等于 KV 耗尽。

本项目的统一 analyze_project.py 用于仓库已归档的 35 轮。新批次先单独验收、形成报告，再决定是否替换或增加正式证据。
