# 禾语 AI 营销内容离线评测

当前版本：

- 题集：`marketing-offline-v1`
- 规则：`marketing-rules-v2`
- 基线：`baseline-v2.json`

运行：

```bash
python scripts/evaluate-content-quality.py
```

更新候选基线：

```bash
python scripts/evaluate-content-quality.py \
  --write-baseline outputs/marketing-quality-baseline-candidate.json
```

评测默认调用零成本、离线且不写业务数据库的
`DeterministicMarketingProvider`。报告中的 `input_tokens`、
`output_tokens` 和 `estimated_cost` 在 Provider 未返回真实计量时必须为
`null`，不能以 `0` 代替未知值。

> 规则评分只衡量结构、事实保留、禁用声明、引用白名单、语言、营销表达、
> 平台适配和可拍性，不代表真实播放量、互动率、成交量或传播效果。
