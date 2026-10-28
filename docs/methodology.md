# 实验方法与统计约定

## 固定条件

项目统一验证三份协议：基线（低到达率/连续单并发，各 3×200）、并发（C32/64/128，各 3×512）、APC（两类输入×ON/OFF，各 5×100）。共同固定输出 64、seed 42 和保存的服务配置；基线/并发固定 APC OFF，APC 对照仅切换缓存开关。各阶段输入不同，不能混算优化倍数。

APC 小测试可显式指定 1 轮、6 请求。基线/并发校验固定正式数量；更换条件时应新建协议，不能混进已发布结果。

- 数据：同一负载所有轮次、两种开关复用同一个 JSONL，逐轮核对 SHA256。
- Chat：传原文，官方 custom 数据加载器跳过客户端模板；服务端套一次。
- 生成：temperature=0、ignore_eos；custom-output-len=-1 从每行 output_tokens 读取长度。
- 服务预热：3 条无关请求；真实模板长度不超过 min(2048, max_model_len−64)。
- 缓存：ON 在服务预热后 reset，必须 success=true；hot 再预填充第一条 shared 输入。
- 计时：官方压测 num-warmups=0、ready-check-timeout-sec=0，避免控制缓存后又发隐式预热。
- 比较：不同模式分开启动一个模型服务；下一批建议交替或随机安排模式顺序。

## 指标

TTFT 是实际请求发出到第一个输出 token 的客户端耗时。每请求 TPOT=(E2EL−TTFT)/(输出 tokens−1)，输出长度大于 1 时有定义。ITL 是相邻流式输出的间隔统计，不默认等于 TPOT。

输出吞吐=总输出 tokens/测量 duration。多轮汇总采用总 tokens/总 duration，不直接平均不同耗时轮次的吞吐。

全量 TTFT 均值包含每轮首请求。首请求与其余请求分开列出用于诊断，不作事后删样本。误差条为各轮均值的样本标准差；P50/P95 采用排序后线性插值。合并分位数是该批观测的描述，不是生产服务承诺。

client queue_times 不包含在 TTFT/E2EL 中。若讨论到达至完成时间，应按每条请求相加再算分位数。

命中率使用本轮 prefix_cache_hits_total / prefix_cache_queries_total 增量。精确匹配指标名称，排除 external_prefix_cache_*。只有 ON、分母大于零、查询增量与测得输入总数相同时才输出比例；否则留空。采样数相等支持窗口一致，但也不能检测到所有同时存在的外部请求，所以实验时应独占服务。

## 自动拒绝的结果

缺轮、未知重试目录、manifest 未完成、失败请求、缺少逐请求细节、非有限时延、输入指纹错误、ON/OFF 数据不一致、实际输出长度错误、缓存开关/reset/预热不符，以及配置或版本在条件间变化，都会导致校验失败。

校验器核对保存的配置，不把它当作完整机器状态证明。服务启动参数中的未保存字段、系统后台负载和模型权重 revision 仍是现有证据的边界。

## 原始证据

每轮 dataset.jsonl / manifest.json / result.json / benchmark.log / metrics_before.txt / metrics_after.txt 六个文件均保留原始字节。命令中的绝对路径是历史来源信息，换电脑后不能原样执行；请按操作说明传自己的 --model 路径。

文件指纹索引见 [evidence-sha256.json](evidence-sha256.json)。原始文件不为了“好看”修改路径或数值；重新生成的表和图存放在 reports。脚本修改也不会改变已归档数据的实验时间或来源。

官方机制参考：[vLLM 0.31.0 APC](https://docs.vllm.ai/en/v0.31.0/features/automatic_prefix_caching/)。实现参数已按本机 vLLM 0.31.0 的 CLI 与数据加载代码核验；升级版本后需重新核对行为。

## 并发与遥测的附加约定

GPU CSV 以 UTC+08 解析，必须按时间递增并覆盖 manifest 起止区间；N/A 不填 0。汇总覆盖整个 runner，包含预热和客户端启动，不能冒充精确 benchmark 窗口。轮次按真实时间另行排序，run 编号不是时间顺序。

服务日志与运行会话仅按时间区间关联；没有逐轮 PID 记录。有限批次 duration 不足 15 秒，不能当持续负载容量。GPU 分配显存和活跃 KV 使用量是不同概念。
