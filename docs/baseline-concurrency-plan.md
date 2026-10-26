# W6–W7：基线稳定性与并发退化改进计划

这是后续实验计划，不是已完成的性能结论。历史文件仍在本机旧目录及整理前备份中，没有混入当前 APC 正式数据。

## 1. 从已有证据出发

| 项目 | 已有证据 | 下一步要解决的问题 |
|---|---|---|
| W6 基线 | 3 轮 × 50 请求，实际输入 157、输出 64，C=1、到达率 1 req/s | 第 3 轮 P95 E2EL 为 1030.51 ms，前两轮约 550 ms；需要解释长尾 |
| W7 并发 | 已做 C=1/4/8/16/32 和 16/32/64/128 扫描 | C64 从 4675.46 降至 776.05 tokens/s，P95 E2EL 从 927.84 升到 9480.23 ms，不能跨阶段挑最快值 |
| W7 定位 | 有 metrics、CPU 火焰图与 UVA 对照 | 缺同一 run_id、修改 diff 和重复对照，尚不能断言 KV 满或 UVA 已被修复 |

上表历史文件：results/w6/run_1.json、run_2.json、run_3.json；results/w7/saturation/concurrency_64.json；results/w7/final/verify_64_1792054747.json。这些是旧目录中的路径，不是本仓库中可下载的证据。数字已重新读取原始 JSON 核对；这里只用于确定复测优先级。

建议拆成两个可讲清楚的成果：W6 回答“基线是否稳定、指标怎么算”；W7 回答“并发增加在哪里退化、证据支持什么原因”。不需要把所有旧组合全部重做。

## 2. 统一前提

- 沿用本仓库环境和模型，APC 固定 OFF。使用同一份数据、同一服务配置；保持电源模式和后台负载一致。
- 输出固定 64 tokens，输入长度以实际 chat 模板后的 token 数为准。不能把 128 字符、128 原始 tokens 和服务端输入 157 tokens 混用。
- 每轮保留 dataset、manifest、result、benchmark.log、前后 metrics。保留首请求，不删除慢请求。
- 先跑 6 条检查链路；正式结果写入 runs/baseline 或 runs/concurrency，不覆盖 results/prefix-cache。
- 本仓库 audit_results.py 验证的是四组 APC 协议，不能直接用它验收 W6/W7。后续需单独建立基线/并发汇总，不要为了让它通过改组名。

详细环境激活和两个终端的使用方法见 [复现步骤](reproduction.md)。

## 3. 第一步：W6 做一份稳定基线

先在终端 B 生成 200 条短输入。下面 repeat=3 表示重复三段文本，不是 3 tokens；实际长度看生成的 workload_manifest.json，不能预先写成 128 或 157。

```bash
python scripts/build_workload.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --num-requests 200 --repeat 3 --output-tokens 64 --output-dir runs/datasets/baseline
python scripts/prepare_dataset.py --source runs/datasets/baseline/independent.jsonl --target runs/datasets/baseline/benchmark.jsonl
python -m json.tool runs/datasets/baseline/workload_manifest.json
```

这份新合成输入与旧 157/64 数据不同，作为新基线，不能据此计算“比旧版本快多少”。目录已存在时不要重复生成，也不要覆盖。

终端 A 启动服务：

```bash
bash scripts/serve.sh off /mnt/d/models/Qwen2.5-1.5B-Instruct
```

终端 B 等健康检查成功后，测低到达率：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/baseline/benchmark.jsonl --output-dir runs/baseline/low_rate_run1 --apc off --cache-state cold --concurrency 1 --request-rate 1
```

再测不人为限制到达间隔的单并发吞吐：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/baseline/benchmark.jsonl --output-dir runs/baseline/serial_run1 --apc off --cache-state cold --concurrency 1 --request-rate inf
```

每种条件测 3 轮，只将目录末尾 run1 改为 run2、run3。第 2 轮先 serial 后 low_rate，第 3 轮恢复原顺序。inf 仍受 concurrency=1 限制，只表示不加入到达间隔；它不是整张卡的峰值吞吐。

每轮必须满足：status=completed、completed=200、failed=0，output_lens 全为 64；输入指纹与配置一致。形成一张表：实际输入范围、到达率、输出 tokens/s、TTFT 均值/P95、TPOT 均值、E2EL P95、到达至完成 P95。

到达至完成时间按每个请求的 queue_times[i] + latencies[i] 计算，再求 P95；不能把两个 P95 相加。时间数组单位为秒，展示毫秒时乘 1000。三轮均值给轮间样本标准差，P95 要标明是逐轮还是合并请求。

若吞吐最大/最小仍相差超过约 10%，或某轮 P95 翻倍，先停下查原因。这是本项目的排查触发线，不是行业稳定性标准；不要只增加轮数把异常平均掉。

