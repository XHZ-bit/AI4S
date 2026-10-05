# Research Atlas 集成检查清单

更新时间：2026-10-04。契约版本：`research-v1.1`。任何单项“通过”都必须有实际命令或人工步骤记录；mock 不得标记为真实服务验证。A—D 保留冻结时的门槛定义，实际集成结果与发布判断见 E—G。

## 最新复核：工作区清理与架构修复（2026-10-04）

- [x] 模型建议纯校验抽离，共用 Schema/证据校验，provider 不依赖 planning 私有实现；公共契约保持不变。
- [x] 畸形模型 choices/message、非法证据数组、default 字段名回归；比较选择/版本变化与图谱迟到响应回归。
- [x] 后端全量 264 passed；前端 41 passed；Ruff、TypeScript/Vite 构建通过。具体命令与首次失败记录见 T0 handoff。
- [x] 78 个缓存/临时数据/旧草稿目标已删除，4 份草稿归档并校验；再次预览无目标。
- [x] 当前设计、验收/交接记录、源码备份、用户数据和旧案例保留；没有生产数据库升级、全局环境安装或 Git 初始化。
- [ ] 本轮真实浏览器、真实模型和外部服务未复跑；不提升此前发布就绪等级，不宣称全部缺陷已解决。

## A. 契约门槛

- [x] `research-v1.1` Python/TypeScript 公共字段、枚举、可空性和版本语义已同步冻结。
- [x] 来源、查找状态、审核状态三组概念彼此独立。
- [x] 方法、实验设置、测量与字段证据分离。
- [x] 两个领域配置及不可比规则冻结。
- [x] API、错误、异步任务、409 乐观锁和 501 未实现行为明确。
- [x] SQLite 真源与 Neo4j 可重建投影边界明确。
- [x] 决策和方案快照的冻结引用、失效触发器明确。
- [x] T1—T5 已完成公共接线；契约通过不单独代表真实服务或完整业务发布完成。

## B. 各任务交付进入集成前门槛（历史验收模板）

### T1

- [ ] 新表只做增量迁移，旧 papers/documents/knowledge/workspaces/roadmaps/cases 不删除、不重写。
- [ ] 所有业务写入在显式事务中完成，失败不产生半成品。
- [ ] 版本冲突返回 409 和 `current_version`；状态非法返回 409/422，不覆盖新版本。
- [ ] 事实修改保留旧版本和审计；论文关联使用软移除。
- [ ] 快照不可变，依赖变化只追加 `needs_review` 原因。
- [ ] API 返回值逐项通过公共 Pydantic 模型。
- [ ] 未实现分支返回 501，不返回假成功。

### T2

- [ ] 纯函数只接收 `ExtractionInput`，不连接 SQLite/Neo4j。
- [ ] 文本与表格候选分别保留定位；表格数值仍为 `candidate`。
- [ ] 每个有值字段有 `FieldEvidence`；缺失使用准确 `FindingStatus`。
- [ ] 文献报告、用户输入、模型建议没有混写。
- [ ] 模型不可用或输出不合法时明确失败；无预置成功候选。
- [ ] 固定输入得到结构稳定、可序列化的 `CandidateBundle`。

### T3

- [ ] 先比条件再比指标；不同数据集/划分/协议/范围不进入同一可比组。
- [ ] 未知关键条件导致 `comparable=false`，不猜测。
- [ ] 决策只接受存在且未撤回的事实，记录所有引用版本。
- [ ] 方案把假设、未知、步骤、验收指标和风险分开。
- [ ] 快照内容包含全部冻结文档、事实、约束、领域配置和决策版本。
- [ ] 纯函数无业务数据库写入。

### T4

- [ ] 只通过 `frontend/src/api/projects.ts` 调用新接口。
- [ ] 页面完整展示来源标签、候选/确认/争议/撤回、未知/未找到/未解析/冲突。
- [ ] 不可比原因可见，界面不生成跨组排名。
- [ ] 409 提示刷新/合并，不静默重试覆盖。
- [ ] 模型不可用时已保存数据仍可浏览；生成失败明确可见。
- [ ] 草稿与已保存快照区分；`needs_review` 和原因可见。
- [ ] 窄屏、刷新恢复、重复点击和异步轮询停止条件覆盖测试。

### T5

- [ ] 只投影指定 `ProjectSnapshot`，节点/边保存 snapshot 版本。
- [ ] 每条事实边支持多个 `fact_ids` 和 `evidence_ids`。
- [ ] 重放相同快照幂等；能从 SQLite 快照完全重建。
- [ ] 查询始终限定 project + snapshot，不混入当前或旧快照。
- [ ] Neo4j 不可用时明确失败，不影响 SQLite 已保存快照。

