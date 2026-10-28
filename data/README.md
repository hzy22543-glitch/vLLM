# 固定合成输入

| 文件 | 用途 | 请求数 | 实际 chat 输入 tokens | 输出 tokens |
|---|---|---:|---:|---:|
| baseline.jsonl | 两种到达条件 | 200 | 159–161 | 64 |
| concurrency.jsonl | 三种并发 | 512 | 159–161 | 64 |
| shared.jsonl | 共享长前缀 APC 对照 | 100 | 2039–2041 | 64 |
| independent.jsonl | 独立前缀 APC 对照 | 100 | 2039–2041 | 64 |

每行包含原始用户 prompt 和 output_tokens。服务端只套一次 chat 模板。比较条件必须复用相同文件，不能重新随机生成。

baseline-workload.json 和 concurrency-workload.json 是原始生成记录。其中 shared/independent SHA256 对应转换前的源文件，不是本目录转换后的 benchmark JSONL；后者由 [证据索引](../docs/evidence-sha256.json) 和每轮 manifest 校验。转换前文件保存在本机整理前备份中。

新短负载使用 build_workload.py 的 repeat=3，APC 使用 repeat=50，seed/模板/模型仍应以实际协议和输出记录为准。模型权重不在此目录。
