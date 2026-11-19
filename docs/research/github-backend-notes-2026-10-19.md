# Research Atlas 后端开源候选核验（2026-10-19）

本次读取了官方 GitHub README、许可证、发布记录及官方文档，并通过公开 GitHub API 核验发布日期和仓库状态。未安装、启用或修改业务代码。

评估约束：FastAPI、SQLite 独立个人空间、约 20 个受邀账号、2 核 2GB、约 500 元年基础设施预算。以下接入方案和优先级属于结合当前代码的工程判断；资源比较依据依赖及进程数量，尚无本机 RSS 压测数据。

## 决策

当前应先补模型调用的轻量统一预算账本；现有任务台账、租户隔离、取消和重启恢复继续保留。本表最多列两项有条件的 P1 候选，不要求立即引入新的服务。

| 候选 | 核验许可 | GitHub latest release（UTC 日期） | 取舍 |
|---|---|---|---|
| [Huey](https://github.com/coleifer/huey) | MIT | [3.4.0，2026-09-04](https://github.com/coleifer/huey/releases/tag/3.4.0) | P1：确需独立 consumer、调度时接入；不能把它当成任务必达恢复方案 |
| [PyrateLimiter](https://github.com/vutran1710/PyrateLimiter) | MIT | [v4.5.0，2026-08-30](https://github.com/vutran1710/PyrateLimiter/releases/tag/v4.5.0) | P1：确需统一请求频率准入时，小范围使用 SQLite 后端 |
| [Authlib](https://github.com/authlib/authlib) | BSD-3-Clause；另有商业许可/支持 | [v1.9.1，2026-10-14](https://github.com/authlib/authlib/releases/tag/v1.9.1) | P2：有明确学校/组织 OIDC 身份源后再接入 |
| [FastAPI Users](https://github.com/fastapi-users/fastapi-users) | MIT | [v15.0.5，2026-03-27](https://github.com/fastapi-users/fastapi-users/releases/tag/v15.0.5) | 暂缓：官方已声明维护模式，不为现有 20 账号系统做整套迁移 |
| [LiteLLM](https://github.com/BerriAI/litellm) | 非 enterprise 部分 MIT；enterprise 为商业许可 | [v1.106.0，2026-10-18](https://github.com/BerriAI/litellm/releases/tag/v1.106.0) | 暂缓完整网关；先借鉴预算预占、结算和拒绝调用的方法 |

上述五个仓库在核验时均未归档。日期取自各仓库公开 `/repos/{owner}/{repo}/releases/latest` 的 `published_at`，不以 star 数或抓取时间代替维护证据。FastAPI Users 的维护声明优先于“仍有新发布”的表面判断。

## Huey：独立调度可取，运行中恢复仍由业务负责

官方 API 明确 SqliteHuey 的队列及结果使用标准库 sqlite3；无需另建 Redis。官方消费者支持 thread/process 等执行模式，默认一个 thread worker。2GB 单机可从“一个 consumer 进程、一个 worker”试验，避免并列启动多个 PDF 解析进程。[API 与 SqliteHuey](https://huey.readthedocs.io/en/latest/api.html#SqliteHuey)、[消费者配置](https://huey.readthedocs.io/en/latest/consumer.html)、[MIT 原文](https://raw.githubusercontent.com/coleifer/huey/master/LICENSE)。

维护证据：3.4.0 的官方发布及后续主分支变更可见，包含消费者关闭选项和 SQLite 出队改进。[发布说明](https://github.com/coleifer/huey/releases/tag/3.4.0)。

本项目增量价值是把 Web 服务与任务执行分开，并获得延迟调度、定时任务和失败重试工具。建议接入点：`backend/app/tasks.py` 的分发接口、`backend/app/jobs.py` 的任务入口、`backend/app/main.py` 的恢复流程；新增受控 worker 入口和运维启动配置。

必须保留的边界：

- 官方明确说明 **“does not guarantee at-least-once delivery of messages”**，也不对任务完成做 ACK。强杀 consumer 可丢失正在执行的消息；持久化待执行队列不等于运行中任务必达恢复。[关闭语义](https://huey.readthedocs.io/en/latest/consumer.html#consumer-shutdown)。
- 跨进程任务负载仅放白名单中的 `user_id + task_kind + task_id`。worker 重查账号状态后进入 `user_scope`；不能依赖当前 `copy_context()` 跨进程传递，也不把 Cookie、数据库连接或 PDF 字节塞进消息。
- 继续以每用户 SQLite 任务台账为事实来源，设计提交后 outbox/重放、运行租约、幂等键和 checkpoint；保留 `task_control.py` 的取消与超时检查。业务库提交与另一份队列 SQLite 写入不是天然的同一事务。
- 线程 worker 的 timeout 仍需协作检查；官方多进程消费者不支持 Windows。付费模型调用不能因为装了队列库而自动重试。[任务 timeout](https://huey.readthedocs.io/en/latest/api.html#Huey.task)、[平台与 worker 限制](https://huey.readthedocs.io/en/latest/consumer.html#worker-types)。

## PyrateLimiter：补请求准入，不替代配额账本

官方 README 说明 SQLiteBucket 持久化限流状态，并注明 **“Persists state to SQLite (sync only)”**；同机多进程共享可以使用文件锁。MIT 已读，`filelock` 是可选额外依赖，无需 Redis 服务。[README 的 SQLiteBucket](https://github.com/vutran1710/PyrateLimiter#sqlitebucket)、[依赖声明](https://raw.githubusercontent.com/vutran1710/PyrateLimiter/master/pyproject.toml)、[MIT 原文](https://raw.githubusercontent.com/vutran1710/PyrateLimiter/master/LICENSE)。

维护证据：v4.5.0 发布含新的限流算法、retry-after 决策及可选后端打包修复；主分支仍有变更。[发布记录](https://github.com/vutran1710/PyrateLimiter/releases/tag/v4.5.0)。

接入点为 `backend/app/access.py` 的已认证昂贵请求入口，或新增 `backend/app/rate_limits.py`：按 `user_id + operation` 设置短窗限制，对未认证登录保留现有账号/IP 保护。返回 429 与重试时间，不在 ASGI 事件循环或唯一任务 worker 中长时间等待配额。若用同步 SQLiteBucket，数据库操作须安排在适当的同步执行边界。显式指定持久数据库路径，不使用默认临时文件。

它解决突发请求频率，不能代替 PDF 存储上限、个人任务并发上限、公平排队、token 预占或人民币金额结算。现有 `accounts.py` 已有 SQLite 登录限速；不能仅为了替换那几行代码引入一层依赖。

## Authlib：有 OIDC 需求再扩展登录

当前根许可证为 BSD-3-Clause。README 明确开源及闭源项目都可选择 BSD 使用，另有商业支持，不应把“有商业许可”写成“普通使用必须付费”。[BSD 原文](https://raw.githubusercontent.com/authlib/authlib/main/LICENSE)、[README 许可说明](https://github.com/authlib/authlib#license)。

维护证据为 2026-10-14 的 v1.9.1 发布。官方提供 FastAPI/Starlette OAuth/OIDC 集成；所读 FastAPI 示例使用临时会话保存授权流程状态。[发布](https://github.com/authlib/authlib/releases/tag/v1.9.1)、[FastAPI 客户端文档](https://docs.authlib.org/en/v1.6.9/client/fastapi.html)。当前主分支运行依赖包括 cryptography、joserfc；仍需实际客户端 HTTP/会话集成，不必自建完整身份提供商。[依赖声明](https://raw.githubusercontent.com/authlib/authlib/main/pyproject.toml)。

有学校/组织统一登录后，在 `backend/app/api/accounts.py` 增加登录/回调接口，并在 `backend/app/accounts.py` 建 `(issuer, subject) -> 内部 user_id` 映射。继续复用本项目 session、停用、角色和个人空间；禁止按不受验证的 email 直接合并账号，仍维持邀请名单。还需设计临时授权状态、OIDC nonce/PKCE 及跨站重定向 Cookie 策略。现有 SameSite=strict 会话不能不经测试直接当作 OAuth 重定向状态存储。

Authlib 处理身份协议，不提供本项目的资料租户隔离、角色分配、队列所有权或预算。只有受邀密码登录需求时，无需为它增加 IdP 服务与运维成本。

## FastAPI Users：维护模式不等于废弃，但现在不值得迁移

官方 README 原文：**“This project is now in maintenance mode”**。其后说明继续提供安全更新与依赖维护，不再增加新功能，并在开发未来替代工具；不能称其已经无人维护。[维护声明与功能](https://github.com/fastapi-users/fastapi-users#readme)、[MIT 原文](https://raw.githubusercontent.com/fastapi-users/fastapi-users/master/LICENSE)。v15.0.5 发布实际是依赖维护，符合该声明。[发布说明](https://github.com/fastapi-users/fastapi-users/releases/tag/v15.0.5)。

它可提供用户模型、登录/注册、密码重置、验证邮箱和可插拔认证后端。若重构，会涉及 `backend/app/accounts.py`、`backend/app/api/accounts.py`、`backend/app/access.py`，以及现有身份库/密码/会话迁移。采用其现成 SQLAlchemy 适配还会引入 ORM/异步数据库适配层；不要求额外常驻服务，但迁移成本明显高于当前 20 账号的收益。[官方数据库适配说明](https://github.com/fastapi-users/fastapi-users#features)。

它不会自动给现有 SQLite 个人空间、文件、后台任务建立授权边界，也不会解决模型预算。不能因为它提供开放注册路由就顺带改变本项目邀请制。

## LiteLLM：统一调用有用，完整预算网关暂缓

根 LICENSE 将 enterprise 目录排除在 MIT 范围之外。实际商业文件目前位于 `enterprise/LICENSE.md`，生产使用需要符合商业条款和席位许可；不能把整个仓库概括成纯 MIT。[根 LICENSE](https://raw.githubusercontent.com/BerriAI/litellm/main/LICENSE)、[Enterprise 许可证原文](https://raw.githubusercontent.com/BerriAI/litellm/main/enterprise/LICENSE.md)。

官方产品文档区分：Python SDK 提供多供应商接口和每次调用成本；开源 Gateway 提供虚拟密钥、预算及限流；Enterprise 增加 SSO、审计日志和更细管理能力。按模型设置虚拟密钥预算等功能在文档中明确标为 Enterprise，不能默认免费可用。[功能分层](https://docs.litellm.ai/docs/enterprise)、[模型预算边界](https://docs.litellm.ai/docs/proxy/users#virtual-key-model-specific)。维护证据为 2026-10-18 的 v1.106.0 发布；主分支版本与正式发布可能不同，不应直接跟随 main 安装。[发布](https://github.com/BerriAI/litellm/releases/tag/v1.106.0)。

最关键的适配成本：官方预算页明确 **“Budgets require a database”**，要求 PostgreSQL；DB-less 部署的全局 max_budget 会 fail-open，不能把“写了一个金额配置”当作付费硬上限。SDK 本身亦有 tokenizers、tiktoken、OpenAI 客户端等一组依赖；完整网关与数据库会增加常驻服务及升级工作量。当前 2GB/500 元约束下暂缓。[预算数据库要求与 fail-open](https://docs.litellm.ai/docs/proxy/users)、[SDK/Proxy 依赖](https://raw.githubusercontent.com/BerriAI/litellm/main/pyproject.toml)。

本项目先把 `backend/app/llm/client.py` 和 `backend/app/research/model_runtime.py` 接到同一轻量调用账本：全局与每用户额度、调用前最坏成本预占、成功后实际 usage 结算、失败/超时未确定费用状态、幂等 request_id、每任务调用上限和人工总开关。可借鉴其“预占再结算”和不可确认额度时拒绝调用的方法，而非复制完整服务。[官方预算预占与 fail-closed](https://docs.litellm.ai/docs/proxy/users#budget-reservation)。

后续真有多供应商需求，可隔离评估 SDK；仍需保留本项目证据契约、脱敏、请求身份、允许模型清单和取消检查。完整 Gateway 也不代替论文证据质量核验或云厂商实际账单对账。

## 引入前应验证的最小业务结果

1. 任务：正常部署、强杀与重启后，任务界面均能给出明确状态；同一任务不会重复写结果或重复扣费；双账号同 ID 不互相执行、取消或读取。
2. 请求准入：限流后能清楚告知何时重试；重启不清空限制；超限请求在解析 PDF 或请求付费模型前被挡住。
3. 统一登录：仅受邀身份可进入，停用后立即失效；身份回调不能越过个人空间边界。
4. 模型预算：缺账本、并发超额或无法确认费用时均不得继续请求；预算能力没有验证前保留多人模式模型关闭。
