# 受控多人试用

当前支持可选 `ACCESS_MODE=multiuser`。原有本机模式保持默认，无需账号；多人模式必须登录，每人拥有独立 SQLite 和资料目录。已支持维护者创建账号、可关闭的自主注册、一次性恢复码，以及配置 SMTP 后的邮箱验证与邮件找回；实际邮箱配置见[账号服务说明](ui-account-services-2026-10-28.md)。统一模型费用台账、完整运营审计及公网运维仍待完善。本说明于2026-10-29核对，以下区分已有账号能力与受控多人部署限制。

## 已实现的边界

- 会话 Cookie 使用 HttpOnly、SameSite=Strict，默认 Secure，固定到期；服务端只保存随机令牌的 SHA-256。密码使用随机盐和 scrypt，无默认账号或默认密码。
- 写请求验证会话 CSRF token 和浏览器来源；服务端鉴权覆盖文件、导出、任务取消和重试。账号管理需要管理员权限，停用账号立即撤销会话；修改或重置密码撤销全部会话。
- 中央账号库位于 `DATA_DIR/identity.db`；个人数据位于 `DATA_DIR/users/<账号ID>/`。没有个人上下文时拒绝打开业务库，不退回原有全局数据库。旧本机资料不自动迁入或共享。
- 任务线程继承个人空间，取消句柄包含空间标识；不同数据库中相同的任务编号互不影响。默认全站一个执行线程，每人至多一个排队或运行中的任务。
- 每用户默认限制 20 篇论文、PDF 5MB/50 页、原文文件 100MB。页数、大小和配额在服务端检查，重复相同文件不重复占用份数；同步上传解析与远程采集暂不开放。
- 多人模式强制关闭新旧统一付费模型、GROBID 外发和共享 Neo4j。人工方案、原文阅读、学习记录、本地检索、行动清单及快照导出可用；新增空间知识图谱使用账号内的 SQLite，来源文件、节点及学习内容按个人数据库隔离。系统状态里的旧共享图服务不可用，不等同于空间 SQLite 图谱未实现。模型生成需要统一多用户预算后再开放。
- 受控多人模式同时关闭统一资料入口的远程链接导入，避免绕过旧的远程采集边界。新增 DOCX、代码等资料的跨文件总存储配额仍需统一完善，不能把现有 PDF 配额称为全类型资料完整配额。
- 登出、账号变化及会话失效会卸载工作空间并清除当前浏览器的 Atlas 本地草稿，避免在公共电脑显示前一账号的输入。重要内容请先保存到服务端。

密码哈希采用 scrypt `N=2^15, r=8, p=3`（32MiB 档），参数依据 [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。

## 启动独立试用环境

使用独立的 Compose 项目与卷，不复用原 `backend_data`。下列 HTTP 配置只用于本机回环测试：

```powershell
# 在项目根目录；需要 Docker Desktop 已启动
$env:ATLAS_MULTIUSER_SECURE_COOKIE = 'false'
docker compose -f docker-compose.multiuser.yml up -d --build
docker compose -f docker-compose.multiuser.yml exec backend python scripts/manage_users.py create --username administrator
```

命令交互输入至少 12 字符的密码，不把口令放在命令参数或输出中。打开 http://127.0.0.1:15173，登录后通过顶部“账号管理”创建普通用户。用户名使用 3 至 64 位英文字母、数字、点、横线或下划线。

```powershell
docker compose -f docker-compose.multiuser.yml exec backend python scripts/manage_users.py list
docker compose -f docker-compose.multiuser.yml exec backend python scripts/manage_users.py reset-password --username administrator
docker compose -f docker-compose.multiuser.yml stop
```

`stop` 保留资料。再次 `up -d` 复用同一卷。不要执行 `down -v`，该命令会删除卷中的账号和个人资料。

部署 HTTPS 时移除上述 Cookie 环境覆盖，保持 `SESSION_SECURE_COOKIE=true`。配置可信反向代理，使应用识别实际 HTTPS 协议，并验证请求来源检查、Cookie、PDF 和导出。当前文件仅绑定回环地址，不执行公网发布或域名/证书配置。

登录失败按用户名与来源地址限速。当前 Nginx 部署下来源可能聚合为代理地址，适用于本机试用；公网部署前需配置并验证可信代理的真实客户端地址传递，避免把多位用户误计入同一限流桶，不能直接信任任意客户端转发头。

不用 Docker 时，可在独立终端设置 `ACCESS_MODE=multiuser`、绝对路径 `DATA_DIR` 和仅供本机 HTTP 的 `SESSION_SECURE_COOKIE=false`，从 `backend` 目录运行 CLI 创建管理员，再运行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8001`。另一个终端在 `frontend` 设置 `ATLAS_API_TARGET=http://127.0.0.1:8001`，运行 `npm run dev -- --host 127.0.0.1 --port 5174`。两者数据均独立于默认本机目录；原 `start.ps1` 面向单机模式。

## 备份和恢复

使用 [整站备份与恢复工具](multiuser-backup-recovery.md)，先停止多人服务，再对 `identity.db` 和完整的个人资料库生成一致快照。工具会拒绝活跃写入、逐文件校验、检查账号与个人目录，恢复到全新目录并撤销旧会话。原单库 `data_archive.py` 仍只处理本机业务目录。恢复先使用隔离目录或新卷演练，核对账号、资料和会话失效后再切换。

## 公开试用的剩余工作

本轮交付范围见 [1.0 升级说明](unified-release.md)。统一资料配额及总空间上限、完整操作审计、多用户模型计量、生产 HTTPS/备份恢复/告警/回滚与真实负载验收仍属于后续公开服务准备。注册与邮件找回代码已经实现；真实邮件商、公网地址及生产投递仍须部署配置和验证。当前实现不代表上述公开服务条件已经完成。
