# 前缀缓存实验复现操作说明

这里说明如何重新测量。若只想检查仓库已有结论，执行根 [README](../README.md) 的三条无 GPU 命令即可。

**正式原始结果在 results/prefix-cache；你新跑的结果一律放 runs 下。** runs 默认不进入 Git，避免把未验收记录混进已经发布的数据。不要删除、覆盖 results/prefix-cache。

## 1. 两个终端如何分工？

| 终端 | 用途 |
|---|---|
| A | 启动模型服务，运行期间一直保留，不要关闭 |
| B | 准备数据、发送测试请求、检查结果 |

Windows PowerShell 中先执行 `wsl -d Ubuntu-24.04` 进入 Ubuntu。后面的命令都是 Bash，按行顺序执行，不复制 Markdown 的反引号。

两个终端都要进入**自己的仓库根目录**并激活同一个 vLLM 环境。本机示例：

```bash
cd /home/administrator/vllm-lab-1
source /home/administrator/ai-infra/.venv-vllm/bin/activate
```

`cd` 切换目录，后面的相对路径都从这里起算；`source .../activate` 让当前终端使用已经安装依赖的 Python。每个新终端都要激活一次。

检查：

```bash
pwd
which python
```

本机应分别显示项目目录和 `/home/administrator/ai-infra/.venv-vllm/bin/python`。其他机器请用自己的路径，不要照抄用户名。

本协议使用 vLLM 0.31.0。新机器需要按硬件配置 Linux/WSL GPU 环境和配套 PyTorch/CUDA，再参照 [直接依赖版本](../requirements-runtime.txt) 安装。已有可用环境不必重新安装。仅画图安装 requirements-analysis.txt 即可。

下文模型路径 `/mnt/d/models/Qwen2.5-1.5B-Instruct` 是本机示例，WSL 的 /mnt/d 对应 Windows D 盘。**如果模型位置不同，要在服务、生成数据和压测命令中一起修改。** 代码不会自动下载模型。

## 2. 在 B 生成 6 条小测试输入

正式输入已经在 data 下；先生成更小的数据检查服务链路：

```bash
python scripts/build_workload.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --num-requests 6 --output-dir runs/datasets/smoke
```

| 参数 | 含义 |
|---|---|
| --model | 用哪个本地 tokenizer 计算实际输入长度 |
| --num-requests 6 | shared 和 independent 各生成 6 条 |
| --output-dir | 新数据放在哪里；目录必须不存在 |

成功后出现两份源 JSONL 和 workload_manifest.json。JSONL 每行一条输入；shared 请求有相同的长开头，independent 较早就出现不同内容。

转换为 benchmark 格式：

```bash
python scripts/prepare_dataset.py --source runs/datasets/smoke/shared.jsonl --target runs/datasets/smoke/shared_bench.jsonl
python scripts/prepare_dataset.py --source runs/datasets/smoke/independent.jsonl --target runs/datasets/smoke/independent_bench.jsonl
```

--source 指读取已有文件，--target 指新生成文件。成功后每条命令输出 6 requests。

**数据只生成一次，ON/OFF 复用同一文件。** 已生成成功就跳过这一步；脚本拒绝覆盖已有文件。

## 3. 在 A 启动 OFF 服务

```bash
bash scripts/serve.sh off /mnt/d/models/Qwen2.5-1.5B-Instruct
```

- `bash scripts/serve.sh` 执行启动脚本。
- `off` 关闭前缀缓存；后面切换成 on 开启。
- 最后一个参数是模型目录。

脚本将模型加载到 GPU。A 不返回命令提示符是正常现象，服务需要持续运行。启动日志会保存在 runs/service-logs，文件名带时间，不覆盖上次日志。

固定参数已经写在脚本中：

| 参数 | 作用 |
|---|---|
| VLLM_SERVER_DEV_MODE=1 | 开放本机实验用的配置查询、缓存重置接口 |
| host=127.0.0.1、port=8000 | 只监听本机，B 访问同一个端口 |
| dtype=half | FP16 |
| gpu-memory-utilization=0.85 | 规划显存比例，不是 GPU 利用率上限 |
| max-model-len=4096 | 输入与输出合计的上下文上限 |
| max-num-seqs=256 | 引擎允许的序列数量上限；不等于客户端实际并发 |
| max-num-batched-tokens=2048 | 调度 token 预算 |
| enable-chunked-prefill | 开启分块 prefill，与归档配置一致 |
| seed=42、generation-config=vllm | 固定服务侧生成配置基准 |

在 **B** 做健康检查：

