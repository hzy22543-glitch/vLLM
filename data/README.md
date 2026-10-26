# 固定输入

[shared.jsonl](shared.jsonl) 与 [independent.jsonl](independent.jsonl) 各 100 行，每行包含 prompt、output_tokens=64。内容是程序生成的中文合成输入，不含模型权重或采集的个人对话。

两份文件与正式结果第一轮 dataset.jsonl 字节相同。ON/OFF 必须使用同一份输入，不在切换模式时重新生成 UUID。

真实模板长度 2039–2041 tokens；公共前缀核验见 [workload_check.json](../reports/workload_check.json)。文件生成逻辑在 [build_workload.py](../scripts/build_workload.py)，格式转换在 [prepare_bench.py](../scripts/prepare_dataset.py)。
