# 参与禾语 AI 开发

感谢参与禾语 AI。这个项目不是一次性比赛页面，而是按可长期维护的商业级平台建设。请优先保证业务正确、权限可靠、资料可追溯，再考虑视觉扩展。

## 开始之前

1. 阅读 `README.md`、`docs/product.md` 和 `docs/architecture.md`。
2. 确认需求没有突破 `docs/release-gates.md` 中的当前阶段边界。
3. 不确定核心业务规则、付费服务、真实资料或视觉方向时，先在 Issue / PR 中确认。

## 分支与提交

- 从最新 `main` 创建分支。
- 建议命名：`feat/...`、`fix/...`、`docs/...`、`test/...`。
- 一次 PR 解决一个清晰问题，避免顺手进行大范围重构。
- 不回退或覆盖其他成员的并行改动。
- Commit 建议采用：`feat: ...`、`fix: ...`、`test: ...`、`docs: ...`。

## 完成定义

一个改动至少需要：

- 行为与产品规则一致；
- 服务端权限和租户隔离成立；
- 必要的自动化测试已新增或更新；
- 三种语言没有缺失 key 或明显机械翻译；
- 不包含密钥、数据库、业务原件或其他隐私数据；
- 相关文档与运行方式仍然准确。

## 本地验证

```powershell
python -m ruff check apps scripts
python -m ruff format --check apps scripts
python -m pytest -q
node scripts/test-i18n.js
node scripts/test-content-renderer.js
python scripts/audit-repository.py
```

涉及用户流程、权限或前端行为时：

```powershell
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:e2e
```

## 数据与安全

- 只使用合成数据，除非资料所有者明确授权。
- 不将 `.env`、API Key、Token、SQLite / PostgreSQL 数据导出提交到 Git。
- 不把仓库、截图、部署地址或业务资料擅自转为公开。
- 前端隐藏不等于授权；每个写操作都必须由 API 再次验证角色和组织。
- 生成内容必须保留来源，且不允许模型自行伪造引用。

## Pull Request

PR 描述应说明：

1. 改了什么；
2. 为什么这样改；
3. 如何验证；
4. 风险和未完成事项；
5. 如涉及 UI，附桌面端与窄屏截图。

未经 CI 与人工审阅，不要把重大改动直接合入 `main`。