```bash
curl --noproxy '*' -i http://127.0.0.1:8000/health
```

curl 发送 HTTP 请求；-i 显示状态；--noproxy '*' 避免本机请求经过代理。星号和引号一起复制。返回 **200 OK** 后再继续；连接失败则看 A 是否还在加载或已经报错。

## 4. 在 B 先预览，再跑 OFF

预览不会访问服务，也不会创建结果目录：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/smoke/shared_bench.jsonl --output-dir runs/smoke/shared_off_run1 --apc off --cache-state hot --dry-run
```

| 参数 | 含义 |
|---|---|
| --model | 本地模型/tokenizer 路径，与 A 保持一致 |
| --dataset | 本次读取哪一份数据，6 行就是 6 个正式请求 |
| --output-dir | 本轮结果的独立目录，必须不存在 |
| --apc off | 预期服务端已经关闭 APC，脚本会核验；这个参数不会切换服务 |
| --cache-state hot | 正式测量前先发第一条 shared 输入做前缀预热 |
| --dry-run | 只显示最终官方压测命令，不进行实验 |

预览输出很多参数是正常的，不需要再把它的输出复制执行。

**OFF 为什么还使用 hot？** 这里 hot 指“先发一次同样输入”的准备步骤。OFF 也做该步骤，使两组准备工作一致，但只有 ON 能获得 APC 复用。cold 不做该次前缀预热。

真正运行时去掉 --dry-run：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/smoke/shared_bench.jsonl --output-dir runs/smoke/shared_off_run1 --apc off --cache-state hot
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/smoke/independent_bench.jsonl --output-dir runs/smoke/independent_cold_off_run1 --apc off --cache-state cold
```

每条完成后再执行下一条。shared_off_run1 表示共享输入、关闭缓存、第 1 轮；independent_cold_off_run1 同理。

脚本会先做三次服务预热，再调用官方压测器。运行时正式压测日志写入文件，B 暂时没有输出不一定是卡住。成功后打印 result.json 路径，并返回命令提示符。

## 5. 查看结果是否成功

查看 shared OFF 的运行清单：

```bash
python -m json.tool runs/smoke/shared_off_run1/manifest.json
```

这条命令只是把 JSON 排版显示，不修改内容。应看到 `"status": "completed"`。若为 failed，查看 error；如果进程已退出但仍为 preparing/running，也不能当成成功。

查看结果：

```bash
python -m json.tool runs/smoke/shared_off_run1/result.json
```

小测试应满足：

| 字段 | 预期 |
|---|---|
| completed / failed | 6 / 0 |
| input_lens | 当前输入和 tokenizer 下为 2039；正式 100 条则为 2039–2041 |
| output_lens | 六条全部 64，不能是 256 |
| mean_ttft_ms | 平均首 token 毫秒数，不要求某个固定值 |

检查日志最后 40 行：

```bash
tail -n 40 runs/smoke/shared_off_run1/benchmark.log
```

若准备阶段就失败，benchmark.log 可能未生成，先看终端错误和 manifest。脚本现在会显示 HTTP 错误的服务端详细原因。

每轮有 dataset.jsonl、manifest.json、result.json、benchmark.log、metrics_before.txt、metrics_after.txt 六份证据。输入副本和指纹证明测量对象；manifest 记录配置、缓存 reset 和预热情况；两个 metrics 文件用于核对计数窗口。

## 6. 切换到 ON，再测两组

等 B 的 OFF 请求都结束。在 **A** 按 Ctrl+C 停止服务，等命令提示符回来，然后启动 ON：

```bash
bash scripts/serve.sh on /mnt/d/models/Qwen2.5-1.5B-Instruct
```

回到 **B** 检查 /health 返回 200，再执行：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/smoke/shared_bench.jsonl --output-dir runs/smoke/shared_on_run1 --apc on --cache-state hot
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset runs/datasets/smoke/independent_bench.jsonl --output-dir runs/smoke/independent_cold_on_run1 --apc on --cache-state cold
```

按第 5 步核验。ON 清单中 cache_reset_success 必须是 true；OFF 为 null，因为没有启用 APC。

四组都成功后，在 B 分析小测试：

```bash
python scripts/audit_results.py --results-dir runs/smoke --output-dir runs/smoke-report --runs 1 --requests 6
python scripts/plot_results.py --summary runs/smoke-report/summary.csv --output-dir runs/smoke-report/figures
```

--results-dir 指原始结果位置，--output-dir 指汇总写到哪里。--runs 1 --requests 6 告诉校验器这是小批次。汇总与原始结果分开放，避免把报告文件夹当成一次实验。

四组各 6 条只用于检查流程。单轮标准差为 0，不表示性能稳定。

## 7. 正式跑五轮

正式数据已在 data 下：

```bash
wc -l data/shared.jsonl data/independent.jsonl
```

wc -l 数行数，预期各 100，合计 200。不要在 ON/OFF 之间重新生成不同数据。

在 **A 运行 OFF** 时，B 执行第 1 轮这两条：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/shared.jsonl --output-dir runs/next/shared_off_run1 --apc off --cache-state hot
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/independent.jsonl --output-dir runs/next/independent_cold_off_run1 --apc off --cache-state cold
```

