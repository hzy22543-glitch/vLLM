# 原始实验数据

- [baseline](baseline/README.md)：6 轮 × 200 请求。
- [concurrency](concurrency/README.md)：9 轮 × 512 请求，附每轮 GPU CSV。
- [prefix-cache](prefix-cache/README.md)：20 轮 × 100 请求。
- sessions/：新基线/并发使用的两份服务日志快照，文件名为 UTC 启动时间。

共 35 轮、7808 条请求。每轮保留 dataset.jsonl、manifest.json、result.json、benchmark.log、metrics_before.txt、metrics_after.txt。归档中的路径与命令代表历史现场，迁移目录时不改写。

逐字节指纹在 [证据索引](../docs/evidence-sha256.json)；新证据的原位置见 [迁移映射](../docs/evidence-provenance.json)。新实验先写入被 Git 忽略的 runs/，校验后再归档。
