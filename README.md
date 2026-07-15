# 禾语 AI · Heyu AI

> 面向农户、合作社与乡村运营团队的一站式 AI 新媒体内容生产与经营平台

从一句农家话出发，禾语 AI 帮助经营者完成产品卖点整理、平台策略、短视频脚本、手机分镜、直播话术和七天运营安排。知识库、版本、审核与团队权限在后台沉淀长期品牌资产。

[![CI](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![License](https://img.shields.io/badge/License-Apache--2.0-5B7083)
![Status](https://img.shields.io/badge/Status-Demo--ready%20Engineering%20MVP-EA6A5A)

> 🌱 **欢迎大家加入禾语 AI，一起建设，一起把它做得更好。**

![禾语 AI 平台首页预览](docs/assets/platform-preview.png)

## 禾语 AI 解决什么问题

许多农户有真实、优质的产品，却缺少持续做新媒体内容的时间、经验和团队。禾语 AI 不要求用户先学会复杂的 Prompt，也不把内容审核当作产品的第一入口，而是从经营任务出发：

```text
选择身份与目标
→ 录入农产品资料
→ 选择发布平台
→ 整理产品画像与卖点
→ 生成平台差异化策略
→ 生成三套短视频与手机分镜
→ 生成直播话术
→ 形成七天运营计划
```

平台采用双模式：

- **农户简单模式 `/create/`**：用一张表单完成本次内容经营方案，默认零成本运行。
- **团队专业模式 `/workspace/`**：维护品牌、产品、知识库、内容版本、审核、发布登记、运营记录和成员权限。

## 现在可以体验什么

### 农户简单模式

当前可以选择：

- 农户、合作社或乡村运营团队；
- 直接销售、建立品牌、积累关注、引流到村等经营目标；
- 抖音、小红书、视频号或快手；
- 朴实自然、温暖故事、活泼表达或克制高级的内容风格；
- 简体中文、香港繁体中文或英文。

一次生成会得到：

1. 产品画像与核心受众；
2. 对应平台的内容重点、时长建议和转化动作；
3. 三条不同叙事角度的短视频；
4. 每条视频的开头、正文、封面文案、背景乐方向、分镜和手机拍摄提示；
5. 一套直播讲解结构；
6. 七天发布与运营计划；
7. 下一步行动清单。

公共页面调用稳定的 `DeterministicMarketingProvider`，不会消耗模型额度，也不要求 API Key。它用于演示完整流程和稳定输出，不等同于真实大语言模型。

### 团队专业模式

当前已经实现：

| 模块 | 已实现能力 |
| --- | --- |
| 组织与权限 | 多租户组织、Owner / Admin / Product Manager / Creator / Reviewer / Viewer、邀请、撤销与角色权限 |
| 品牌与产品 | 品牌、农产品档案、编辑、提交、审核以及修改后的重新审核 |
| 知识库 | TXT / Markdown / CSV / PDF / PPTX 导入，PDF/PPTX 本地文字提取，品牌与产品关联，SHA-256 指纹，线性修订与审核 |
| 知识检索 | `lexical-v1` 关键词与字符片段排序、范围过滤、上下文长度限制、来源清单与截断记录 |
| 内容生产 | 短视频、手机拍摄清单、直播话术、评论回复、社交文案、标题与封面文案 |
| 模型适配 | 零成本 Mock 与 OpenAI-compatible 适配层；真实模型失败时可配置自动降级，重复请求支持有界 TTL 缓存 |
| 内容治理 | 不覆盖的内容版本、人工修改、提交审核、来源记录和生成失败留痕 |
| 运营闭环 | 发布登记、表现数据快照、人工视频诊断、改进 Brief 和后续草稿 |
| 材料导出 | 生成可继续编辑的 16:9 PPTX 营销材料 |
| 国际化 | 简体中文、香港繁体中文和英文界面切换，不改写用户录入的业务资料 |
| 工程运行 | Windows 本地运行、SQLite、可选 Docker/PostgreSQL、自动化测试与 GitHub Actions |

知识库不是独立的“审核产品”，而是 AI 内容生产的底层产品记忆。农户以后可以复用产地、品种、种植方式、规格、品牌故事和历史内容，不必每次从头填写。

## 快速本地体验

### Windows：最简单方式

源码或 ZIP 方式需要先安装 **Python 3.12**。第一次安装会通过 `pip` 下载依赖，通常需要联网；安装完成后的日常启动不需要 Docker、Ollama、Node.js、域名或付费 API。

1. 点击 GitHub 页面右上方绿色 **Code** 按钮；
2. 点击 **Download ZIP**；
3. 解压到空间充足的目录，推荐 D 盘；
4. 第一次双击 `安装禾语AI.bat`；
5. 安装完成后双击 `启动禾语AI.bat`；
6. 浏览器打开后，从首页进入“开始一次内容经营”。

如果电脑上没有 Python 3.12，安装脚本会给出明确提示。项目建议放在 D 盘等空间充足的位置，虚拟环境和本地数据库都会保存在项目目录内。

也可以使用 PowerShell：

```powershell
git clone https://github.com/KayZhongyi/heyu-ai.git
cd heyu-ai
.\scripts\setup-windows.ps1
.\scripts\start-windows.ps1
```

启动后访问：

- 首页：`http://127.0.0.1:8000/`
- 农户简单模式：`http://127.0.0.1:8000/create/`
- 团队专业模式：`http://127.0.0.1:8000/workspace/`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

GitHub 仓库公开只代表任何人都可以查看和下载代码，**不等于已经拥有一个在线网址**。不想安装时，仍需把仓库部署到 Render 等托管平台；参见 [Render Demo 指南](docs/render-demo.md)。

## 演示数据重置

需要重新录制或从空白状态演示时：

1. 关闭正在运行的禾语 AI；
2. 双击 `重置禾语AI演示.bat`；
3. 输入 `RESET`；
4. 再次启动平台。

重置脚本默认先把当前 SQLite 数据库备份到 `data/backups/`，再创建干净环境。确认不需要备份时，开发者可以执行：

```powershell
.\scripts\reset-local-demo.ps1 -SkipBackup -Force
```

## 接入国产模型

禾语 AI 不绑定单一厂商。只要服务实现兼容的 `POST /v1/chat/completions` 接口，就可以通过同一适配层连接。可评估通义千问、DeepSeek 或其他 OpenAI-compatible 服务，但仓库不声称已经验证每一家厂商的所有模型版本。

复制 `.env.example` 为 `.env`：

```dotenv
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-model-name
AI_API_KEY=replace-with-your-own-key
AI_TIMEOUT_SECONDS=45

MARKETING_CACHE_TTL_SECONDS=900
MARKETING_CACHE_MAX_ENTRIES=256
MARKETING_FALLBACK_TO_MOCK=true
```

说明：

- ChatGPT/Codex 订阅不是模型 API Key；
- API Key 只保存在本地或部署环境变量中，不要提交到 Git；
- 公共 `/create/` 预览始终使用零成本 Mock，避免公开页面无限消耗额度；
- 需要真实模型的生成接口要求登录；
- 相同输入可以在 TTL 内复用缓存；
- 模型超时、网络失败或结构校验失败时，可按配置切换到 Mock 降级结果，并显式标记 `degraded`，不会伪装成真实模型输出。

## 知识库技术

当前知识库由 FastAPI、SQLAlchemy 和 SQLite/PostgreSQL 构成：

```text
资料导入
→ PDF/PPTX 本地文字提取
→ 用户确认与结构化保存
→ 品牌/产品关联
→ SHA-256 内容指纹
→ 线性修订与审核
→ lexical-v1 有界检索
→ 作为生成上下文并保存来源记录
```

下一步会在现有来源、版本和权限结构上增加文本切分、Embedding、向量存储、关键词与向量混合召回、重排序及引用正确率测试，逐步形成面向营销内容生产的混合 RAG。当前 `lexical-v1` 是词法检索，不应写成已经完成的语义 RAG。

## 三类演示案例

农户简单模式提供三个可一键生成的完整案例，自动化测试同时覆盖桌面端与移动端：

- 当季番茄：突出成熟度、采摘现场和家庭食用场景；
- 高山茶叶：突出产区、工艺、香气和冲泡场景；
- 当季水果：突出成熟窗口、口感、采收和家庭分享场景。

在 `/create/` 点击任一案例，平台会按当前语言自动填入身份、目标、产品、卖点、平台、语气和热点信息，并直接生成策略、三条短视频、直播话术及七天计划。手动修改表单后，案例高亮会自动取消，避免把用户输入误认为模板内容。

## 能力状态

为了让成员知道下一步怎么参与，能力按三种状态说明：

### 已自动完成

- 农户经营任务结构化；
- 平台差异化策略；
- 三条短视频、分镜、拍摄建议和背景乐方向；
- 直播话术结构；
- 七天运营计划；
- 零成本 Mock 演示；
- 文档文字提取、版本、权限、审核和来源记录；
- PPTX 营销材料导出。

### 需要负责人配置

- 选择并授权真实国产模型服务；
- 配置 API Key、模型名称和服务地址；
- 正式部署时配置 PostgreSQL、HTTPS、密钥、备份和监控；
- 获得抖音、小红书、视频号等第三方平台的合法接口授权。

### 接下来建设

| 方向 | 已有基础 | 实施方式 |
| --- | --- | --- |
| 知识库混合 RAG | 来源、修订链、权限、`lexical-v1` | 增加切分、Embedding、向量存储、混合召回、重排序和引用评测 |
| 热点辅助 | 用户可以手动填写热点 | 接入合规数据源，记录抓取时间和来源；先匹配产品、目标和平台，再生成脚本，不虚构“实时热度” |
| 模型质量评测 | Provider、结构校验、Mock 降级 | 建立脱敏农产品题集，对事实准确性、营销表达、三语质量、延迟和成本评分 |
| 运营数据回流 | 人工数据快照、诊断和后续草稿 | 支持 CSV/Excel 导入，再在获得授权后连接平台 API |
| 自动视频理解 | 人工诊断结构和改进 Brief | 增加视频上传、语音转写、镜头/字幕切分和多模态分析 |
| 发布协作 | 内容版本和发布登记 | 先提供各平台复制/导出格式，获得授权后增加定时发布、失败重试和回执 |
| 模型设置界面 | `.env` Provider 配置 | 增加管理员连接测试；密钥仅服务端保存，不返回浏览器 |
| 正式商业运行 | PostgreSQL、迁移、审计、CI | 完成隐私政策、数据保留、监控告警、恢复演练和安全验收 |

当前发布登记不是自动发布，运营数据主要由人工录入，视频诊断目前也是人工流程。这些能力已经有可持续扩展的数据结构，但不应被描述成已经连接第三方平台。

## 仓库结构

```text
apps/
  api/                         FastAPI、SQLAlchemy、迁移与业务服务
  web/                         首页、农户简单模式与团队专业模式
docs/
  architecture.md              系统架构与工程边界
  product.md                   产品范围与业务规则
  platform-v2-plan.md          农户内容经营平台建设规划
  operations.md                启动、备份、恢复与运维
  release-gates.md             Demo、工程 MVP 与生产发布门槛
scripts/
  reset-local-demo.ps1         安全重置本地演示数据
  seed_demo_workspace.py       初始化合成团队演示资料
  setup_demo_accounts.py       创建演示账号
  test-browser-e2e.js          Playwright 浏览器端到端测试
  audit-repository.py          仓库发布审计
```

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m ruff check apps scripts
.\.venv\Scripts\python.exe -m pytest -q
node scripts/test-i18n.js
node scripts/test-content-renderer.js
node scripts/test-browser-e2e.js
.\.venv\Scripts\python.exe scripts/audit-repository.py
```

当前浏览器 E2E 会验证三语首页、三类一键案例、三条视频、直播话术、七天计划、语言切换数据保持以及 390px 移动端布局。Windows 便携构建还会通过 `acceptance-smoke.py` 验证首页、简单模式、营销预览、知识生命周期、内容生成和运营闭环。

涉及数据库结构时还需验证 Alembic 升降级；涉及在线部署时还需验证 PostgreSQL、备份恢复、生产配置和真实浏览器流程。详细门槛见 [发布门槛](docs/release-gates.md)。

## 参与建设

新功能开始前，请在 Issue 或团队沟通中明确负责人、修改范围和验收条件，避免多人同时改动同一模块。功能变化应同步更新 README 的“当前能力”或“接下来建设”。

基本约定：

- 不直接向 `main` 推送，使用短生命周期分支和 Pull Request；
- 不提交 `.env`、API Key、数据库、原始私密 PDF/PPT 或真实客户资料；
- 不虚构爆款率、销量提升、实时热度或平台授权；
- VR、医疗功能、数字人直播和区块链不属于当前 MVP 主线；
- 设计和实现优先回答两个问题：农户能不能用，使用之后的内容是否更好。

完整协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[Apache License 2.0](LICENSE)
