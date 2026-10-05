# Research Atlas 并行开发文件归属

本表自 2026-10-04 起生效。共享目录不等于共享写权限；未列出的跨任务修改先写入各自 handoff，由 T0 集成。
其他窗口已产生的文件不是脏数据，不得清理、覆盖或回滚。

## T0：架构、公共契约与集成

独占：

- `docs/parallel-dev/00-contract.md`
- `docs/parallel-dev/01-ownership.md`
- `docs/parallel-dev/02-integration-checklist.md`
- `docs/parallel-dev/handoffs/T0.md`
- `backend/app/models/research.py`
- `frontend/src/api/project-types.ts`
- `backend/app/main.py`
- `backend/app/jobs.py`
- `backend/app/db/sqlite.py`
- `backend/app/config.py`
- `backend/app/research/__init__.py`
- `backend/tests/conftest.py`
- `frontend/src/App.tsx`
- `frontend/src/components/Shell.tsx`
- `frontend/src/api/client.ts`
- 所有依赖清单、锁文件、构建配置、启动脚本、Docker 配置和根 `README.md`
- 公共类型独立测试：`backend/tests/test_research_contract.py`

T0 第一阶段只冻结契约和公共类型，不预接入未完成业务模块。后续集中处理路由注册、迁移入口、任务分发、
前端导航和最终回归。

## T1：存储与业务编排

- `backend/app/db/projects.py`
- `backend/app/api/projects.py`
- `backend/app/research/service.py`
- `backend/tests/test_research_t1_*.py`
- `docs/parallel-dev/handoffs/T1.md`

T1 独占所有新业务 SQLite 写入和事务。不得修改公共模型；发现缺口写 handoff，给出所需字段、类型及理由。

## T2：候选抽取

- `backend/app/research/extraction.py`
- `backend/app/research/extraction_prompts.py`
- `backend/tests/test_research_t2_*.py`
- `backend/tests/fixtures/research_t2/`
- `docs/parallel-dev/handoffs/T2.md`

T2 从固定原文片段返回 `CandidateBundle`，不连接业务数据库、不确认候选、不把表格数值自动标成可信。

## T3：比较、决策校验与方案内容

- `backend/app/research/comparison.py`
- `backend/app/research/decisions.py`
- `backend/app/research/planning.py`
- `backend/app/research/domain_profiles/`
- `backend/tests/test_research_t3_*.py`
- `backend/tests/fixtures/research_t3/`
- `docs/parallel-dev/handoffs/T3.md`

T3 只做纯计算和内容组装，不写数据库、不调用图服务、不改变公共类型。

## T4：项目工作台前端

- `frontend/src/pages/research/`
- `frontend/src/components/research/`
- `frontend/src/api/projects.ts`
- `frontend/src/__tests__/research/`
- `docs/parallel-dev/handoffs/T4.md`

T4 只经冻结 API 访问业务数据。路由和 Shell 接入申请由 handoff 交 T0。

## T5：知识图谱投影与查询

- `backend/app/research/graph_projection.py`
- `backend/app/research/graph_queries.py`
- `backend/tests/test_research_t5_*.py`
- `docs/parallel-dev/handoffs/T5.md`

T5 只从 `ProjectSnapshot` 生成可重建的 Neo4j 投影。不得把 Neo4j 当业务真源，不写业务 SQLite。

## T6：验收与评估

- `backend/tests/test_research_acceptance_*.py`
- `evaluation/research_atlas/`
- `docs/parallel-dev/acceptance/`
- `docs/parallel-dev/handoffs/T6.md`

T6 使用临时数据库和模拟外部服务；不得把 mock 测试描述为真实端到端验证。

## 跨任务规则

### 2026-10-04 清理与架构修复接管

按用户明确要求清理冗余/草稿并修复代码；再次读取窗口状态，T1—T6 均未活动，沿用其 completed 交接。
本轮 T0 接管 `backend/app/research/planning.py`、`frontend/src/components/research/ComparisonPanel.tsx`、
`frontend/src/components/research/ProjectGraphPanel.tsx`；原 T0 provider/runtime 继续维护。
新增 T0 所有文件：`backend/app/research/suggestion_validation.py`、`scripts/clean-workspace.ps1`、
`backend/tests/test_research_cleanup_regression.py`、`frontend/src/__tests__/research/stale-state.test.tsx`。
`docs/superpowers/plans/` 下四份 2026-09-21 阶段草稿先归档校验再删除；设计 specs、验收记录、
所有 handoff、现有备份、原始资料、生产数据库、依赖和 Docker 卷均保留。
可再生 pytest 临时目录、Python/Ruff 缓存与 tsbuildinfo 通过限定路径的清理脚本处理；不读取其数据库内容。

### 2026-10-04 比赛增强版集成接管

T0 已通过任务状态读取确认 T1—T6 最近一轮均 completed，未发现其他 AI4S 活跃写入窗口。
本轮不派发新窗口。为执行获批比赛增强计划，T0 明确接管：
`backend/app/research/service.py`、`backend/app/research_extraction/candidates.py`、
`backend/app/research_extraction/prompts.py`、`frontend/src/pages/research/ResearchProjectPage.tsx`。
不修改其他任务 handoff，不修改 T3 纯函数的模板模式契约。
新增集成文件 `backend/app/research/model_runtime.py`、`backend/app/research/plan_provider.py`、
`backend/tests/test_research_t0_enhancement.py` 和前端 `research/next-step.test.tsx` 由 T0 本轮拥有。
材料规范更新接管 `docs/parallel-dev/acceptance/release-materials-plan.md`。
静态接线标记随实现同步：接管 `evaluation/research_atlas/check_release_gate.py`；
只更新已变更的 provider 接线标记，不放宽真实验收门槛。
配套回归接管 `backend/tests/test_research_extraction.py`、`backend/tests/test_research_t1_storage.py`、
`backend/tests/test_research_integration.py`、`backend/tests/test_research_acceptance_preintegration.py`：
仅将旧的“空模型响应即成功”夹具换为有证据的合成步骤，及同步私有提示词元数据路径。
具体改动、验证与剩余返工项写入 T0 handoff，其他范围维持原归属。

1. 公共类型、公共接口、错误码和路径只有 T0 可改。
2. 跨任务需要变更时，在自己的 handoff 写“当前行为、阻塞原因、精确修改建议、兼容影响、建议测试”。
3. 任务文件可导入公共模型，不得复制一份近似模型来绕过契约。
4. T1 接收 T2/T3 纯函数输出并负责持久化；T5 接收已保存快照；T4 只调用 HTTP。
5. 不读取或输出 `.env`；不接触用户数据库和 Docker 数据卷；测试只用独立临时目录。
6. 不初始化 Git、不创建工作树、不提交、不重置；恢复副本由 T0 统一维护。
