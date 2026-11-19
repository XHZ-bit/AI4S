# Research Atlas：GitHub 轻量运维选型核验

核验日期：2026-10-19。约束为 2 核 2GB、每年 500 元预算、单实例 FastAPI、SQLite 个人目录及现有 Compose/Nginx。本文只做源码检查与官方资料核验，没有安装候选工具、启动服务、购买资源或发布公网；没有进行 Docker 镜像构建、容量压测或恢复实测。

建议近期依次完成 **uv 依赖锁定、restic 完整备份与恢复演练、Caddy HTTPS 入口**。前两项可先在隔离环境完成；Caddy 的公网接入仍需域名、备案、服务器与发布授权。观测先使用结构化日志和健康/备份状态，按需要再增加指标库。Litestream 暂缓作为主备份方案。

## 候选与维护证据

下表日期来自本次官方 GitHub Release 页面；前四项还核对了页面 `relative-time datetime` 的完整 UTC 时间。没有用搜索引擎的相对时间推算发布日期，也没有用星数代替维护证据。发布记录只能证明存在该次发布，不代表本项目已验证兼容性。

| 候选 | 官方仓库及许可证 | 本次 `/releases/latest` 指向及发布日期 | 本项目判断 |
|---|---|---|---|
| Caddy | [caddyserver/caddy](https://github.com/caddyserver/caddy)，[Apache-2.0](https://github.com/caddyserver/caddy/blob/master/LICENSE) | [v2.11.7](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)，2026-10-03，UTC 05:58:33 | 优先，补 HTTPS 与入口代理配置 |
| restic | [restic/restic](https://github.com/restic/restic)，[BSD-2-Clause](https://github.com/restic/restic/blob/master/LICENSE) | [v0.19.1](https://github.com/restic/restic/releases/tag/v0.19.1)，2026-07-05，UTC 08:13:33 | 优先，保存完整、多版本的异机备份 |
| uv | [astral-sh/uv](https://github.com/astral-sh/uv)，[MIT](https://github.com/astral-sh/uv/blob/main/LICENSE-MIT) 或 [Apache-2.0](https://github.com/astral-sh/uv/blob/main/LICENSE-APACHE)，由使用者二选一 | [0.13.1](https://github.com/astral-sh/uv/releases/tag/0.13.1)，2026-10-14，UTC 05:15:30 | 优先，固定 Python 依赖和构建工具 |
| Litestream | [benbjohnson/litestream](https://github.com/benbjohnson/litestream)，[Apache-2.0](https://github.com/benbjohnson/litestream/blob/main/LICENSE) | [v0.5.17](https://github.com/benbjohnson/litestream/releases/tag/v0.5.17)，2026-08-31，UTC 21:59:32 | 后续降低数据库丢失窗口的补充方案 |
| Prometheus FastAPI Instrumentator | [trallnag/prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)，[ISC](https://github.com/trallnag/prometheus-fastapi-instrumentator/blob/master/LICENSE)；其 routing 模块另含 BSD-3-Clause 代码，见仓库 README Licensing | [v8.1.0](https://github.com/trallnag/prometheus-fastapi-instrumentator/releases/tag/v8.1.0)，2026-07-26 | 可选，先做最小指标再决定是否需要采集服务 |

GitHub REST API 在本次共享出口触发匿名限流，故维护日期采用官方 Release HTML，而非缺失的 API 字段。许可证均已读取官方 LICENSE；uv 的双许可选择和 Instrumentator 的模块许可补充也核对了 README。

## 1. uv：先固定已验证环境

当前 `backend/pyproject.toml` 大多只有版本下限，`backend/Dockerfile` 直接执行 `pip install .`；CI 也另装未固定版本的 Ruff。Docker 使用 Python 3.11，CI 使用 3.12。重建时依赖版本可能变化，这会影响已通过的验收结果是否能复现。此判断来自本地上述文件及 `.github/workflows/ci.yml`。

uv 支持项目锁文件；`--locked` 在锁文件与项目元数据不符时失败，`--frozen` 则跳过一致性检查。CI 应优先使用 `--locked`，不能把 `--frozen` 当成“锁文件有效”的验证。[官方锁定与同步说明](https://docs.astral.sh/uv/concepts/projects/sync/)。

拟接入文件与步骤：

1. 在独立环境记录当前通过测试的直接、间接依赖版本，审查后生成并提交 `backend/uv.lock`，同时固定 uv 工具版本。初次锁定不能未经比较就把全部依赖升级到最新。
2. 统一 CI 与镜像的 Python 次版本；如果保留 3.11/3.12 两个目标，则分别验证。将 Ruff 纳入锁定的开发依赖；现有 `dev` 是 optional extra，需使用 `--extra dev`，不能误以为默认开发组会包含 pytest/respx。
3. 迁移 `.github/workflows/ci.yml` 为锁文件检查和锁定安装，再运行原有测试/浏览器验收。工具安装 Action 固定提交，工具版本固定；参考 [uv GitHub Actions 集成](https://docs.astral.sh/uv/guides/integration/github/)。
4. 迁移 `backend/Dockerfile`：先按锁文件安装依赖，再复制源码并完成项目安装，运行时使用固定虚拟环境。若第一层还没有 `app/`，不能尝试完成项目包安装；先用 `--no-install-project` 缓存依赖层，再安装项目。镜像参考 [uv Docker 指南](https://docs.astral.sh/uv/guides/integration/docker/)。
5. 检查 `start.ps1`、`demo.ps1` 和各验收脚本对 Python 的选择：目前 `Get-Command python` 不会自动选择新建的 `backend/.venv`。要显式选择项目解释器或统一使用 `uv run`，再验证启停和环境恢复。

建议的准备命令，仅供后续迁移使用，本次未执行：

```powershell
uv lock --project backend
uv sync --project backend --locked --extra dev
```

必须同时审查 `[build-system]` 中的 `setuptools>=68` 等构建依赖。运行依赖锁定不自动约束所有隔离构建依赖；uv 提供 `build-constraint-dependencies`。[官方构建依赖约束](https://docs.astral.sh/uv/reference/settings/#build-constraint-dependencies)。还需固定 Python/Node/Nginx/uv 镜像版本与 digest、目标平台及 CI 中临时安装的 Playwright 版本。它们合起来改善环境可重复性；不能承诺仅加一个 `uv.lock` 就得到逐字节相同的镜像。

资源与费用：uv 用在安装和构建阶段，无需新增业务常驻服务。本项目的安装耗时、峰值内存、镜像大小及节省金额均未实测；不要照搬上游速度倍率。

## 2. restic：先解决完整多人备份

当前中央账号库位于 `DATA_DIR/identity.db`，个人数据位于 `DATA_DIR/users/<id>/atlas.db` 和相邻 `pdfs/`。现有 `backend/app/data_archive.py` 以根目录 `atlas.db` 为入口，不能直接把它当成整个多人部署的备份器；`docs/multiuser-trial.md` 已记录这个边界。

restic 提供文件备份、去重和仓库加密，适合将一致的暂存副本送到异机；它不会替应用建立跨数据库、PDF 的事务边界。[官方仓库 README](https://github.com/restic/restic)、[备份说明](https://restic.readthedocs.io/en/stable/040_backup.html)。以下一致性流程是针对本项目的工程方案。

拟新增 `ops/backup-multiuser.sh`、`ops/restore-multiuser.sh`、调度模板和隔离恢复验收；可新增 `backend/scripts/backup_multiuser.py` 管理清单。首版采用可解释的短暂停写方案：

1. 记录原运行状态，停止接收写入，等待 API 和所有写入进程退出；后续如拆出 worker，也必须包含 worker。同步禁止账号 CLI 修改。不能只隐藏上传按钮。
2. 在业务目录之外创建唯一暂存目录。在无写入期间，用 SQLite Backup API 分别导出 `identity.db` 与全部个人业务库，复制 PDF 及其他需要恢复的业务文件，记录相对路径、大小、SHA-256、应用提交与镜像/锁文件版本。逐库执行 `PRAGMA integrity_check`。SQLite 备份 API 提供单库一致副本；跨库一致性来自上述统一停写边界。[SQLite 官方 Backup API](https://www.sqlite.org/backup.html)。
3. 完成并核验不可变暂存副本后恢复原先运行的服务，再由 restic 上传暂存目录。网络上传不应延长整个停写窗口。失败路径必须可靠恢复原服务状态，同时保留错误证据；本次没有实施启停。
4. 使用受限权限的仓库凭据和独立保管的仓库密码。仓库不能放在待备份业务树内；加密仓库也不能成为密码的唯一存放处。
5. 通过初次恢复演练后再启用保留策略。例如 7 个日备份、4 个周备份可以作为讨论起点，最终按实际空间和账单调整。清理和 `prune` 属于单独受控操作，不能在没有已验证恢复点时自动删旧副本。[官方保留策略](https://restic.readthedocs.io/en/stable/060_forget.html)。

Linux 部署可用 systemd timer 定时调用，无需再运行一个备份管理平台。首个目标是夜间备份；若每天一次，最坏可丢失接近一天的新数据，这是拟定 RPO，不是已实现承诺。备份完成时间、最近成功快照 ID、失败原因和剩余磁盘应能由维护者检查。

恢复验收必须在新目录/新卷完成，禁止覆盖运行中的数据：

- `restic check` 检查仓库，再恢复明确的快照 ID；定期进行抽样数据读取和完整恢复。仓库检查不能替代应用验收。[官方仓库检查](https://restic.readthedocs.io/en/stable/045_working_with_repos.html)。
- 核对中央账号与个人目录一一对应，逐库检查完整性，校验 PDF 哈希、原文下载、学习记录、课题与快照导出，并重跑双账号隔离用例。
- 恢复会话库后统一撤销旧会话；检查重启任务状态，不让已完成或被取消的任务重新外发。恢复耗时和可接受停机时间目前未实测。
- 保留原数据和兼容版本。数据已经迁移后，仅回退代码不一定能回退数据格式。

资源与费用：定时 CLI 不新增业务常驻进程，但备份/清理时会占 CPU、内存、磁盘和带宽；本项目均未实测。需要预留完整暂存副本及仓库缓存空间，不能只看原始 PDF 总量。异机容量、请求、恢复出网以及长期保留仍会产生费用；开源软件不能证明年度 500 元一定足够。本次没有询价或开通存储。

## 3. Caddy：补入口，保持现有业务栈

Caddy 官方支持证书自动申请、续期与 HTTP 转 HTTPS；公网模式依赖正确 DNS、可达端口及持久化可写证书存储。[自动 HTTPS 文档](https://caddyserver.com/docs/automatic-https)。它解决当前入口运维缺口，不替代账号、授权或资料隔离。

拟新增 `ops/caddy/Caddyfile` 和生产 Compose 覆盖文件，保留现有多人 Compose 供回环测试：

- Caddy 作为唯一公网入口，`/api/*` 直接转发 `backend:8000`，静态页面转发 `frontend:80`。原 Nginx 继续提供静态构建，这样 API 不再经过两层会重写代理头的入口。
- 持久化 Caddy 的 `/data`、`/config`，固定镜像版本与 digest；不要发布管理接口。Docker 网络内使用服务名和容器端口，不使用 `localhost` 指向另一个容器。[官方 Compose 示例](https://caddyserver.com/docs/running#docker-compose)。
- Caddy 会设置转发协议和客户端地址，并默认忽略客户端伪造的相应转发头。[官方反向代理头处理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers)。后端仍需显式配置可信代理来源，仅信任明确代理地址/隔离网络中的代理；不把任意来源的转发头视为可信。
- 调整 `backend/Dockerfile` 或生产启动命令中的 Uvicorn 代理信任配置；保留 `SESSION_SECURE_COOKIE=true`。现有 `AccountBoundary` 比较 Origin 与请求协议/Host，必须让 ASGI 正确识别 HTTPS，不能通过关闭来源检查来“修好登录”。
- 增加 HTTPS 浏览器验收：登录、退出、CSRF、停用账号、真实客户端限流、伪造转发头、PDF 分段读取/下载、快照导出及后端重启。证书先在 staging 环境测试，后续正式切换仍需授权。

资源与费用：新增一个入口进程，相对现有 Nginx 的实际额外内存、TLS 峰值与吞吐均未在 2GB 主机测过。Caddy 软件无需采购商业授权，但域名、主机、备案、带宽和可用性仍需分别落实；本次没有发布任何入口。

## 4. 观测：日志先行，指标库可选

先使用 Caddy JSON 访问日志、现有应用日志、`/health`、任务积压与备份最近成功时间。记录请求耗时、状态码、路由模板、任务阶段和稳定错误码即可，先补磁盘/备份失败可见性，再决定是否需要长期时序存储。

Caddy 默认会遮蔽 Cookie、Set-Cookie 和标准授权头，但业务自定义头与查询内容仍需显式过滤。[官方日志说明](https://caddyserver.com/docs/caddyfile/directives/log)。本项目应额外去除 `X-Atlas-Csrf`、自定义凭据及查询字符串中的私有内容，不记录正文、PDF、密码或 prompt；日志轮转已有 Compose 配置，可以复用。

如随后需要 HTTP 指标，可在 `backend/pyproject.toml`/锁文件增加 Instrumentator，在 `backend/app/main.py` 注册。它提供请求次数和时延等指标，但上游明确提醒通用中间件会带来性能成本；不应把“库比整套平台少组件”写成已测低开销。[官方 README](https://github.com/trallnag/prometheus-fastapi-instrumentator)。

接入前必须解决两个本地契约：一是使用固定路由模板/状态类别，不能把用户 ID、任务 ID、论文名、查询文本当标签；二是当前 `AccountBoundary` 默认保护所有路径，不能直接照抄 `.expose(app)` 后把 `/metrics` 加入匿名公网白名单。指标应仅通过受控内部采集或专门管理员授权访问。先验收权限及稳定标签，再测延迟和内存增量。当前没有部署 Prometheus、Grafana、Loki 或 OpenTelemetry Collector。

## 5. Litestream：可降丢失窗口，不能代替完整备份

现行 Litestream 配置已经支持目录、glob、递归与动态监视，不能据旧版认知把它描述为“只支持一个固定数据库”。[官方配置](https://litestream.io/reference/config/)。它工作于 SQLite WAL 模式，并存在复制间隔造成的数据丢失窗口。[官方限制](https://litestream.io/tips/)。

本项目如以后引入，需新增 `ops/litestream.yml`，纳入中央 `identity.db` 和所有新建个人 `atlas.db`，为同名个人库生成唯一、稳定的远端前缀，验证账号新建/停用/删除后的发现与保留行为。恢复还必须知道每个数据库对应的用户与复制恢复点，并匹配当时的 PDF 文件版本。

多个数据库各自复制成功，不表示它们与 PDF 在同一业务时点；数据库恢复到一小时前、PDF 却只有今天的版本会产生悬空引用。上述跨库、文件清单与加密/访问控制要求仍须应用侧补齐。因此首版先用 restic 保存统一停写得到的完整快照；未来只有明确需要缩短 RPO，且完成多库加 PDF 的恢复演练后，再考虑 Litestream 作为补充。

资源与费用：每库监视、元数据、复制间隔、远端请求和保留的实际成本都未在本项目测量，不能承诺“每秒复制不占预算”。新增备份目标也不能被描述为零费用。

## 暂缓更重的基础设施

以下为基于本项目规模的取舍，不是对这些项目的性能实测结论：

- Keycloak：当前约 20 个维护者发放账号，已有个人空间和会话实现，短期没有明确的企业 SSO/身份联邦需求。另建身份服务及生产数据库会增加迁移与运维边界；若以后确需联邦身份再重新评估。[Keycloak 生产部署指南](https://www.keycloak.org/server/configuration-production)。
- Temporal：当前主要是单机 PDF/科研后台任务，先完善现有任务持久记录、取消、重启恢复和幂等。额外运行工作流服务及其存储属于更大的架构变更，当前没有跨服务长工作流的证据支持。[Temporal 自托管指南](https://docs.temporal.io/self-hosted-guide)。
- 整套日志与时序监控：先明确要回答的问题和告警对象。采集、索引、存储、仪表与告警组件会增加常驻进程和保留策略，本轮没有测出 2GB 主机可承受的余量；先用结构日志、健康探测、磁盘与备份状态覆盖实际故障。

## 后续实施验收顺序

| 顺序 | 可审查交付 | 通过标准 |
|---|---|---|
| 1 | uv 锁文件、工具/解释器/构建约束、CI 更新 | 干净隔离环境锁定安装成功；原后端、前端、浏览器与启停验收通过，记录实际版本 |
| 2 | 完整多人备份/恢复脚本和清单 | 新卷恢复账号、全部个人库和 PDF；双账号隔离、会话撤销、原文哈希及导出通过；记录备份时长、峰值资源和恢复时长 |
| 3 | Caddy 生产覆盖配置与可信代理规则 | 测试环境 HTTPS 与身份全流程通过；确认资源余量；域名和公网授权齐全后才能切换 |
| 4 | 日志/最小指标与备份失败可见性 | 不泄露私有内容，标签数量有界，指标访问受限，能定位真实故障 |
| 后续 | Litestream 补充验证 | 先定义更小 RPO，再证明新建个人库和 PDF 都能恢复到一致状态 |

以上均为待实施路线；本次只新增这份研究记录，没有改业务代码或启用运维服务。
