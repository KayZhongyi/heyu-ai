# Render 免费在线 Demo

本文档用于比赛前的短期、受监督演示，不代表平台已经通过公网商业运营门槛。

## 部署结构

- 一个 Render Free Web Service，使用仓库中经过 CI 构建验证的 Dockerfile；
- 一个同区域的 Render Free PostgreSQL；
- Web 服务启动时先执行 `alembic upgrade head`，成功后再启动 API；
- `/ready` 同时验证应用和数据库；
- 默认使用零费用 `DeterministicProvider`，不会调用付费模型；
- 数据库不开放公网 IP，应用密钥由 Render 自动生成。
- 整个演示站点有独立访问密码，未知访客不能创建组织或查看工作台。

仓库可以保持 Private。创建 Blueprint 时，只需要授权 Render 读取这个仓库。

## 免费版限制

Render 免费 Web Service 闲置后会休眠，第一次重新访问需要等待唤醒。免费
PostgreSQL 有有效期，因此它只适合作为短期 Demo 数据库。部署前应再次查看
[Render Free 文档](https://render.com/docs/free)，确认当时的额度和期限没有变化。

不要在免费 Demo 中录入真实个人信息、客户秘密、未获授权的农户资料或生产密钥。

## 创建在线 Demo

1. 确认目标提交的 GitHub Actions 全部通过；
2. 登录 Render，选择 **New → Blueprint**；
3. 授权并选择禾语 AI 仓库；
4. Render 会读取仓库根目录的 `render.yaml`；
5. 为 `DEMO_BASIC_AUTH_PASSWORD` 填写一个至少 12 位、未在其他地方使用的临时密码；
6. 确认 Web Service 和 PostgreSQL 均为 **Free**，然后创建 Blueprint；
7. 等待 `/ready` 健康检查通过，记录 Render 提供的 HTTPS 地址。

不需要在 Render 控制台手工填写 `APP_SECRET` 或 `DATABASE_URL`。Blueprint 会分别
生成密钥并绑定 PostgreSQL 私有连接串。

浏览器首次打开时会显示系统登录框。用户名固定为 `heyu-demo`，密码是创建
Blueprint 时填写的临时密码。只将这组信息发送给本次演示成员，演示结束后立即删除。

## 准备两至三个展示账号

推荐使用同一个演示组织中的三个角色：

- `owner`：负责人，管理组织、资料、成员与审核流程；
- `creator`：内容同学，生成和修改营销内容；
- `reviewer`：审核同学，查看依据并完成内容审核。

账号必须通过平台的 Bootstrap、邀请和接受邀请接口创建，不要把账号密码或数据库种子
硬编码进仓库。先在当前 PowerShell 窗口设置临时密码：

```powershell
$env:HEYU_DEMO_USERNAME = "heyu-demo"
$env:HEYU_DEMO_PASSWORD = "<Render 外层访问密码>"
$env:HEYU_DEMO_OWNER_PASSWORD = "<负责人临时密码>"
$env:HEYU_DEMO_CREATOR_PASSWORD = "<内容账号临时密码>"
$env:HEYU_DEMO_REVIEWER_PASSWORD = "<审核账号临时密码>"
```

四个密码必须各不相同；外层访问密码至少 12 位，三个账号密码至少 10 位。

然后运行：

```powershell
python scripts/setup_demo_accounts.py `
  --base-url https://实际地址.onrender.com `
  --accounts 3 `
  --output outputs/render-demo-accounts.json
```

默认邮箱为 `leader@demo.example`、`video@demo.example` 和 `review@demo.example`。平台当前
不发送邮件，因此可使用这些合成地址；需要更换时使用 `--owner-email`、`--creator-email`
和 `--reviewer-email`。只需要两个账号时传入 `--accounts 2`。

一次完整执行成功后，脚本可重复运行：已有组织会改为登录，已有成员会被验证而不会重复创建。
如果已有账号的角色不一致，脚本默认停止；负责人确认确实需要修改后，才可增加
`--repair-roles`。输出报告只包含组织、邮箱、角色和用户 ID，不包含密码、访问令牌或邀请令牌。
临时密码应通过私下渠道发送，演示结束后删除 Render 资源。

## 首次验收

将实际地址替换到下面的命令中：

```powershell
$env:HEYU_DEMO_USERNAME = "heyu-demo"
$env:HEYU_DEMO_PASSWORD = "你在Render中填写的临时密码"

python scripts/acceptance-smoke.py `
  --base-url https://你的-render-地址.onrender.com `
  --output outputs/render-acceptance.json
```

然后人工确认：

1. 首页和工作台可以打开；
2. 首位负责人可以创建演示组织；
3. 品牌、农产品和知识资料可以提交并审核；
4. 短视频脚本、直播话术和手机拍摄清单可以生成；
5. 内容版本、引用来源和审核记录可以查看；
6. 简中、香港繁中、英文切换正常；
7. 服务休眠并重新唤醒后，账号及演示数据仍然存在。

验收仅使用合成数据或明确获准的材料。`outputs/` 中的报告不得提交到 Git。

## 演示结束

1. 导出需要保留的非敏感演示记录；
2. 删除 Render Blueprint 或至少删除数据库；
3. 撤销 Render 对 GitHub 仓库的访问（如果后续不再使用）；
4. 不要将免费 Demo 直接延长为正式商业服务。

公网商业运营仍需完成 `docs/release-gates.md` 中的安全、恢复、隐私、告警和容量门槛。
