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
