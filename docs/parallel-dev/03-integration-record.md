# T0 第二阶段集成记录

## 真实验收接管增量（2026-10-04）

T4/T6 先前任务已结束，本轮由 T0 接管 PlansPanel.tsx、ResearchPrintPage.tsx、research-workspace.css、workspace-panels.test.tsx 和 evaluation/research_atlas 下新增真实验收脚本。原因是实测发现方案刷新选错历史版本、窄屏溢出和打印引用断行；未改公共契约或依赖。新增 frontend/.live-validation.vite.config.ts 为显式 opt-in 本地验收配置，不参与正常启动。

真实浏览器、PDF、隔离图写入查询、GROBID 和离线后端验证通过；真实 Qwen 方法名质量失败。详见 acceptance/T0-live-validation-20261004.md；旧章节中的 NOT RUN 为历史记录，不代表最新状态。

日期：2026-10-04。集成契约：`research-v1.1`。

## 后续平台完善状态

T4 已增加 `user_input` 人工方案 fallback，T1/T6 已补齐失败恢复和发布边界验收。生产方案 provider 仍未授权，生成任务继续明确失败；但用户现在可人工编辑、保存、快照和导出，因此核心代码达到冻结门槛。真实服务、浏览器/PDF 和人类评测仍未完成，不能据此宣称发布 READY。

## 集成前状态

- 未发现 `AGENTS.md`；项目根目录不是 Git 仓库，未初始化 Git、未创建工作树、未提交或重置。
- 已阅读 T1—T6 handoff、T6 pre-integration 报告和验收脚本。
- 对 T1—T5 所属 42 个源码文件连续两次计算 SHA-256，间隔 3 秒，结果稳定；集成开始时没有窗口继续写入。
- T6 初始门禁显示 5 类公共接线缺口；旧报告中的 T5 语义查询失败在接管前的当前源码中已修复并有测试。

## 契约修订

契约从 `research-v1` 同步修订为 `research-v1.1`，没有为错误实现静默放宽：

1. `ComparisonRequest.domain` 改为必需字段。影响：调用方必须显式说明领域；后端校验与项目领域一致，T3 不再从候选内容猜测。
2. 新增 `GraphProjectionStatus` 和快照投影状态/重试 API。影响：前端可区分 pending/running/succeeded/failed，并对失败投影显式重试。
3. 方案生成 provider 未授权时明确失败。影响：生产 API 不把无模型结构化模板返回为异步成功；测试必须显式注入本地 fake。

Python 模型、TypeScript 类型、契约文档和相关测试已同步。

## 公共接线

- `backend/app/db/sqlite.py`：初始化 research 增量 schema；重启中断 research 任务并把运行中投影待办标为失败可重试。
- `backend/app/main.py`：注册项目 router；仅新项目 API 使用统一校验错误，旧路由行为保留。
- `backend/app/jobs.py`：接入 research 任务执行器和持久化失败处理。
- `frontend/src/App.tsx`、`frontend/src/components/Shell.tsx`：接入课题、项目、图和打印路由及导航。
- `.env.example`：补充 `DATA_DIR` 示例；未读取或修改 `.env`。

## 接管记录

确认各责任窗口停止且文件稳定后，T0 为解决跨模块阻断项直接接管以下文件：

- T1：`backend/app/db/projects.py`、`backend/app/research/service.py`、`backend/app/api/projects.py`、`backend/tests/test_research_t1_api.py`、`backend/tests/test_research_t1_storage.py`。修复任务分发预期、显式领域校验、快照投影状态/重试、导出端点误缩进、约束更新的模型/字典类型错误，以及方案 provider 未授权的明确失败。
- T2：新增 `backend/app/research/extraction.py`，只做契约路径适配，不修改抽取算法。
- T3：`backend/app/research/comparison.py`、`backend/tests/test_research_t3_comparison.py`。移除领域猜测，使用请求中的显式领域。
- T4：`frontend/src/api/projects.ts`、`frontend/src/pages/research/ProjectGraph.tsx`、`frontend/src/components/research/ProjectGraphPanel.tsx` 及相关 research 测试。修复图模式/节点参数未发送、投影失败状态和重试入口。
- T6 测试资产：`backend/tests/test_research_acceptance_preintegration.py` 只增加显式 fake 方案 provider，使 mock 属性可审计；未改 T6 报告结论历史。

T5 投影/查询模块未由 T0 改写；T0 只通过 API 和任务编排调用其公开边界。

## 新增集成验证

`backend/tests/test_research_integration.py` 挂载真实 FastAPI app，使用临时 SQLite、mock 模型和 mock 图后端，验证：

- 陌生合成资料无需业务特例即可抽取，且未报告资源保持空值；
- 同一方法的两个实验设置不混合，条件不兼容不排名；
- 人工确认、用户决策、方案编辑保存、快照和 JSON/Markdown 导出；
- 图服务失败不丢快照，状态可查询并可重试；
- 409 不覆盖新版本；被冻结事实变化使引用快照 `needs_review`；
- 新项目校验错误符合统一错误结构。

## 修改文件

- 公共契约/模型：`docs/parallel-dev/00-contract.md`、`backend/app/models/research.py`、`frontend/src/api/project-types.ts`、`backend/app/research/__init__.py`、`backend/tests/test_research_contract.py`。
- 公共集成：`backend/app/main.py`、`backend/app/jobs.py`、`backend/app/db/sqlite.py`、`frontend/src/App.tsx`、`frontend/src/components/Shell.tsx`。
- 接管文件：见“接管记录”。
- 测试：`backend/tests/test_research_integration.py`、相关 T1/T3/T6 测试、`frontend/src/__tests__/research/` 中 fixtures、workspace-panels 和 project-graph 测试。
- 文档/配置：`README.md`、`.env.example`、`docs/research-workspace-release.md`、`docs/research-project-workspace.md`、`docs/parallel-dev/02-integration-checklist.md`、本记录和 T0 handoff。

## 实际测试结果

```text
powershell -ExecutionPolicy Bypass -File evaluation/research_atlas/run_acceptance.ps1
Research 106 passed；全部非 Research 后端 116 passed；打印页 2 passed；静态门禁 11/11

python -m ruff check app tests scripts ../evaluation/research_atlas/evaluate.py ../evaluation/research_atlas/check_release_gate.py
All checks passed!

npm test -- --run
11 test files, 33 tests passed

npm run build
成功，4030 modules transformed
```

## 未验证与发布限制

- 没有调用真实模型、真实 Neo4j 或真实 GROBID；没有下载模型、训练数据或执行论文仓库。
- 没有人工浏览器全流程、窄屏/刷新、真实 PDF 打印版式或公网部署验证。
- 没有真实论文人工 gold、A/B/C 对照、外部用户试用或 GPU 复现。
- 生产方案生成 provider 未授权接入；模型生成能力未验证。人工方案 fallback 已解除 P0 保存/快照/导出阻断，核心代码可冻结，但不标记发布 READY。

## 版本管理与恢复

- `git rev-parse --show-toplevel` 仍返回“not a git repository”；本阶段未初始化 Git 或执行任何 Git 写操作。
- 最终源码恢复包：`.local-backups/research-atlas-source-t0-integration-final-clean-20261004.zip`。
- 清单检查：272 个条目，`BlockedEntryCount=0`；显式排除 `.env`、数据库、`backend/data`、`docs/validation`、T6 `.tmp`、依赖、缓存与构建产物。
- SHA-256 在最终交付回复中记录，避免恢复包文档自引用导致每次归档哈希变化。
- 首次生成的不合格包因含 T6 临时 `data` 目录已在精确路径校验后删除；未删除源码或用户数据。
