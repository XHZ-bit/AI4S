# 账号与源代码交付核查 · 2026-10-29

本核查只验证工程状态，不代替AIC官方规则逐条比对。没有修改正在使用的账号、论文库、研究空间或服务运行模式，没有真实发信或模型请求。

## 结论

账号系统已经是实际服务，不是仅有页面的demo。当前服务采用 `ACCESS_MODE=local`，因此可以匿名使用本机工作空间；注册登录后进入 `users/<账号ID>/` 独立资料库。现有匿名本机资料继续保留，不会自动复制到新账号。

`multiuser` 是另一部署配置，必须先登录，并强制关闭尚无多用户费用配额的统一付费模型。不能为了展示登录，直接把日常数据环境切到multiuser并假定原资料与AI能力会自动迁移。

只读查询当前 `/api/auth/session` 的结果：本机模式，注册已开放，真实邮件找回未启用。未读取或展示任何用户密码、会话令牌、SMTP凭据和API密钥。

## 能力与验证边界

| 流程 | 当前状态 | 验证与限制 |
| --- | --- | --- |
| 注册、密码登录、退出 | 已实现 | 服务端密码哈希及持久会话；本机可选账号，多人配置强制登录 |
| 密码与会话安全 | 已实现 | 随机盐scrypt；Cookie HttpOnly/SameSite；令牌哈希存储、到期和撤销；写请求CSRF与Origin校验 |
| 个人资料、项目、文件隔离 | 已实现且隔离验证 | 不同账号使用独立SQLite与文件目录；跨账号访问已知项目/知识/源文件返回404，多人匿名访问返回401 |
| 邮箱验证与邮件找回 | 代码及模拟流程已实现，当前未部署 | SMTP及公开站点地址未配置；不能声称公网邮件已经可投递 |
| 一次性恢复码、密码修改、会话撤销 | 已实现 | 验证使用合成账号及模拟邮件，不触及日常账号 |
| 空间知识图谱 | SQLite按账号隔离 | 旧共享Neo4j接口仍在multiuser中关闭；不能用其状态推断新空间图谱不存在 |
| 多用户统一AI调用 | 尚未开放 | 缺少完整的账号费用配额与运营控制，现有multiuser策略保持关闭，不绕过安全边界 |
| 全类型资料存储配额 | 部分实现 | PDF页数/大小/份数配额已有；DOCX、代码等知识资产的跨文件总空间仍需统一接入 |
| 公开部署 | 未验证完成 | 未执行公网HTTPS、真实邮件商、反向代理真实IP、负载与运营告警验收 |

本轮账号前端20项测试通过，日志 `.tmp/aic-auth-frontend-tests.log`。账号、恢复、多人隔离及工作上下文广泛回归72项通过（1085.36秒），日志 `.tmp/aic-auth-backend-tests.log`。新增空间图谱／源文件／学习内容账号隔离，以及受控多人关闭付费服务与远程导入边界2项针对性检查通过，日志 `.tmp/aic-boundary-final-tests.log`；这些检查与广泛回归存在覆盖重叠，不相加宣称独立样本量。

额外执行全新临时目录的真实HTTP烟检：实际注册两个合成账号、登录会话、CSRF拒绝、项目隔离、退出后无权访问原账号项目、正确密码重新登录恢复私有项目及Cookie标志均通过。脚本不是mock登录响应，结果见 `.tmp/aic-account-smoke-result.json`。该烟检不启动应用lifespan后台服务，不验证公网浏览器或真实SMTP；未向正在使用的生产账号库注册用户。

本机启动前检查 `.\start.ps1 -Mode Local -Check` 返回成功，明确使用项目虚拟环境、原数据目录和8000/5173端口，日志 `.tmp/aic-local-start-check.log`。这项只检查本机现有依赖与启动配置，不等同于全新机器安装验收。

## 本轮已修复

1. 新统一资料的远程链接入口 `/api/projects/{id}/sources/link` 现在纳入受控多人禁止远程采集的边界；本机模式不受影响。此前它可能绕过旧paper采集入口的关闭策略。
2. 修正 `docs/multiuser-trial.md` 中“注册与邮件恢复尚未实现”等过时描述，明确本机可选账户、受控多人限制及SQLite图谱的区别。
3. 源包工具在文件存在时收录顶层LICENSE、NOTICE、第三方清单与DESIGN，新增 `--require-license` 最终交付门槛。该检查只检查声明文件存在，不替权利人选择许可，也不证明依赖兼容。
4. 源包整体排除生成的Pyodide运行时，避免仅打入JS/JSON而漏WASM/标准库zip。前端 `prebuild` 从锁定npm依赖恢复完整运行时，与PDF.js生成资源一致。打包三项隔离检查通过，日志 `.tmp/aic-release-tests.log`。

## 开源交付前必须明确

- 当前没有顶层自研LICENSE；须由权利人决定并确认适用范围，不能把“代码可查看”写成“已有明确开源授权”。
- [第三方清单](../../THIRD_PARTY_NOTICES.md)记录主要直接依赖及解析模型许可，[环境索引](aic-dependency-licenses-2026-10-29.json)记录当前版本与上游许可文件位置。这不是完整传递依赖SBOM或许可兼容性结论。
- PyMuPDF官方提供GNU AGPL与商业许可两条路径，具体见[官方文档](https://pymupdf.readthedocs.io/en/latest/about.html)。自研许可证与对外分发方案必须同时核对该依赖，不能将整个平台直接概称为MIT。
- Docling代码使用MIT，模型权重另有CDLA-Permissive或Apache条款。源包不含权重；当前安装器记录已下载文件哈希，但上游模型尚未全部固定到不可变提交。
- 论文、研究报告、仓库快照和模型API服务的使用／再分发权限应分别声明。提交源包不包含日常数据库、私有报告、论文PDF和真实凭据。

## 可复验步骤

```powershell
# 合成账号与全新临时数据目录，不启动/停止日常服务，不发邮件或模型请求
backend\.venv\Scripts\python.exe evaluation\research_atlas\check_account_submission.py

# 隔离测试；tests/conftest.py强制临时DATA_DIR及外部HTTP模拟
Push-Location backend
.venv\Scripts\python.exe -m pytest tests/test_accounts.py tests/test_account_recovery.py tests/test_multiuser_isolation.py tests/test_work_context.py -q
.venv\Scripts\python.exe -m pytest tests/test_source_delivery.py -q
Pop-Location

# 声明文件经权利人确认、全部开发完成后再生成最终源包；输出新文件名
backend\.venv\Scripts\python.exe scripts\package_release.py --version aic-final-20261030 --require-license --output .releases\aic-final-20261030.zip
```

审计中已生成 `.releases/audit-auth-20261029.zip`，CRC和逐文件SHA-256回读通过。它生成于并行开发过程中，仅用于检查打包机制，不能代替开发完成后的最终提交包。尚未声称在一台全新机器完成全部依赖下载、模型下载及系统安装验收。
