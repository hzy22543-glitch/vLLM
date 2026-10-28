# 并发证据

c032、c064、c128 各 3 轮，每轮 512 请求；APC OFF、到达率 inf。实际输入 159–161、输出 64 tokens。gpu.csv 为对应轮次的原始 GPU 采样。

run3 实际早于 run1/2，来自另一服务会话；目录编号不代表时间顺序。c128 原名 c0128，历史 manifest 保持原样。

[解释与局限](../../reports/concurrency.md)。公共输入为 [data/concurrency.jsonl](../../data/concurrency.jsonl)。这是不足 15 秒的有限批次测量。