### T6

- [ ] 覆盖建立课题到导出快照的主流程与失败流程。
- [ ] 使用独立临时 SQLite、模拟模型、模拟图服务，不访问真实用户数据。
- [ ] 覆盖并发冲突、任务中断、模型不可用、解析缺口、不可比、证据撤回和约束变化。
- [ ] 真实部署/模型/GROBID/Neo4j/用户试用分别列为未验证或提供真实记录。

## C. T0 集成顺序（已执行）

1. 阅读各 handoff，拒绝公共契约漂移和越权文件改动。
2. 先接 T1 增量 schema 与 API，再接 T2/T3 纯函数，最后接 T5 投影任务。
3. 在 `backend/app/main.py` 注册项目路由；在 `backend/app/jobs.py` 注册真实处理器，未知类型继续明确失败。
4. 接 T4 路由与 Shell；不改旧论文、学习、路线和案例入口。
5. 运行公共契约测试、各任务定向测试、后端全量、ruff、前端测试与 build。
6. 使用全新临时数据目录执行 mock 端到端；验证失败路径没有假成功。
7. 在隔离部署环境分别验证 SQLite 迁移、Neo4j 重建、GROBID 和模型不可用降级。
8. 更新 T0 handoff，只有全部 P0 验收后才声明“核心功能 READY”。

## D. 最低回归命令

```powershell
cd backend
python -m pytest -q tests/test_research_contract.py --basetemp=.pytest_tmp_contract
python -m pytest -q --basetemp=.pytest_tmp_research
python -m ruff check app tests scripts
cd ../frontend
npm test
npm run build
```

测试产生的临时数据库不得指向生产 `DATA_DIR`，不得启动真实模型调用、下载权重或执行论文仓库命令。

## E. 实际公共接线状态

- [x] research schema 随 SQLite 初始化增量创建；旧表不删除、不重写。
- [x] `/api/projects` router、research 异步任务、重启中断处理已注册，旧 API 保留。
- [x] T2 契约路径适配器 `app.research.extraction` 已提供。
- [x] 比较请求显式携带 `domain`，服务端校验项目领域，不从内容猜测。
- [x] `/research`、项目页、图页、打印页和 Shell 导航进入生产构建。
- [x] 快照创建后排入图投影；失败保留 SQLite 快照并提供状态与重试 API。
- [x] JSON/Markdown 导出返回真实不可变快照，冻结文档哈希和事实版本可追踪。
- [x] 事实状态变化可把引用它的快照标记为 `needs_review`，不改写旧快照。
- [x] 生产代码扫描未发现 mock、预置论文名或硬编码候选答案。
- [x] 方案生成 provider 未授权时明确失败；不把 T3 结构化模板伪装成 API 任务成功。
- [x] 无 provider 时可创建 `source_kind=user_input` 人工空白草稿，经现有 API 保存、创建快照和导出；不会预填科学结论。

## F. 实际验证结果

```text
root: powershell -ExecutionPolicy Bypass -File evaluation/research_atlas/run_acceptance.ps1
结果：Research 108 passed；全部非 Research 后端回归 116 passed；打印页 2 passed；静态门禁 11/11

backend: python -m ruff check app tests scripts ../evaluation/research_atlas/evaluate.py ../evaluation/research_atlas/check_release_gate.py
结果：All checks passed!

frontend: npm test -- --run
结果：11 files, 33 tests passed

frontend: npm run build
结果：成功，4030 modules transformed

```

`backend/tests/test_research_integration.py` 使用临时 SQLite、mock 模型和 mock 图服务，完成建立课题、关联陌生合成资料、候选抽取、人工确认、条件比较、人工决策、mock 方案生成、编辑保存、快照、JSON/Markdown 导出、历史依据、图失败保留与重试、409、依赖变化待复核。它不是实时外部服务或浏览器端到端验证。

## G. 发布判断

公共接线、契约、人工方案 fallback、模块组合、全部旧后端回归、前端全量与生产构建通过。**截至 2026-10-04，核心开发达到可冻结标准**：外部方案 provider 不可用时生成任务明确失败，用户仍可通过人工输入完成方案编辑、保存、快照和导出。

这不等于发布 READY。尚未验证：真实模型、真实 Neo4j、真实 GROBID、断网部署、人工浏览器窄屏/刷新、真实“打印为 PDF”版式、真实论文标注、A/B/C 任务对照和外部用户试用。接入外部方案模型前仍必须确定允许发送的字段、服务、日志脱敏和数据保留规则。

## H. 2026-10-04 下一步计划实测增量

