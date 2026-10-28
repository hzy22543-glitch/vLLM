# 项目整理记录

## 2026-10-26 初次 APC 发布

本仓库以完成验收的 APC 四组 20 轮为发布范围。早期 W6/W7 的探索不足以支撑本轮严格结论，未将其包装成新完成的负载扫描成果。

整理前完整目录已打包在本机仓库旁的 `vllm-lab-1-before-release-20261026.tar.gz`，共 292 个文件，已核对归档文件数量；备份不上传 GitHub。

从发布目录移出：
- 早期 results/w6、w7、w8 及旧图表；
- smoke-v2 和两次修复验证目录（其中一次是输出长度错误的失败实验）；
- review-originals、旧审查表和“尚未完成”状态的过时报告；
- 重复的旧 JSONL、fresh UUID 工具、只服务旧结果的分析入口。

保留并复核：
- results/prefix-cache 下 20 轮、120 个原始证据文件，全部保持原始字节；
- data 下两份与正式实验一致的公共输入；
- 生成/转换/运行/校验/绘图工具及必要历史环境背景。

补充：
- 统一使用正式批次作为默认分析目标；严格阻止错误结果进入统计；
- 修正固定写“5×6”的图注，显示真实轮次和样本数；
- 移除代码中的个人模型默认路径，改为显式传参；
- 加入无 GPU 测试、GitHub Actions、Git 忽略规则及发布文档。

不改写历史实验顺序：五轮确实都是 OFF→ON。缺失的模型 revision、逐轮遥测、完整启动日志保留为局限，没有补造。

## 2026-10-27 命名规范

工具统一放 scripts/，复现步骤放 docs/reproduction.md；正式结果目录改为 results/prefix-cache，图片改为 prefix-cache-ttft.png。Python 使用 snake_case，文档/实验目录使用有意义的英文名称。历史 manifest 中的原运行路径保留，不篡改历史命令；证据索引只迁移路径，SHA256 值不变。

## 2026-10-28 三阶段整合

整合前已将工作目录（不含 Git 元数据）保存到仓库旁 vllm-lab-1-before-integration-20261028.tar.gz，共 277 个文件；逐文件 SHA256 与归档内容核对一致。既有提交保存在 Git 历史中。

新归档 6 轮基线、9 轮并发、9 份 GPU CSV 和两份服务日志快照。c0128 改为 c128；原文件字节不变，映射见 evidence-provenance.json。保留两份转换后公共输入和原始 workload 记录。

删除已归档的 runs 重复结果/输入/遥测、vllm: command not found 的失败启动日志、过时计划文件、无实际功能的兼容分析入口及 w8 字节码目录。仍可能写入的服务日志留在被忽略的 runs/service-logs，发布版本使用冻结快照。旧 vllm-lab 目录与两份外部备份没有删除。

统一脚本为 analyze_project.py；APC 协议移到 audit_prefix_cache.py，新增 audit_load.py。重写总 README、基线/并发报告和复现步骤；图表和派生表采用明确的实验前缀。35 轮全部保留，未删除慢请求、未改写运行顺序，也未声称完成持续负载或 UVA 归因。