切换 **A 到 ON**，B 执行：

```bash
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/shared.jsonl --output-dir runs/next/shared_on_run1 --apc on --cache-state hot
python scripts/run_benchmark.py --model /mnt/d/models/Qwen2.5-1.5B-Instruct --dataset data/independent.jsonl --output-dir runs/next/independent_cold_on_run1 --apc on --cache-state cold
```

继续第 2～5 轮：只把各条命令的保存目录末尾 run1 改为 run2、run3 等，数据路径不变。新批次建议按下表执行：

| 轮次 | 先测两类输入的模式 | 后测模式 |
|---|---|---|
| 1 | OFF | ON |
| 2 | ON | OFF |
| 3 | OFF | ON |
| 4 | ON | OFF |
| 5 | OFF | ON |

每切换模式都停止并重启 A。同模式下可直接跑下一条命令，脚本自行重做预热与缓存控制。正式归档的旧批次没有做到交替，报告已如实标明；上表用于改进下一批。

最后应有 20 个成功目录、2000 个正式请求，所有输出为 64。预热请求不计入这 2000 条。汇总新结果：

```bash
python scripts/audit_results.py --results-dir runs/next --output-dir runs/next-report
python scripts/plot_results.py --summary runs/next-report/summary.csv --output-dir runs/next-report/figures
```

默认严格要求 5 轮 × 100 请求，不足会报错。查看新报告，而不是覆盖仓库的正式 reports；确认协议和结论后再作为一个新版本发布。

## 8. 常见问题

| 现象 | 检查方法 |
|---|---|
| 缺包/找不到 vllm | 当前终端激活环境了吗？which python 是否正确？ |
| 找不到脚本或输入文件 | pwd 是否是仓库根目录？相对路径是否正确？ |
| Connection refused | A 是否已就绪？是否在 8000 端口？ |
| /server_info 或 /reset_prefix_cache 返回 404 | 用 serve.sh 启动，它设置了开发接口环境变量 |
| Requested APC state differs | B 的 --apc 必须与 A 的实际启动模式一致，改目录名无效 |
| reset 返回 false | 是否有其他请求还在运行？当前轮不能当作冷测试成功 |
| FileExistsError | 目录已经存在，工具拒绝覆盖 |
| 超过上下文长度 | 阅读完整 HTTP 错误，确认模型路径、tokenizer 与服务上下文一致 |
| Expected 5 runs / unexpected directory | 缺轮或失败/重试目录混进同一批次 |

失败轮保留在批次目录外，例如 runs/failed；把失败目录移出后，再用原规范名字重跑。不要在同一批次中保留 shared_on_run1_retry，校验器会拒绝它。

不要为了让测试通过关闭输出长度、缓存状态或成功数检查；这些检查是为了避免又得到条件不一致的对照。

## 9. 参数背后的原理

入口自动加上 --skip-chat-template，避免客户端先套模板、服务端再套一次；--custom-output-len -1 明确从每行读取输出长度，避免被官方默认值覆盖；--temperature 0 --ignore-eos 控制生成策略和输出长度。

预热先用实际 tokenizer 计算模板后的长度，保留生成预算。服务预热后 ON 清空 APC，hot 再做前缀预填充。官方 benchmark 的隐藏预热和 ready-check 都关闭，避免破坏这个顺序。

默认并发为 1，request_rate=inf 表示不人为等待固定到达间隔，允许时尽快发送下一条，**不是无限并发**。TTFT 不包含客户端等待并发许可的时间。

统计以全量请求为主；各轮首请求偏慢也保留。更多口径见 [方法说明](../docs/methodology.md)。

上面全部使用单行命令。如果看到其他文档把一条命令拆为多行，Bash 行尾的反斜杠表示下一行接着写；反斜杠后不能有空格。这里无需使用 MODE/ROUND 变量或循环。
