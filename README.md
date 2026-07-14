# 禾语 AI · Heyu AI

> 面向农业品牌与产销团队的可信 AI 内容工作台
>
> **让经过审核的产品事实，变成来源可查、版本可审、效果可复盘的营销内容。**

[![CI](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![License](https://img.shields.io/badge/License-Apache--2.0-5B7083)
![Status](https://img.shields.io/badge/Status-Engineering%20MVP-EA6A5A)

> 🌱 **欢迎大家加入禾语 AI，一起建设，一起把它做得更好。**

[如何体验](#组长与内容同学如何体验平台) · [快速开始](#快速开始) · [当前能力](#当前能力) · [参与开发](#参与开发) · [产品边界](#必须守住的产品边界) · [贡献指南](CONTRIBUTING.md)

禾语 AI 是一个可本地运行、可持续扩展的农产品内容与运营平台。它把品牌档案、农产品事实和审核通过的知识资料组织成可信上下文，生成短视频脚本、直播话术及其他营销内容，并保留完整的来源、版本、审核与运营记录。

本仓库已经公开，欢迎查看、下载、试用和参与建设。仓库只包含可公开的程序代码与合成演示资料，不包含项目原始 PDF / PPT、真实客户资料、密码、令牌或本地数据库。

![禾语 AI 平台首页预览](docs/assets/platform-preview.png)

## 组长与内容同学：如何体验平台

> **先说明：公开 GitHub 仓库不等于在线网站。** GitHub 页面展示的是源代码，不能直接在仓库网页内运行带账号、数据库和 AI 工作流的完整平台。
>
> 当前无需 Docker、Ollama、Node.js、域名或付费模型 API。推荐下载 Windows
> 便携体验包，无需预先安装 Python。

### 最简单：Windows 便携体验包

1. 打开本仓库右侧的 **Releases**；
2. 下载 `heyu-ai-windows-portable.zip`；
3. 解压 ZIP（不要直接在压缩包中运行）；
4. 双击 `HeyuAI.exe`；
5. 等待浏览器自动打开。关闭启动窗口即可停止平台。

便携体验包不要求安装 Python、Git、Docker、Ollama 或 Node.js，资料只保存在解压目录的
`data` 文件夹。当前体验版没有购买 Windows 代码签名证书；如果 SmartScreen 首次提示，
请确认文件来自本仓库的 Release，再选择“更多信息”→“仍要运行”。

### 源代码本地体验（适合开发者）

1. 点击绿色 **Code** 按钮，再点击 **Download ZIP**；
2. 解压下载的 ZIP；
3. 安装 **Python 3.12**；
4. 第一次双击 `安装禾语AI.bat`；
5. 以后双击 `启动禾语AI.bat`。

启动后也可以手动访问：

- 平台首页：`http://127.0.0.1:8000/`
- AI 工作台：`http://127.0.0.1:8000/workspace/`

每位体验者使用的是自己电脑上的本地平台，数据不会自动上传或与其他成员共享。安装或启动失败时，请把窗口中的完整错误信息发到团队群或 GitHub Issue，不要提交包含密钥、私人资料或真实客户数据的截图。

如果希望任何人点击一个网址就能使用，而不下载代码、不安装 Python，则仍然需要一个在线部署环境。可以按
[Render 免费在线 Demo 指南](docs/render-demo.md)创建短期演示环境。仓库是否公开与网站能否运行是两件不同的事；
实际连接 Render 和 GitHub 外部账号前必须由负责人确认授权。
部署完成后可使用 [`scripts/setup_demo_accounts.py`](scripts/setup_demo_accounts.py)
通过真实邀请流程创建两至三个展示账号。所有密码只从本机环境变量读取，不会写入仓库或验收报告。

## 新成员从这里开始

> 第一次加入？先完成下面四步。普通本地演示不需要 Docker、Ollama、Node.js、域名或付费模型 API。

1. Fork 本仓库，或将仓库 Clone 到本地；
2. 阅读 [产品范围](docs/product.md) 和 [贡献指南](CONTRIBUTING.md)；
3. 按[快速开始](#快速开始)运行平台，确认首页、工作台与 API 文档可以访问；
4. 在 GitHub Issue 中领取任务，从最新 `main` 创建个人分支，通过 Pull Request 提交。

```powershell
git clone https://github.com/KayZhongyi/heyu-ai.git
cd heyu-ai
.\scripts\setup-windows.ps1
.\scripts\start-windows.ps1
```

**协作约定：** 不直接向 `main` 推送；不提交密钥、数据库或真实业务资料；不确定产品规则或任务边界时，先在 Issue / PR 中确认。

## 当前能力

| 模块 | 已实现 |
| --- | --- |
| 组织与权限 | 多租户组织、六种角色、邀请记录与主动撤销、持久化登录/邀请滥用防护、角色变更即时生效、旧令牌撤销 |
| 品牌资产 | 品牌与农产品档案、编辑、提交审核、通过或退回 |
| 可信知识库 | TXT / Markdown / CSV 导入、来源指纹、修订链、人工审核 |
| AI 内容创作 | 短视频、手机拍摄清单、直播、评论回复、社交文案、标题与封面文案；已提供零成本生成器与 OpenAI-compatible 真实模型适配器 |
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

## 快速开始

以下是 Windows 本地开发流程；普通演示仅需 Python 3.12，建议至少预留 2 GB 磁盘空间。

```powershell
git clone https://github.com/KayZhongyi/heyu-ai.git
cd heyu-ai

.\scripts\setup-windows.ps1
.\scripts\start-windows.ps1
```

不使用命令行时，也可以首次双击 `安装禾语AI.bat`，之后双击 `启动禾语AI.bat`。虚拟环境、SQLite 数据库及运行文件默认保存在项目目录中；需要指定 Python 时，可设置环境变量 `HEYU_PYTHON`。

可选 Docker / PostgreSQL：

```bash
cp .env.example .env
docker compose up --build
```

为了让任何成员下载后都能零成本体验完整流程，平台默认使用
`DeterministicProvider`。需要查看真实大模型的内容效果时，可以直接切换到已经实现的
OpenAI-compatible 模型适配器。

平台已经实现 OpenAI-compatible 模型适配器，但不会默认调用付费服务。需要评估真实模型内容效果时，
可将 `.env.example` 复制为 `.env`，并配置 `AI_PROVIDER=openai-compatible`、
`AI_BASE_URL`、`AI_MODEL` 与 `AI_API_KEY` 后重新启动。Windows 便携版可复制包内的
`portable-model-settings.example.env` 并重命名为 `.env`。当前尚未提供模型设置图形界面，
也没有把任何真实 API Key 写入仓库或便携包。

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
  release-evidence.md          精确提交自动化发布证据
  acceptance-test.md           人工验收流程
scripts/
  setup_demo_accounts.py       安全创建两至三个展示账号
  seed_demo_workspace.py       初始化合成演示资料与内容
  initialize-render-demo.ps1   交互式完成 Render Demo 初始化
  release-evidence.py          生成精确提交发布证据
  audit-repository.py          仓库发布审计
  test-browser-e2e.js          浏览器端到端测试
  test-i18n.js                 三语完整性测试
  test-content-renderer.js     内容渲染测试
```

## 参与开发

开始编码前，请先在 GitHub Issue 或团队沟通渠道中确认任务的**负责人、范围与验收条件**，避免多人重复修改同一模块。
功能型 PR 如果改变了平台能力，需要同时更新本 README 的“当前能力”或“下一步建设方向”，
让项目说明始终与实际代码保持一致。

| 方向 | 适合参与的工作 |
| --- | --- |
| 产品与内容 | 真实业务流程、验收用例、简中 / 香港繁中 / 英文营销文案 |
| Web | 工作台交互、响应式布局、可访问性、Playwright E2E |
| API / AI | FastAPI、数据模型、RBAC、知识检索、生成链路、模型 Provider |
| 工程质量 | Pytest、CI、Docker / PostgreSQL、文档与仓库审计 |

推荐使用短生命周期分支，一次 PR 只解决一个明确问题：

```powershell
git switch main
git pull --ff-only
git switch -c feat/short-description

python -m ruff check apps scripts
python -m pytest -q
node scripts/test-i18n.js
node scripts/test-content-renderer.js
```

完整的分支、测试、完成定义与数据安全要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。涉及浏览器行为时再运行：

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
- 未经负责人确认，不调用付费服务、不公开私密业务资料、不部署生产环境。
- 当前范围不包含 VR、医疗功能、数字人直播、联邦学习、区块链或无数据支撑的“爆款预测”。

## 下一步建设方向

| 建设方向 | 已有基础 | 下一步实施方式 |
| --- | --- | --- |
| PDF / PPTX 资料导入 | 已有知识库、来源文件名、内容指纹、修订链、审核流程和生成引用 | 增加受限文件上传，使用 MIT 许可的 MarkItDown 按文件流解析 PDF / PPTX；展示抽取预览、页码或幻灯片来源和解析警告，用户确认后再进入知识库。扫描件后续单独增加可选 OCR，不默认上传外部服务 |
| 营销方案 PPTX 生成 | 已有品牌、产品、活动、脚本、渠道文案、审核版本等结构化数据 | 先定义稳定的演示文稿数据结构和“禾语 AI”母版，使用 MIT 许可的 PowerPoint 生成库输出可编辑 `.pptx`；支持封面、产品卖点、受众、内容矩阵、脚本、排期和审核信息，并增加溢出检测、下载接口和文件级测试 |
| 真实模型内容评测 | 已实现 OpenAI-compatible Provider、输出结构校验、引用校验和失败留痕 | 由负责人选择并授权模型服务，安全配置 API Key；准备脱敏农产品样本，对不同模型的事实准确性、营销表达、三语质量和成本进行对比，再确定默认模型 |
| 语义知识检索 | 已有审核资料、来源指纹、修订链和 `lexical-v1` 词法检索 | 为已审核资料生成向量表示，接入可本地或服务端运行的向量存储；建立召回率、引用正确率和无依据回答测试，逐步形成完整 RAG |
| 助农营销工作流库 | 已有短视频、直播、评论回复、社交文案、标题与封面等结构化生成器 | 把不同渠道和业务场景拆成可版本化的工作流配置，明确输入字段、证据要求、输出结构和验收规则；参考成熟开源项目的设计方法，但只复用许可证允许的代码，并以农产品真实样本持续评测 |
| 自动视频理解 | 已有人工视频诊断、结构化证据、改进 Brief 和后续草稿 | 增加视频上传与存储、语音转写、镜头与字幕切分，再接入多模态模型分析；所有诊断结论继续保留证据和人工复核 |
| 内容发布协作 | 已有审核通过内容、发布登记和版本记录 | 先增加适合抖音、小红书、视频号等渠道的复制与导出格式；获得平台授权后，再按渠道 API 增加定时发布、失败重试和发布回执 |
| 运营数据回流 | 已有人工表现数据快照、诊断和迭代链路 | 支持 CSV / Excel 批量导入并统一播放、互动、转化等指标口径；在获得第三方平台授权后增加自动同步和趋势看板 |
| 模型设置体验 | 已支持 `.env` 和便携包配置文件切换 Provider | 在工作台增加仅管理员可用的模型设置与连通性测试；API Key 使用服务端加密存储，不返回前端、不写入日志 |
| 公网商业部署 | 已有 Docker、PostgreSQL、迁移、CI、仓库审计和本地便携包 | 完成 HTTPS、密钥托管、备份恢复、监控告警和人工安全验收后，再部署团队共享或正式生产环境 |

详细发布条件见 [docs/release-gates.md](docs/release-gates.md)。

## License

[Apache License 2.0](LICENSE)
