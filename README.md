# vLLM Inference Performance Lab

单卡推理性能实验：从稳定基线出发，测量并发带来的吞吐/延迟取舍，再验证 Automatic Prefix Caching（APC）的适用条件。

**35 轮、7808 条正式请求，全部成功。** 项目使用 vLLM 现有服务与官方压测器；自己的工作是构造负载、控制实验条件、保存证据、校验统计与解释结果，没有重新实现推理引擎或缓存算法。

## 实验结论

| 实验 | 设计 | 可支持的结论 |
|---|---|---|
| 基线（W6） | 两种到达条件，各 3 × 200 请求，C1 | 低到达率 69.69 tokens/s；连续单并发 110.34 tokens/s；两组轮间最大/最小差分别约 1.00% / 0.20% |
| 并发（W7） | C32/C64/C128，各 3 × 512 请求 | 吞吐 2304 → 3473 → 4326 tokens/s，同时合并 P95 E2EL 为 1.03 → 1.41 → 2.57 秒 |
| 前缀缓存（W8） | 共享/独立输入 × OFF/ON，各 5 × 100 请求 | 共享前缀平均 TTFT 106.08 → 19.53 ms，降低 81.59%；独立输入基本无变化 |

表中吞吐按总输出 tokens / 总测量时间计算；下图吞吐柱为轮均值，误差条为轮间样本 SD，两种口径在 CSV 中分别保存。基线与并发输入为 159–161 tokens，APC 为 2039–2041 tokens；输出固定 64。各阶段负载不同，不能把表中吞吐直接作为优化前后倍数。

![基线与并发对照](reports/figures/load-overview.png)

![前缀缓存对照](reports/figures/prefix-cache-ttft.png)

**结论范围：W7 是 7–15 秒的有限批次测试，不能当作持续负载容量或最优并发证明。** 旧实验的退化根因尚未闭合，本次没有声称已经完成 UVA 修复。三部分都保留首请求和全部慢请求。

## 快速复核：不需要 GPU

在仓库根目录，使用 Python 3.12：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/analyze_project.py
python3 scripts/check_repository.py
```

三条命令依次测试代码、复算三部分实验、核对原始文件指纹与文档链接。只使用 Python 标准库，不下载模型，不启动服务。预期看到测试 OK、35 runs / 7808 requests、evidence files unchanged。

重画两张图：

```bash
python3 -m pip install -r requirements-analysis.txt
python3 scripts/plot_results.py
```

自动汇总写入 reports/，原始数据不变。使用 --output-dir 可把复算结果写到新目录。GitHub Actions 自动执行测试、全量校验和派生表一致性检查，见 [检查记录](https://github.com/hzy22543-glitch/vLLM/actions/workflows/check.yml)。

## 阅读与复现顺序

1. [项目总报告](reports/project-report.md)：验收结论、三个实验如何组成完整项目。
2. [基线报告](reports/baseline.md) → [并发报告](reports/concurrency.md) → [APC 报告](reports/prefix-cache.md)：数据、解释与局限。
3. [基线/并发操作步骤](docs/baseline-concurrency.md) 与 [APC 操作步骤](docs/reproduction.md)：两个终端如何分工、每条命令的参数和成功标志。
4. [指标与方法](docs/methodology.md)：TTFT、TPOT、E2EL、客户端排队与统计口径。

模型为 Qwen2.5-1.5B-Instruct；硬件 RTX 4080 Laptop GPU / 12 GB，WSL Ubuntu，FP16。记录版本为 Python 3.12.3、vLLM 0.31.0、PyTorch 2.13.0+cu132、Transformers 5.17.0。权重不包含在仓库中；[运行依赖](requirements-runtime.txt) 是直接版本清单，不是完整环境锁文件。模型与 tokenizer 的不可变 revision 未记录。

## 目录

| 目录 | 内容 |
|---|---|
| [scripts](scripts/analyze_project.py) | 生成/转换负载、启动服务、单轮压测、统一校验和绘图 |
| [data](data/README.md) | 四份固定输入及新负载的生成记录 |
| [results](results/README.md) | 35 轮原始结果、9 份 GPU 采样、2 份服务日志快照 |
| [reports](reports/project-report.md) | 人工解释、可自动复算的 CSV/Markdown、图片 |
| [docs](docs/methodology.md) | 复现步骤、证据指纹、路径迁移记录、提交方法 |
| [tests](tests/test_load_analysis.py) | 无 GPU 的协议、统计、遥测和故障回归测试 |
| runs/ | 新实验/正在写入的日志；默认不提交 |

GPU 采样覆盖整个 runner（含预热），部分间隔接近 4 秒；没有逐轮 CPU 时序。并发实验跨两次服务会话，run3 实际更早。APC 实验未交替 OFF/ON 顺序。这些限制在报告中保留，不补造数据。

第三方框架与模型来自 [vLLM](https://github.com/vllm-project/vllm) 和 [Qwen](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)。实验脚本有 AI 辅助编写与修订；原始性能数据由本机实验生成。后续变更按 [提交说明](docs/publishing.md) 操作。