## 4. 第二步：W7 先解决 C64 波动

使用同一份 512 条短输入，各个并发复用：

```bash
python scripts/build_workload.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --num-requests 512 --repeat 3 --output-tokens 64 --output-dir runs/datasets/concurrency
python scripts/prepare_dataset.py --source runs/datasets/concurrency/independent.jsonl --target runs/datasets/concurrency/benchmark.jsonl
```

先只做 C32、C64、C128，各 3 轮。同一会话保持服务配置不变，用以下顺序减轻时间漂移：

| 轮次 | 顺序 |
|---|---|
| 1 | 32 → 64 → 128 |
| 2 | 128 → 64 → 32 |
| 3 | 64 → 32 → 128 |

第一条可直接执行：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/concurrency/benchmark.jsonl --output-dir runs/concurrency/c032_run1 --apc off --cache-state cold --concurrency 32 --request-rate inf
```

后续同时修改两处：--concurrency 的数值，以及保存目录中的 c032/run1。目录命名统一为 c032_run1、c064_run1、c128_run1，再进入 run2、run3。不要启动多个压测进程同时测。

512 条在高并发下可能只持续数秒，只能作为初筛。先检查每轮 duration；正式吞吐结论应增加同条件请求数，使测量窗口至少约 60 秒，稳定区间不足时继续延长。所有并发仍复用同一份加长输入，不能仅给最快并发更多请求。

## 5. 遥测必须和每一轮对应

每轮压测前，在第三个终端启动 GPU 采样，结束后 Ctrl+C。以下示例对应 c032_run1：

```bash
mkdir -p runs/telemetry
nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm --format=csv -l 1 > runs/telemetry/c032_run1-gpu.csv
```

每轮换文件名；重试用新的 run_id，避免重定向覆盖旧文件。某些 WSL/驱动不提供部分字段，N/A 要保留为未知，不能填成 0。

同时为每轮保存：
1. 服务日志文件名、服务/engine/client PID、UTC 起止时间。
2. 服务端 running、waiting、KV 使用比例、preemptions 的定时采样；当前 runner 的前后快照不能代替时序。
3. 客户端和 engine CPU 使用率。旧 monitor.py 只监控服务指标，缺 CPU/GPU 和 run_id，下一步应把它改为带 --output、--run-id、UTC 时间和异常记录的独立采集器。

不要从一份无法与运行窗口对齐的 metrics.csv 给另一轮解释瓶颈。比较采样应覆盖预热前至正式完成，并按 manifest 时间截取测量窗口。

## 6. 按证据做优化，而不是先改参数

| 同一轮观察 | 可以提出的假设 | 下一次只改一项 |
|---|---|---|
| GPU 时钟下降、功耗/温度变化和退化同向 | 电源或热状态可能影响性能 | 固定供电/散热与后台负载，按交替顺序复测；相关性不等于根因 |
| GPU 利用率低、engine 或 client 单核繁忙 | CPU、调度或客户端可能限制吞吐 | 分别采样 engine 和 client，确认热点，再改对应路径 |
| KV 使用接近满、preemptions 增长 | KV 容量/抢占可能参与退化 | 先降低并发，比较抢占增量与 P95；没有这些证据不要写“显存满了” |
| CPU 栈大量出现 copy_to_uva | 拷贝路径值得进一步定位 | 保存最小补丁 diff，做 A/B 交替；CPU 栈比例不能当 GPU 拷贝耗时 |
| 高并发吞吐提升但 P95 不满足目标 | 吞吐与延迟存在取舍 | 选择满足预先声明的 P95 目标的并发，不直接选峰值 |

先在 C32 做 A/B，各 3 次；出现一致收益后再检查 C64/C128。A 是原版本，B 是唯一修改。记录补丁、恢复命令和版本；最终计时关闭 profiler。改善小于轮间波动时，结论应是“尚无法确认”。

稳定后补长度覆盖：短/中/长输入，输出 64/256，各选 C1 和一个稳定并发即可。每次仍以实际模板 token 数命名，不必马上跑所有排列组合。

## 7. 收尾交付与学习顺序

W6 交付：固定输入、6 轮原始结果、指标定义、稳定性表及一次异常分析。
W7 交付：重复并发曲线、对齐的遥测、一项受控 A/B、满足明确延迟目标的并发选择及限制。

建议先完成 W6 的 6 轮，再做 W7 的 9 轮初筛。确认短测是否稳定，再决定延长测量或做 UVA 定位。下一步最值得动手实现的是带 run_id 的遥测采集器与独立 W6/W7 汇总器；本次尚未执行这些新 GPU 实验。
