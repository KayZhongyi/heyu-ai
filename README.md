# 禾语 AI · Heyu AI

> 面向农业品牌与产销团队的可信 AI 内容工作台
>
> **让经过审核的产品事实，变成来源可查、版本可审、效果可复盘的营销内容。**

[![CI](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![License](https://img.shields.io/badge/License-Apache--2.0-5B7083)
![Status](https://img.shields.io/badge/Status-Engineering%20MVP-EA6A5A)

[快速启动](#3-分钟本地启动windows) · [当前能力](#当前能力) · [团队协作](#团队协作) · [产品边界](#必须守住的产品边界) · [贡献指南](CONTRIBUTING.md)

禾语 AI 是一个可本地运行、可持续扩展的农产品内容与运营平台。它把品牌档案、农产品事实和审核通过的知识资料组织成可信上下文，生成短视频脚本、直播话术及其他营销内容，并保留完整的来源、版本、审核与运营记录。

仓库目前处于**私有协作与发布前审查阶段**。代码按未来开源标准建设，但在负责人明确批准前，不得公开仓库、业务资料或部署地址。

## 当前能力

| 模块 | 已实现 |
| --- | --- |
| 组织与权限 | 多租户组织、六种角色、成员邀请、角色变更即时生效、旧令牌撤销 |
| 品牌资产 | 品牌与农产品档案、编辑、提交审核、通过或退回 |
| 可信知识库 | TXT / Markdown / CSV 导入、来源指纹、修订链、人工审核 |
| AI 内容创作 | 短视频、直播、评论回复、社交文案、标题与封面文案 |
| 可信生成 | 仅使用审核资料、来源引用校验、模型与 Prompt 记录、失败留痕 |
| 内容治理 | 不可覆盖的内容版本、人工修改、提交与审核 |
| 运营闭环 | 发布登记、表现数据快照、人工视频诊断、改进 Brief、后续草稿 |
| 国际化 | 简体中文、香港繁体中文、英文切换；不改写用户业务数据 |
| 工程化 | Windows 本地启动、SQLite、Docker / PostgreSQL、自动化测试与 CI |

## 先看平台

启动后访问：

- 首页：`http://127.0.0.1:8000/`
- 工作台：`http://127.0.0.1:8000/workspace/`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## 3 分钟本地启动（Windows）

普通演示**不需要 Docker、Ollama、Node.js、域名或付费模型 API**。

### 前置条件

- Windows 10 / 11
- Python 3.12
- 建议至少预留 2 GB 磁盘空间

### 启动步骤

1. Clone 或下载仓库到本地磁盘。
2. 首次运行双击 `安装禾语AI.bat`。
3. 安装完成后双击 `启动禾语AI.bat`。
4. 浏览器打开 `http://127.0.0.1:8000/`。

虚拟环境、SQLite 数据库及运行文件默认都保存在项目目录中，不写入大型全局运行环境。需要指定 Python 时，可设置环境变量 `HEYU_PYTHON`。

## 开发者启动

```powershell
git clone https://github.com/KayZhongyi/heyu-ai.git
cd heyu-ai

.\scripts\setup-windows.ps1
.\scripts\start-windows.ps1
```

可选 Docker / PostgreSQL：

```bash
cp .env.example .env
docker compose up --build
```

默认使用零成本的 `DeterministicProvider`，用于验证完整业务流程。它不是实际大语言模型。接入外部模型时必须通过 provider 边界，并且不得把 API Key 提交到仓库。

## 仓库结构

```text
apps/
  api/                         FastAPI、SQLAlchemy、Alembic 与业务服务
  web/                         品牌首页与浏览器工作台
docs/
  architecture.md              系统边界与架构
  product.md                   产品范围与业务规则
  operations.md                启动、备份、恢复与运维
  release-gates.md             Demo、工程 MVP 与公网发布门槛
  acceptance-test.md           人工验收流程
scripts/
  audit-repository.py          仓库发布审计
  test-browser-e2e.js          浏览器端到端测试
  test-i18n.js                 三语完整性测试
  test-content-renderer.js     内容渲染测试
```

## 团队协作

加入项目后请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [docs/product.md](docs/product.md)。

### 新成员第一天

1. 接受 GitHub 私有仓库邀请并 Clone 项目；
2. 按[本地启动步骤](#3-分钟本地启动windows)运行平台，确认首页、工作台和 API 文档可以访问；
3. 阅读 [docs/product.md](docs/product.md) 了解产品范围，阅读 [docs/architecture.md](docs/architecture.md) 了解系统边界；
4. 在 Issue 或团队沟通渠道中确认任务负责人，避免多人重复修改同一模块；
5. 从最新 `main` 创建个人分支，通过 Pull Request 提交，不直接向 `main` 推送。

可以从以下方向参与：

- **产品与内容**：梳理真实业务流程、验收标准和三语营销文案；
- **前端体验**：工作台交互、响应式布局、无障碍与浏览器测试；
- **后端与 AI**：权限、知识库、生成链路、审核流和模型 Provider；
- **质量与工程**：测试、CI、Docker / PostgreSQL、文档和发布审计。

推荐流程：

1. 从最新 `main` 创建短生命周期分支；
2. 一次提交只处理一个明确问题；
3. 不绕过服务端权限、审核或租户隔离；
4. 提交前运行相关测试；
5. 通过 Pull Request 合并，不直接覆盖他人改动。

```powershell
git switch main
git pull --ff-only
git switch -c feat/short-description

python -m ruff check apps scripts
python -m pytest -q
node scripts/test-i18n.js
node scripts/test-content-renderer.js
```

涉及浏览器行为时再运行：

```powershell
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:e2e
```

## 必须守住的产品边界

- **租户隔离必须由服务端执行**，不能只在前端隐藏按钮。
- **AI 只能使用审核通过的资料**，未知引用和缺失引用必须失败关闭。
- **版本不可覆盖**，修改、审核、发布和复盘都必须留下历史。
- 不提交 `.env`、令牌、API Key、数据库、原始私密 PDF / PPT 或真实客户资料。
- 未经负责人确认，不调用付费服务、不公开仓库、不部署公网。
- 当前范围不包含 VR、医疗功能、数字人直播、联邦学习、区块链或无数据支撑的“爆款预测”。

## 真实能力边界

- `DeterministicProvider` 是开发与演示 provider，不是真实大语言模型。
- `lexical-v1` 是确定性的词法检索，不是向量数据库或完整语义 RAG。
- 视频诊断目前由人工录入结构化证据，不是自动视频理解。
- 发布模块记录发布事实，不会自动向社交平台发帖。
- 运营指标目前由人工录入，不会自动抓取第三方平台数据。
- 当前是工程化 MVP，不等于已获准直接提供公网商业服务。

详细发布条件见 [docs/release-gates.md](docs/release-gates.md)。

## License

[Apache License 2.0](LICENSE)
