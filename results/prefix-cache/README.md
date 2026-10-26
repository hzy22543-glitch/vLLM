# 正式原始数据

四组目录：shared_off、shared_on、independent_cold_off、independent_cold_on；每组 run1–run5，每轮 100 请求。20 个目录均为 completed，全部 2000 请求成功，实际输出均为 64 tokens。

每个目录保留完整输入副本、运行清单、原始结果、压测日志和前后指标快照。重复保留输入是为了让每轮证据自包含；整个数据量适合普通 Git，无需加入模型权重。

这些目录不用于新测试输出。新测试写入默认忽略的 runs/ 下，避免覆盖本次证据。目录名中的 v2 表示修正后的正式协议，不代表 vLLM 版本。

本地复核：在仓库根目录执行 `python3 scripts/audit_results.py`。查看结果请打开 [正式报告](../../reports/prefix-cache.md)。
