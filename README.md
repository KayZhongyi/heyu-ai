<p align="center">
  <img src="docs/assets/readme/heyu-readme-hero.svg" width="100%" alt="禾语 AI：让产地的真实，成为内容的底气">
</p>

<div align="center">

**面向农户、合作社与乡村内容团队的开源农产品内容生产与经营平台**

让真实产地经验进入内容生产，让每一次发布都为下一次创作留下依据。

<p>
  <a href="https://github.com/KayZhongyi/heyu-ai/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/KayZhongyi/heyu-ai/ci.yml?branch=main&style=flat-square&label=CI&color=3D715C" alt="CI"></a>
  <img src="https://img.shields.io/badge/status-commercial%20MVP-173C2F?style=flat-square" alt="Commercial MVP">
  <img src="https://img.shields.io/badge/run-local--first-5A806A?style=flat-square" alt="Local first">
  <img src="https://img.shields.io/badge/i18n-简中%20·%20繁中%20·%20EN-927C43?style=flat-square" alt="Simplified Chinese, Traditional Chinese and English">
  <img src="https://img.shields.io/badge/model-pluggable-5A806A?style=flat-square" alt="Model pluggable">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-173C2F?style=flat-square" alt="Apache License 2.0"></a>
</p>

[看懂产品](#overview) · [查看界面](#product) · [本地启动](#quick-start) · [技术架构](#architecture) · [参与建设](#contributing)

</div>

<!-- 最终比赛演示视频或 GIF 将放在这里。 -->

<a id="overview"></a>

## 30 秒看懂禾语 AI

禾语 AI 从产品与经营背景出发，生成相互匹配的选题、口播、分镜和发布建议。内容发布后，方案、版本与运营结果会继续留在系统中，成为下一轮生产的依据。

<table>
  <tr>
    <td width="25%" valign="top">
      <strong>01 · 认识产品</strong><br><br>
      <sub>录入品种、产地、受众、经营目标和发布平台。</sub>
    </td>
    <td width="25%" valign="top">
      <strong>02 · 找到依据</strong><br><br>
      <sub>调用已授权资料、历史方案，也可加入用户提供的热点线索。</sub>
    </td>
    <td width="25%" valign="top">
      <strong>03 · 直接开拍</strong><br><br>
      <sub>获得创意路线、标题、口播、手机分镜和拍摄清单。</sub>
    </td>
    <td width="25%" valign="top">
      <strong>04 · 继续经营</strong><br><br>
      <sub>保存版本、登记发布结果，让反馈进入下一轮内容。</sub>
    </td>
  </tr>
</table>

> **一句话定位：** 禾语 AI 把散落在访谈、产品资料和过往内容里的经验，整理成可以直接执行、持续复用的农产品内容方案。

### 产品能力全景

禾语 AI 为每一款农产品建立持续积累的内容档案。平台先梳理产品事实、目标受众和经营目标，再完成拍摄与发布方案。方案版本、发布记录和运营结果会回到同一条业务链路中，为后续内容提供依据。

| 能力 | 用户价值 | 平台支撑 |
| --- | --- | --- |
| 基层知识记忆 | 把农户访谈、调研案例、产品资料和地方产业经验沉淀为内容依据 | 文档导入、文本分块、混合检索、来源关联与分级权限 |
| 产品与经营记忆 | 持续保存品牌、产品、历史方案、内容版本、发布记录和运营反馈 | 产品档案、方案库、版本链、发布任务与运营记录 |
| 高热内容适配 | 输入高热视频标题、来源链接或内容线索，判断是否适合当前产品和拍摄条件 | 来源关联、时效信息、适配判断、叙事结构提取与选题重组 |
| 营销定位与内容策略 | 根据产品事实、经营目标和目标受众确定平台重点、选题方向与承接动作 | 结构化经营简报、平台策略、三条创意路线与选题适配 |
| 完整内容生产 | 围绕同一目标获得标题、封面、前三秒开头、完整口播、手机分镜和七天安排 | 三条路线及相互匹配的完整拍摄内容包 |
| 发布后的持续运营 | 登记发布与表现数据，把评论、私信和内容效果转化为后续经营依据 | 发布任务、方案版本、运营数据回流与下一轮优化参考 |
| 多语种与出海适配 | 在保留产品事实和产地表达的前提下，调整不同语言受众所需的标题、节奏与行动建议 | 简体中文、香港繁体中文和英文界面与核心内容链路 |
| 本地运行与模型替换 | 使用 Mock 零成本体验，也可以接入国产云模型、本地推理服务或其他 OpenAI-compatible 服务 | SQLite、本地启动、模型适配、缓存与显式降级 |
| 团队协作与交付 | 团队共同维护资料、内容和版本，并导出可编辑、可交付的成果文件 | 组织权限、版本管理、Word、PDF、PPTX 与素材包导出 |

### 用户最终会拿到什么

| 产出 | 内容 |
| --- | --- |
| 内容决策 | 产品定位、核心受众、平台策略、热点适配结论与本轮内容目标 |
| 创意选择 | 三条互不重复的创意路线，以及每条路线的适用原因和改进建议 |
| 拍摄执行包 | 标题、封面文案、完整口播、逐秒手机分镜、BGM 方向、拍摄清单和结尾动作 |
| 发布运营包 | 七天发布安排、评论与私信承接建议、内容复用方式和下一轮选题 |
| 长期经营档案 | 历史方案、人工修改版本、发布记录、运营数据和后续优化依据 |
| 对外交付文件 | 三语内容，以及 Word、PDF、PPTX 和平台素材 ZIP 等可下载文件 |

### 为什么它更适合农产品内容生产

|  | 常见通用 AI 使用方式 | 禾语 AI |
| --- | --- | --- |
| 内容依据 | 每次临时描述产品，结果依赖当前 Prompt | 关联产品档案、已授权基层资料、历史方案与经营记录 |
| 热点使用 | 用户自行判断是否适合，再要求模型仿写 | 先判断产品、受众、平台、时效和拍摄条件，再重组为自己的选题 |
| 交付结果 | 得到一段文案或单个脚本 | 同时得到三条创意路线、完整口播、手机分镜、拍摄准备和发布建议 |
| 后续经营 | 对话结束后，发布结果需要另行保存 | 方案、版本、发布记录和运营反馈在同一工作台持续积累 |

### 四个核心能力

#### 1. 真实基层资料成为内容依据

农户访谈、实地案例、产品资料和地方产业经验经过规范整理后，可以沉淀为项目的知识资产。生成内容时，系统按当前产品和任务调用相关信息，用于补充产品特点、产地故事和经营背景。

知识库承担内容生产的产品记忆层。资料、产品档案和历史方案可以在同一条链路中相互关联，形成更贴近真实经营场景的内容方案。

#### 2. 用户看到的高热内容，可以转化为自己的选题

用户可以输入热点标题、来源链接或高互动内容线索。平台先判断它是否适合当前农产品、目标受众、发布平台和现有拍摄条件，再提取可用的叙事结构与表达方式，重组为符合产品特点的选题。

#### 3. 一次得到相互匹配的完整内容包

产品定位、平台策略、创意方向、口播、分镜和发布建议围绕同一个经营目标生成。用户不必在多个工具之间反复复制、改写和拼接。

#### 4. 让内容记住产品，也记住经营过程

品牌档案、产品资料、知识来源、历史方案、内容版本、发布记录和运营数据可以持续关联。下一次生成从已有经营过程继续，用户不必重新介绍同一个产品。

<a id="product"></a>

## 看一眼产品

![禾语 AI 平台首页](docs/assets/readme/heyu-landing.png)

### 从产品信息到三条创意路线

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/heyu-creative-routes.png" alt="禾语 AI 三条创意路线">
      <br>
      <sub>围绕同一个产品生成不同方向，由用户决定接下来拍什么。</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/heyu-knowledge-memory.png" alt="禾语 AI 基层知识记忆">
      <br>
      <sub>把产品资料和基层案例整理为可检索、可关联的内容记忆。</sub>
    </td>
  </tr>
</table>

### 从一次生成到持续经营

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/heyu-plan-library.png" alt="禾语 AI 经营方案库">
      <br>
      <sub>保存完整方案、内容版本和历史记录，后续可以继续编辑与复用。</sub>
    </td>
    <td width="50%" valign="top">
      <img src="docs/assets/readme/heyu-operations-loop.png" alt="禾语 AI 运营数据回流">
      <br>
      <sub>登记发布与运营结果，让下一次建议建立在已经发生的经营过程上。</sub>
    </td>
  </tr>
</table>

<details>
  <summary><strong>查看英文工作台</strong>（平台同时支持简体中文、香港繁体中文和英文）</summary>
  <br>
  <img src="docs/assets/readme/heyu-english-workspace.png" alt="禾语 AI 英文工作台">
</details>

## 一条完整的内容生产动线

```mermaid
flowchart LR
    A["产品档案"]:::quiet
    B["基层资料<br/>热点线索"]:::quiet
    C["内容记忆层"]:::memory
    D["三条创意路线"]:::work
    E["可执行内容包"]:::focus
    F["发布与反馈"]:::memory

    A --> C
    B --> C
    C --> D --> E --> F
    F -. "进入下一轮" .-> C

    classDef quiet fill:#F3F6F1,stroke:#B9CDBE,color:#355246;
    classDef memory fill:#DDEADF,stroke:#7FA58B,color:#294C3C;
    classDef work fill:#E8F2EC,stroke:#5F8E73,color:#244A39;
    classDef focus fill:#14271E,stroke:#14271E,color:#FFFFFF,stroke-width:2px;
```

| 阶段 | 用户操作 | 系统产出 |
| --- | --- | --- |
| 建立背景 | 选择演示产品，或录入自己的产品、产地、受众与目标 | 产品画像、核心受众、传播目标与平台重点 |
| 补充依据 | 关联知识资料，输入已确认的热点或高热内容线索 | 资料召回结果、热点适配判断与内容切入点 |
| 选择方向 | 对比三条创意路线，选定其中一条继续完善 | 差异化主题、叙事结构、情绪与转化动作 |
| 生成方案 | 确认平台、风格和拍摄条件 | 标题、封面、前三秒钩子、完整口播、手机分镜、BGM方向和准备清单 |
| 发布经营 | 保存方案、登记发布情况并回填效果 | 方案版本、发布记录、评论回复建议和下一轮优化参考 |
| 交付复用 | 在工作台查看、编辑或导出 | Word、PDF、PPTX和平台素材 ZIP |

## 当前 MVP 已经实现

| 能力 | 当前实现 |
| --- | --- |
| 农户内容生产 | 农户简单模式、团队专业工作台；番茄、高山茶叶、当季水果三类演示案例 |
| 策略与脚本 | 结构化产品输入、热点适配、三条创意路线、标题、钩子、口播、分镜和运营建议 |
| 知识记忆 | TXT、Markdown、CSV、DOCX、PDF、PPTX 导入；文本分块、词法召回、可插拔 Embedding 与 RRF 融合 |
| 经营记忆 | 品牌与产品档案、方案保存、结构化编辑、版本记录、发布登记、运营数据回流 |
| 团队协作 | 多租户组织、成员邀请、角色权限、知识修订和团队工作台 |
| 多语界面 | 简体中文、香港繁体中文和英文，覆盖首页、内容生成与核心工作台 |
| AI 与降级 | 确定性 Mock、OpenAI-compatible 模型适配、TTL 缓存和可配置 Mock 降级 |
| 本地与部署 | SQLite 本地运行；Docker、PostgreSQL、Windows 启动器与便携构建 |
| 工程质量 | Ruff、MyPy、Pytest、Playwright、仓库审计、迁移检查和 GitHub Actions |

<a id="quick-start"></a>

## 五分钟本地启动

默认 Mock 模式**不需要 API Key，也不产生模型费用**。它适合本地体验、课堂展示、比赛 Demo 和功能开发。

### Windows：第一次安装

需要 [Python 3.12](https://www.python.org/downloads/) 和 Git。

```powershell
git clone https://github.com/KayZhongyi/heyu-ai.git
cd heyu-ai
.\scripts\setup-windows.ps1
.\scripts\start-windows.ps1
```

不使用命令行也可以：

1. 第一次双击 `安装禾语AI.bat`；
2. 以后双击 `启动禾语AI.bat`；
3. 使用结束后双击 `停止禾语AI.bat`。

需要清空本地演示数据时，先确认现有数据不再需要，再使用 `重置禾语AI演示.bat`。

### 启动后访问

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:8000/` | 产品首页 |
| `http://127.0.0.1:8000/create/` | 农户简单模式 |
| `http://127.0.0.1:8000/workspace/` | 团队专业工作台 |
| `http://127.0.0.1:8000/docs` | API 文档 |
| `http://127.0.0.1:8000/health` | 服务状态 |

本地模式默认把数据保存在项目的 `data/` 目录中。Mock 模式无需调用外部模型；部署方也可以按自己的数据治理要求选择国产云模型、本地推理服务或统一模型网关。

### Docker 与 PostgreSQL

```bash
docker compose up --build
```

启动后访问 `http://127.0.0.1:8000/`。Compose 会同时启动 API 与 PostgreSQL，并保留数据库卷。

完整演示流程见 [Demo Showcase](docs/demo-showcase.md)，部署说明见 [Render Demo](docs/render-demo.md)。

## 接入国产模型或本地模型

默认配置使用确定性 Mock：

```env
AI_PROVIDER=mock
AI_MODEL=deterministic-v1
```

任何提供 OpenAI-compatible `POST /v1/chat/completions` 接口的模型服务，都可以通过环境变量接入：

```env
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-model-name
AI_API_KEY=replace-with-your-own-key
AI_TIMEOUT_SECONDS=45

MARKETING_CACHE_TTL_SECONDS=900
MARKETING_CACHE_MAX_ENTRIES=256
MARKETING_FALLBACK_TO_MOCK=true
```

云端国产模型、本地推理服务和统一模型网关可以共用同一套业务流程。Mock 与真实模型也共用结构化输出协议，切换 Provider 时不需要改写前端页面和核心数据结构。

更多配置见 [开放模型适配说明](docs/open-source-adapters.md) 和 [`.env.example`](.env.example)。

<a id="architecture"></a>

## 技术架构

```mermaid
flowchart LR
    A["Web<br/>三语交互"]:::edge
    B["FastAPI<br/>业务接口"]:::core
    C["知识检索<br/>内容记忆"]:::core
    D["AI Provider<br/>Mock / Compatible"]:::core
    E["结构校验<br/>方案编排"]:::core
    F["SQLite / PostgreSQL<br/>版本与反馈"]:::edge
    G["脚本 · 分镜<br/>运营方案"]:::focus

    A --> B
    B --> C --> D --> E --> G
    B <--> F
    C <--> F
    G --> F

    classDef edge fill:#F3F6F1,stroke:#B9CDBE,color:#355246;
    classDef core fill:#DDEADF,stroke:#6F987C,color:#284B3A;
    classDef focus fill:#14271E,stroke:#14271E,color:#FFFFFF,stroke-width:2px;
```

| 层级 | 技术实现 |
| --- | --- |
| Web | 原生 HTML、CSS 与 JavaScript；首页、农户简单模式、团队工作台和三语字典 |
| API | FastAPI、Pydantic；业务接口、权限控制与结构化生成 |
| 数据 | SQLAlchemy、Alembic；SQLite 与 PostgreSQL |
| 检索 | 文本分块、BM25 风格召回、可插拔 Embedding、余弦相似度与 RRF 融合 |
| Provider | 确定性 Mock 与 OpenAI-compatible 适配器 |
| 可靠性 | 结构校验、TTL 缓存、Embedding 词法回退与模型 Mock 降级 |
| 质量门禁 | Ruff、MyPy、Pytest、Playwright、迁移检查、仓库审计和构建验证 |

更完整的设计说明见 [技术架构文档](docs/architecture.md)。

## 自动化测试

GitHub Actions 与本地测试覆盖：

- API 静态检查、格式检查、类型检查和数据库迁移；
- Pytest 与不低于 80% 的代码覆盖率门禁；
- 简体中文、香港繁体中文和英文浏览器流程；
- 番茄、高山茶叶、当季水果三类内容生成场景；
- Windows 安装、启动、便携构建和验收冒烟；
- Docker 构建与 PostgreSQL 持久化；
- 敏感信息、演示配置和发布证据审计。

```powershell
Push-Location apps/api
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest -q
Pop-Location

node scripts/test-i18n.js
node scripts/test-content-renderer.js
python scripts/audit-repository.py
```

完整浏览器流程：

```powershell
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:e2e
```

## 产品路线

### 当前版本：核心闭环

- [x] 农户简单模式与团队专业工作台；
- [x] 知识检索与基层资料记忆；
- [x] 三条创意路线、完整脚本、手机分镜与拍摄准备；
- [x] 用户提供热点线索后的适配与重组；
- [x] 七天发布安排、方案版本、发布登记和运营数据回流；
- [x] 简体中文、香港繁体中文和英文界面与核心内容；
- [x] 本地运行、国产模型适配、Mock、缓存与显式降级；
- [x] Windows、Docker、PostgreSQL 与自动化质量门禁。

### 下一阶段：经营智能

- 让典型基层调研案例参与选题、脚本和发布方案生成；
- 深化高热内容的结构识别、互动方式提取与产品适配；
- 根据历史内容、评论和运营结果生成更具体的下一轮建议；
- 扩展评论回复、私信承接、内容复用和跨平台改写；
- 增加县域农产品案例、行业模板和地区语言。

### 长期方向：县域内容基础设施

禾语 AI 将继续扩展可配置的县域知识空间、内容资产库和团队工作流，让地方产业经验可以沉淀，让内容生产可以复制，让机构能够在本地部署和模型可替换的基础上长期运营。

## 项目结构

```text
apps/
  api/                 FastAPI、数据模型、知识检索与 AI Provider
  web/                 首页、农户简单模式与团队工作台
docs/                  产品、架构、部署、演示和验收文档
evals/                 离线评估集与评估结果
scripts/               启动、测试、审计、打包与演示脚本
.github/workflows/     GitHub Actions
```

<a id="contributing"></a>

## 参与建设

欢迎提交 Issue、补充真实使用场景、改进文档与测试，或从功能分支发起 Pull Request。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

特别欢迎这些方向：

- 农产品内容方法与真实经营场景；
- 简体中文、香港繁体中文和英文体验；
- FastAPI、检索、模型适配与数据结构；
- 前端交互、响应式与可访问性；
- Playwright E2E、部署与工程质量。

实地调研与农户资料遵循授权、最小必要和脱敏原则。

## English

**Heyu AI is an open-source content production and operations platform for farmers, agricultural cooperatives, and rural content teams.**

It connects product profiles, authorized field research, trend references, content planning, publishing records, and performance feedback. From one structured brief, users can compare three creative directions and produce a complete short-video package including hooks, scripts, mobile shot lists, publishing suggestions, and reusable operation plans.

The MVP runs locally with SQLite and a deterministic Mock provider, supports Simplified Chinese, Traditional Chinese for Hong Kong, and English, and can connect to any model service that exposes an OpenAI-compatible chat completions API.

## License

[Apache License 2.0](LICENSE)

<div align="center">

**把真实产地经验沉淀为可复用的内容能力，让更多乡村好产品被看见、被理解、被记住。**

</div>
