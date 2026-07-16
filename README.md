# 禾语 AI · Heyu AI

> 从一份农产品资料出发，生成能拍、能发、能持续运营的新媒体内容方案。

禾语 AI 是面向农户、合作社与乡村运营团队的开源 AI 内容生产与经营平台。用户只需填写产品、产地、经营目标和发布平台，系统便会完成产品画像、选题适配、创意路线、短视频脚本、手机分镜、直播话术与七天运营计划。

它不是只返回一段文案的通用聊天工具，而是一条从“农产品资料”通向“可执行内容”的完整工作流。平台可在没有 API Key、Docker 或本地大模型的情况下运行，也可以连接 OpenAI-compatible 模型；生成结果还能进入团队工作台，沉淀为可复用的品牌与内容资产。

[![CI](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![License](https://img.shields.io/badge/License-Apache--2.0-5B7083)
![Status](https://img.shields.io/badge/Status-Demo--ready%20Engineering%20MVP-EA6A5A)
![No Docker Required](https://img.shields.io/badge/Docker-Not%20required-5B7083)
![No API Key Required](https://img.shields.io/badge/API%20Key-Optional-22A06B)

**[5 分钟启动](#5-分钟本地启动)** · **[功能一览](#核心能力)** · **[技术架构](#技术结构)** · **[建设路线](#当前能力与建设路线)** · **[参与贡献](#参与建设)**

> 🌱 欢迎加入禾语 AI，一起把乡村内容经营做得更简单、更专业。

![禾语 AI 平台首页预览](docs/assets/platform-preview.png)

## 核心能力

| 能力 | 禾语 AI 如何实现 |
| --- | --- |
| **经营任务结构化** | 从身份、目标、产品、受众和发布平台出发，把模糊需求拆成可执行的内容任务 |
| **三条创意路线** | 同一产品同时生成实用钩子、人物故事、轻松反差三种方向，避免只给一个答案 |
| **产品特定分镜** | 根据产品信息生成真实可拍动作；茶叶对应投茶、注水和出汤，百香果对应切果、果肉与气泡饮 |
| **热点适配而非硬蹭** | 从产品、受众、目标、平台、时效和可拍性六个维度判断热点是否值得使用 |
| **品牌知识记忆** | 保存产地、品种、种植方式、规格、品牌故事和历史资料，为后续内容持续提供上下文 |
| **内容经营闭环** | 从脚本和手机分镜继续延伸到直播话术、七天运营计划、版本复用和效果回流 |

## 从资料到内容经营

```text
身份与经营目标
        ↓
产品资料与知识库
        ↓
热点、节气与常青选题适配
        ↓
三条差异化创意路线
        ↓
标题 + 前三秒钩子 + 口播 + 手机分镜 + BGM
        ↓
直播话术 + 七天运营计划
        ↓
保存、编辑、复用与效果回流
```

当前 Demo 已针对番茄、茶叶、百香果、水果和谷物等品类生成不同的镜头语言，而不是统一套用“展示产品”的空泛模板。

想快速体验完整流程，可以查看 [演示指引](docs/demo-showcase.md)，或启动后直接进入 `/create/` 选择一键案例。

## 为什么做禾语 AI

农产品进入新媒体市场，需要连续完成选题、脚本、拍摄、直播和后续运营。现有通用 AI 工具通常只返回一段文案，用户还要自己判断该拍什么、在哪个平台发布，以及下一步怎么继续。

禾语 AI 把这些步骤串成同一条工作流。用户不需要先学习 Prompt，只需要说明这次想卖什么、讲给谁听、准备发到哪里。平台负责把经营任务拆成可以直接执行的内容方案。

平台采用双模式：

- **农户简单模式 `/create/`**：用一张表单完成本次内容经营方案，默认零成本运行。
- **团队专业模式 `/workspace/`**：集中保存经营方案，维护品牌、产品、知识库、内容版本、审核、发布登记、运营记录和成员权限。

## 已经可以使用的功能

### 农户简单模式

当前可以选择：

- 农户、合作社或乡村运营团队；
- 直接销售、建立品牌、积累关注、引流到村等经营目标；
- 抖音、小红书、视频号或快手；
- 朴实自然、温暖故事、活泼表达或克制高级的内容风格；
- 简体中文、香港繁体中文或英文。

农户简单模式一次生成会得到：

1. 产品画像与核心受众；
2. 对应平台的内容重点、时长建议和转化动作；
3. 手工热点、节气农事与常青痛点三类选题信号，以及产品、受众、平台、时效、可拍性和来源适配判断；
4. 实用钩子、人物故事、轻松反差三条可选择的创意路线；
5. 每条视频的标题、封面文案、前三秒钩子、完整口播、背景乐方向、产品特定分镜、手机拍摄提示、规则质量分和改进建议；
6. 一套直播讲解结构；
7. 七天发布与运营计划；
8. 从选路线、准备拍摄到保存经营方案的连续下一步引导。

公共页面默认使用 `DeterministicMarketingProvider`，不消耗模型额度，也不要求 API Key，因此任何贡献者都能稳定复现完整流程。需要更开放的语言生成时，可以切换到 OpenAI-compatible Provider。

热点辅助当前用于**选题规划与适配判断**：系统记录信号类型，并优先判断热点与产品、受众和拍摄条件是否匹配，而不是机械追逐热词。

生成完成后，可以把整套方案保存到团队工作台。已经登录的成员可直接保存；尚未登录时，方案会在当前浏览器会话中临时保留，登录后再导入，不需要重新生成。

### 团队专业模式

当前已经实现：

| 模块 | 已实现能力 |
| --- | --- |
| 组织与权限 | 多租户组织、Owner / Admin / Product Manager / Creator / Reviewer / Viewer、邀请、撤销与角色权限 |
| 经营方案库 | 保存简单模式的完整经营方案，再次打开、可读预览、结构化编辑、复制复用和不覆盖旧内容的版本记录 |
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

## 5 分钟本地启动

### Windows 最简单方式

源码或 ZIP 方式需要先安装 **Python 3.12**。第一次安装会通过 `pip` 下载依赖，通常需要联网；安装完成后的日常启动不需要 Docker、Ollama、Node.js、域名或付费 API。

1. 点击 GitHub 页面右上方绿色 **Code** 按钮；
2. 点击 **Download ZIP**；
3. 解压到空间充足的目录，推荐 D 盘；
4. 第一次双击 `安装禾语AI.bat`；
5. 安装完成后双击 `启动禾语AI.bat`；
6. 浏览器打开后，从首页进入“开始一次内容经营”。

如果电脑上没有 Python 3.12，安装脚本会给出明确提示。项目建议放在 D 盘等空间充足的位置，虚拟环境和本地数据库都会保存在项目目录内。
平台会在后台运行；使用结束后双击 `停止禾语AI.bat` 即可安全停止本项目启动的服务。

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

1. 双击 `重置禾语AI演示.bat`，脚本会先停止由本项目启动的本地服务；
2. 输入 `RESET`；
3. 再次启动平台。

重置脚本只处理 Windows 源码启动器使用的 `data/heyu.db`，默认先备份到 `data/backups/`，再创建干净环境；它不会重置自定义 `DATABASE_URL`、便携版目录或 PostgreSQL。确认不需要备份时，开发者可以执行：

```powershell
.\scripts\reset-local-demo.ps1 -SkipBackup -Force
```

## 连接国产模型

禾语 AI 不绑定单一厂商。当前完成的是 OpenAI-compatible 协议适配和模拟响应测试：服务需要支持 Bearer Token、`POST /v1/chat/completions`、`response_format=json_object`，并能在 `choices[0].message.content` 中返回符合营销方案 Schema 的 JSON。可评估通义千问、DeepSeek 或其他兼容服务，但仓库尚未完成具体国产模型厂商和模型版本的端到端认证。

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

## 技术结构

平台把经营任务、AI 生成和团队资产分开建模。前端只负责收集农产品资料和展示可执行结果；FastAPI 服务负责编排选题、脚本、知识检索和运营流程；Provider 层负责在零成本 Demo 与真实模型之间切换。模型返回内容必须经过 Pydantic Schema 校验，才能进入页面、版本库和后续工作流。

```mermaid
flowchart LR
    A["农户简单模式<br/>身份、目标、产品、平台"] --> B["内容经营编排<br/>选题适配与三条创意路线"]
    K["产品知识库<br/>来源、修订、lexical-v1"] --> B
    B --> C["生成层<br/>Deterministic / OpenAI-compatible"]
    C --> D["结构校验与质量评估<br/>Pydantic Schema + 规则评分"]
    D --> E["可执行内容包<br/>脚本、分镜、直播、七天计划"]
    E --> F["团队工作台<br/>版本、审核、发布登记、数据回流"]
```

主要工程组件：

- Python 3.12、FastAPI、Pydantic；
- SQLAlchemy 2.x、Alembic、SQLite/PostgreSQL；
- 可插拔 AI Provider、JSON 结构化生成、超时与降级；
- Pytest、Playwright、MyPy、Ruff 和 GitHub Actions；
- 原生 HTML、CSS、JavaScript 响应式界面，不要求 Docker 或前端构建工具才能体验。

## 三类演示案例

农户简单模式提供三个可一键生成的完整案例，自动化测试同时覆盖桌面端与移动端：

- 当季番茄：突出成熟度、采摘现场和家庭食用场景；
- 高山茶叶：突出产区、工艺、香气和冲泡场景；
- 当季水果：突出成熟窗口、口感、采收和家庭分享场景。

在 `/create/` 点击任一案例，平台会按当前语言自动填入身份、目标、产品、卖点、平台、语气和热点信息，并直接生成策略、三条短视频、直播话术及七天计划。手动修改表单后，案例高亮会自动取消，避免把用户输入误认为模板内容。

## 当前能力与建设路线

### 已自动完成

- 农户经营任务结构化；
- 平台差异化策略；
- 热点、节气与常青选题信号的来源标识、六维适配判断和“不建议追”的降级建议；
- 实用钩子、人物故事、轻松反差三条创意路线；
- 三条短视频、分镜、拍摄建议、背景乐方向、规则质量评估和改进建议；
- 直播话术结构；
- 七天运营计划；
- 从选题、选路线、准备拍摄到保存方案的连续下一步引导；
- 完整经营方案保存、再次打开、编辑、复制与版本追踪；
- 零成本 Mock 演示；
- 文档文字提取、版本、权限、审核和来源记录；
- PPTX 营销材料导出。

### 需要部署者配置

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

当前浏览器 E2E 会验证三语首页、三类一键案例、完整经营方案生成与保存、再次打开、编辑新版本、旧版本保留、复制复用、只读角色权限、语言切换数据保持以及 390px 移动端布局。Windows 便携构建还会通过 `acceptance-smoke.py` 验证首页、简单模式、营销预览、知识生命周期、内容生成和运营闭环。

涉及数据库结构时还需验证 Alembic 升降级；涉及在线部署时还需验证 PostgreSQL、备份恢复、生产配置和真实浏览器流程。详细门槛见 [发布门槛](docs/release-gates.md)。

## 参与建设

欢迎提交 Issue、设计讨论和 Pull Request。开始修改前，请先写清范围和验收条件，避免多人同时改动同一模块。功能变化应同步更新 README 的“当前能力”或“接下来建设”。

基本约定：

- 不直接向 `main` 推送，使用短生命周期分支和 Pull Request；
- 不提交 `.env`、API Key、数据库、原始私密 PDF/PPT 或真实客户资料；
- 不虚构爆款率、销量提升、实时热度或平台授权；
- VR、医疗功能、数字人直播和区块链不属于当前 MVP 主线；
- 设计和实现优先回答两个问题：农户能不能用，使用之后的内容是否更好。

完整协作规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[Apache License 2.0](LICENSE)
