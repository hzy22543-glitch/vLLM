# 仓库与后续提交

目标仓库：https://github.com/hzy22543-glitch/vLLM

上传内容包括脚本、固定合成输入、报告、图片、正式原始证据和测试。runs/、虚拟环境、模型权重、旧实验备份均已忽略。

后续修改前先拉取最新 main，在仓库根目录复核：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit_results.py
python3 scripts/check_repository.py
git diff --check
git status --short
```

检查变更后提交并上传：

```bash
git add .
git diff --cached --check
git commit -m "Describe the actual change"
git push origin main
```

提交信息应替换成对实际修改的描述。Git 作者使用自己的身份。本项目尚未选择开源许可证；模型和第三方依赖的许可证不随本项目改变。
