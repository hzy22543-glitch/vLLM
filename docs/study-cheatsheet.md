# vLLM 项目复习速查表

配套：[完整学习手册](study-guide.md)。本页用于十分钟回顾；不代替正式复现步骤。数据基于 2026-10-28 归档。

## 一句话记住项目

在 RTX 4080 Laptop GPU / 12 GB 上，使用 Qwen2.5-1.5B-Instruct 和 vLLM 0.31.0，完成基线、有限批次并发、前缀缓存三组实验，共 **35 轮、7808 条正式请求**。

自己的工程工作是实验设计、负载控制、运行与排错、证据归档、统计复算；没有重新实现引擎或 APC 算法。

## 最重要的时间线

~~~text
t0 到达客户端 → 等待许可 → t1 发送 → t2 首 token → t3 完成
~~~

| 指标 | 公式/含义 |
|---|---|
| 客户端排队 Q | t1−t0 |
| TTFT | t2−t1 |
| E2EL | t3−t1，本项目的发送后延迟 |
| 到达至完成 | Q+E2EL，逐请求配对后再求分位数 |
| TPOT | (E2EL−TTFT)/(输出 token 数−1)，输出至少 2 个 |
| 输出吞吐 | 总输出 tokens / 正式测量总秒数 |
| 合并多轮吞吐 | 各轮输出总和 / 各轮时长总和 |
| 降低率 | (原值−新值)/原值 |
| 缓存命中比例 | 正式窗口 Δhits/Δqueries，分母为 0 时不适用 |

result.json 的 ttfts、latencies、queue_times 数组单位是秒；mean_ttft_ms 等汇总字段是毫秒。

**不能相加两个 P95；不能用轮吞吐平均值冒充合并吞吐；SD 不是置信区间。**

## 三组结果怎么讲

| 阶段 | 关键实测 | 正确解释 |
|---|---|---|
| W6 | low_rate 69.69、serial 110.34 tokens/s | 同为 C1，到达条件不同；低到达率包含等待 |
| W6 | serial P95 E2EL 0.585 s，到达至完成约 110.34 s | 后者包含客户端排队 |
| W7 | C32→64→128，吞吐 2304→3473→4326 tokens/s | 当前有限批次更快完成 |
| W7 | P95 E2EL 1.03→1.41→2.57 s | 单请求延迟随并发增加，存在取舍 |
| W8 | shared TTFT 106.08→19.53 ms | 降低 81.59%，主要节省重复前缀 prefill |
| W8 | independent TTFT 105.78→105.81 ms | 短公共前缀基本无收益，作为负对照 |
| W8 | shared 命中约 98.835%，independent 约 0.7765% | token 计数比例，不是缓存答案的请求比例 |

W6/W7 输入 159–161 tokens，W8 输入 2039–2041，输出都为 64。不同负载和并发不能混成一个“优化倍数”。

## 六组容易混淆的概念

| 这两个概念 | 区别 |
|---|---|
| prefill / decode | 处理输入 / 逐步生成输出 |
| KV Cache / APC | 保存历史 K/V / 复用匹配前缀的 K/V |
| 并发 / 到达率 | 同时执行多少 / 请求多快到达 |
| 服务预热 / 前缀预热 | 减少启动影响 / 让目标前缀进入缓存 |
| cold cache / 冷启动服务 | 缓存起始状态 / 服务尚未预热 |
| 显存分配 / 有效 KV 占用 | 包含权重与预留等 / 有效缓存状态所占部分 |

APC 不是答案缓存；命中也仍然需要生成新输出。

request_rate=inf 不等于无限并发；C1 仍一次只允许一条执行，其余可在客户端排队。

## 实验协议的关键顺序

~~~text
确认实际服务参数
→ 3 次无关服务预热
→ ON 时清缓存并确认成功
→ hot 时额外预热目标前缀
→ metrics_before
→ 正式请求
→ metrics_after
→ 检查完成数、失败数、实际 token 长度
~~~

shared OFF/ON 都做同样的额外前缀请求；只有 ON 能通过 APC 受益。independent cold 不做目标前缀预热。

## 排错速记

| 现象 | 优先检查 |
|---|---|
| health 200、生成 400 | 看生成请求的错误正文，不只看状态码 |
| 预热报长度错误 | 实际输入 tokens+输出预算是否超过 4096 |
| 请求输出变成 256 | 数据字段是否被官方压测器默认参数覆盖 |
| 输入 2039 变成 2068 | 聊天模板是否重复套用 |
| vllm 找不到 | 当前终端是否激活正确环境 |
| cold 结果不可信 | reset 是否成功，隐藏预热是否污染状态 |
| 目录已存在 | 使用新轮次目录，不覆盖原始证据 |
| GPU 内存很高 | 区分预留缓存池与活跃 KV，不直接判断瓶颈 |

当时的越界：4033+64=4097>4096。修复是按实际 token 计数并留输出预算，不是猜字符数。

## 只读复核入口

以下在 WSL Ubuntu 终端执行：

~~~bash
cd /home/administrator/vllm-lab-1
python3 scripts/check_repository.py
~~~

检查原始证据与文档链接。详细的无 GPU 计算练习见 [手册第 15 章](study-guide.md#chapter-15)。

要复算到新目录：

~~~bash
python3 scripts/analyze_project.py --output-dir runs/review-recomputed
~~~

该命令写派生结果，不改 results/。正式重跑按 [基线/并发步骤](baseline-concurrency.md) 与 [APC 步骤](reproduction.md) 操作。

## 六个文件记住证据在哪里

- dataset.jsonl：当轮输入。
- manifest.json：配置、版本、时间、预热、完成/失败状态。
- result.json：实际长度与逐请求结果。
- benchmark.log：压测过程和错误。
- metrics_before.txt / metrics_after.txt：正式窗口前后服务计数。
- 并发组另有 gpu.csv；服务日志位于 results/sessions/。

## 汇报时必须保留的边界

1. W7 每轮仅 7–15 秒；不是持续容量或生产最优并发证明。
2. 并发跨两次服务会话，run3 实际较早。
3. GPU 采样含预热且有近 4 秒间隔；没有逐轮 CPU 时序。
4. APC 未交替 OFF/ON，存在时间顺序混杂可能。
5. 模型/tokenizer 不可变 revision 未记录。
6. 旧退化根因未闭环；CPU 火焰图不直接等于 GPU 耗时。
7. 25 项测试与 CI 检查通过，不等于云端重跑了本机 GPU 实验。

## 闭卷能答这五题，就抓住了主线

1. 为什么 serial 的 E2EL 约半秒，总等待却可达 110 秒？
2. 为什么并发增加，吞吐和单请求延迟会一起上升？
3. 为什么 APC 主要改善 TTFT，而不是同幅度改善 TPOT？
4. 为什么需要 independent 负对照与实际 token 检查？
5. 为什么当前结果不能证明最优并发或已修复旧退化？

答案与更多练习见 [手册第 16 章](study-guide.md#chapter-16)。