- [x] 新增可重复的隔离浏览器 fixture；脚本拒绝 `backend/data` 和非空输出目录，清单明确 `scientific_result=false`、`external_calls_made=false`。
- [x] 使用真实 Chrome headless 渲染项目页与打印页，生成 2 页 PDF；视觉未见遮挡或实验设置混排。
- [x] 后端进程停止并从同一临时 SQLite 重启后，原快照、1 个冻结文档、4 个冻结事实与 `user_input` 方案仍可读取和 JSON 导出。
- [x] 只读确认本机 Neo4j 容器健康、GROBID `/isalive` 为真；没有读取凭据、没有图写入、没有上传 PDF、没有操作数据卷。
- [x] 报告/PPT/视频/演示/许可工作已经形成可执行材料计划，没有自动公开或提交。
- [ ] CUA 因 Windows deny-read ACL 初始化失败，交互式浏览器编辑、窄屏、刷新恢复尚未实测。
- [ ] PDF 视觉通过，但 Chrome 文本层有少量 CJK 兼容部首映射和长标识符内插空格；目标演示机全文检索/无障碍复核未完成。
- [ ] Neo4j 认证写入/查询、GROBID 真实 PDF 解析、真实模型、断网部署和外部用户试用仍未执行。

前端全量第一次并发于生产构建运行时出现 1 个用例超时；串行复现确认是测试在完整 Ant Design DOM 上重复做可访问名称扫描的性能热点，不是保存业务死锁。T0 明确接管 T4 测试文件后改为定位同一按钮的唯一可见文本，未延长超时、未改业务逻辑或契约；最终串行全量为 11 files / 33 tests passed。接管记录见 T4 handoff。

详细记录：`acceptance/T0-browser-pdf-validation.md`、`acceptance/local-service-validation.md`、`acceptance/browser-validation-protocol.md`、`acceptance/release-materials-plan.md`。

## I. 真实验证更新（以本节覆盖此前 NOT RUN，2026-10-04）

- [x] Chrome 点击/键盘编辑/保存/刷新恢复；修复保存后刷新选错方案。
- [x] 390px 无溢出；真实浏览器 offline 保存失败保留草稿、重连刷新恢复。
- [x] PDF 字体就绪后打印，渲染检查与双引擎原样 ID/CJK 检查通过。
- [x] 独立 Neo4j 认证、投影幂等、三类查询、项目隔离、历史版本。
- [x] GROBID 两页合成 PDF 解析，6 个正文片段，未报告信息保留。
- [x] Docker --network none 后端启动、快照读取/JSON 导出、图失败后数据保留。
- [x] Qwen 真实调用 3 次，服务可达；不代表生产方案 provider 已接入。
- [ ] Qwen 方法名质量失败：资料声明被并入方法名，不能标记抽取验收通过。
- [ ] Windows 原生 CUA 仍因沙箱 ACL 初始化失败；交互由真实 Chrome/Playwright 完成。

前端全量 34/34、定向 10/10、生产构建和脚本 Ruff 通过。详细记录：`acceptance/T0-live-validation-20261004.md`。仍不是完整发布 READY。

## J. 比赛增强第一批（2026-10-04，覆盖旧 provider 未实现描述）

- [x] 生产方案 provider 已实现并接入，默认 `RESEARCH_MODEL_ENABLED=false`；未自动启用外发。
- [x] 抽取与方案使用有请求预算、输入/输出限制、无自动付费重试的适配层；可显式选 JSON Schema。
- [x] 生产生成失败、空响应、非法 Schema 与被拒绝步骤不会被模板 fallback 伪装成成功。
- [x] 正文/定位元数据分离、明显跨句方法名拒收；仍需人工确认，未宣称科学质量通过。
- [x] 流程下一步说明、README 配置与官方材料尺寸要求同步；旧人工方案路径保留。
- [x] 最终后端 245 passed；前端 35 passed；TypeScript/Vite 构建、Ruff、静态接线 11/11 通过。
- [ ] 新接线后的真实模型抽取与方案生成质量验证（需预算及外发范围审批）。
- [ ] 人工事实字段修订/表格补录的新 API 与 UI、统一约束判定和完整冻结图内容扩展。
- [ ] 100 字段人工核验、独立留出、效果对照、三位目标用户试用。
- [ ] 依赖版本锁定、全量许可审核、项目 LICENSE 审批与评审期成果链接。
- [ ] 赛后多模态、持久化 Agent 工作流、观测、MCP、团队权限。

本批不改公共 wire 类型、不迁移生产数据、不下载资源、不公开或提交材料。
当前是“第一批工程增强测试通过”，不是比赛发布 READY；命令、接管和剩余返工入口见 T0 handoff 最新增量。
