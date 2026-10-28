# 基线证据

low_rate_run1–3：到达率 1 req/s；serial_run1–3：到达率 inf。两者客户端并发都是 1，每轮 200 请求，APC OFF，实际输入 159–161、输出 64 tokens。

[解释与局限](../../reports/baseline.md)。输入副本保留在每轮目录，公共副本为 [data/baseline.jsonl](../../data/baseline.jsonl)。没有逐轮 GPU CSV。
