# vLLM Prefix Cache Lab

在单卡推理服务上验证 **Automatic Prefix Caching（APC）什么时候有效**：对比共享长前缀与独立前缀两种输入，固定生成长度，保存每轮配置、缓存状态与原始请求数据。

这是一项基于 vLLM 现有功能的实验工程项目。工作包括负载构造、缓存状态控制、基准测试、结果校验和可复现报告，没有重新实现 vLLM 的缓存算法。

## 结果

20 轮、2000 条正式请求全部成功。每个条件重复 5 轮，每轮 100 条；输入 2039–2041 tokens，输出全部为 64 tokens；客户端并发上限 1。

| 负载 | APC OFF 平均 TTFT | APC ON 平均 TTFT | 结论 |
|---|---:|---:|---|
| 共享长前缀，预填充后 | 106.082 ms | 19.526 ms | 降低 **81.59%** |
| 独立前缀，冷状态开始 | 105.782 ms | 105.809 ms | 基本无变化 |

共享组输出吞吐由 95.74 提升至 110.41 tokens/s；TPOT 由 8.924 变为 8.888 ms，变化很小。这里的结果只适用于测得的单卡、模型和负载，不能当作高并发容量或 decode 加速结论。

![完整请求 TTFT 对照](reports/figures/prefix-cache-ttft.png)

详见 [正式实验报告](reports/prefix-cache.md)、[逐轮明细](reports/runs.csv) 和 [自动复算表](reports/computed.md)。

## 不启动 GPU，也能复核结果

在仓库根目录使用 Python 3.12 执行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit_results.py
python3 scripts/check_repository.py
```

这三条分别检查代码行为、20 轮实验完整性以及原始证据指纹/文档链接。只用 Python 标准库，不下载模型，不向服务发请求。预期看到测试 `OK`、`20 runs validated`、`120 evidence files unchanged`。

需要重画图时，在已有 Python 环境中安装分析依赖：

```bash
python3 -m pip install -r requirements-analysis.txt
python3 scripts/plot_results.py
```

汇总写入 `reports/`，图片写入 `reports/figures/`。不会覆盖正式原始数据。也可用 `--output-dir` 将复算报告写到其他目录。

## 自己重新运行实验

按 [逐步操作说明](docs/reproduction.md) 执行：两个终端分别运行服务和实验，先做 6 条小测试，再完成正式对照。文档逐项解释命令、参数和成功标志。

代码不固定某个人的模型位置：启动服务和测试时均显式传入本地模型路径。实验使用的直接依赖版本列在 [requirements-runtime.txt](requirements-runtime.txt)，GPU 环境需配套安装 CUDA 兼容的 PyTorch/vLLM；该文件不是完整依赖锁文件。仅分析归档数据不需要安装它。

记录环境：RTX 4080 **Laptop GPU / 12 GB**，WSL Ubuntu，Python 3.12.3，vLLM 0.31.0，PyTorch 2.13.0+cu132，Transformers 5.17.0，FP16。模型为 Qwen2.5-1.5B-Instruct，模型权重不包含在仓库中。

## 仓库结构

| 路径 | 内容 |
|---|---|
| [scripts/run_benchmark.py](scripts/run_benchmark.py) | 一轮实验入口：预热、核对 APC、清缓存、官方压测、保存结果 |
| [scripts/serve.sh](scripts/serve.sh) | 固定配置启动 ON/OFF 服务，保存启动日志 |
| [scripts/audit_results.py](scripts/audit_results.py) | 严格校验四组实验、配对输入和统计，生成报告 |
| [复现实验](docs/reproduction.md) | 负载生成/格式转换/分析兼容入口/绘图 |
| [data](data/README.md) | 两份正式合成输入，ON/OFF 复用同一文件 |
| [results/prefix-cache](results/prefix-cache/README.md) | 20 轮原始证据；每轮六个文件，保持原始字节 |
| [reports](reports/prefix-cache.md) | 正式报告、复算表、图片、环境与 tokenizer 核验 |
| [tests](tests/test_benchmark_pipeline.py) | 无 GPU 测试，包括两次真实脚本故障的回归检查 |
| [docs](docs/methodology.md) | 指标口径、实验控制、整理记录、提交方法 |
| `runs/` | 你新运行的结果和服务日志，默认不进入 Git |

GitHub Actions 会自动运行无 GPU 测试、归档校验和文档链接检查；当前只在本机执行过这些检查，远程 CI 需推送后运行。

## 结论边界

- 每轮都先测 OFF、后测 ON，未随机化或交替顺序，可能存在时间/温度漂移。
- 模型与 tokenizer 的不可变 revision 未记录；现有输入指纹、运行版本和 token 数可以核验，但不是完整环境快照。
- 首请求仍有较高延迟，全部保留在主结果中；没有事后删除慢请求。
- 只有一个模型、一个 GPU、一个输入长度范围和一种输出长度。独立组的小幅差异不构成可靠收益证据。
- 仓库只发布本轮完成验收的 APC 实验。早期 W6/W7/W8 探索已移出，未用作本轮性能结论。

第三方框架与模型分别来自 [vLLM](https://github.com/vllm-project/vllm) 和 [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)。项目中的实验脚本有 AI 辅助编写与修订；原始结果由本机实验生成，统计可用上述命令复核。

准备上传时参考 [GitHub 提交说明](docs/publishing.md)。

## 后续：基线与并发优化

W6–W7 的已有问题、分步命令和验收标准见 [基线与并发改进计划](docs/baseline-concurrency-plan.md)。这是后续工作计划，未混入本轮已完成的 APC 结论。
