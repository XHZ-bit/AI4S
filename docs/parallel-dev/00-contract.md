# Research Atlas 并行开发契约（research-v1.1）

状态：**T0 集成修订后冻结**。初始冻结及 v1.1 修订日期：2026-10-04。公共 JSON 字段以
`backend/app/models/research.py` 与 `frontend/src/api/project-types.ts` 为准；本文说明行为语义。
未经 T0 协调，不得在任务私有文件中复制、改名或放宽公共类型。

## 1. 首版边界

首版完整用户流程：建立课题 → 关联多篇现有论文 → 对每个固定文档版本提取方法、实验设置和测量候选
→ 用户逐字段核对并确认/争议/撤回 → 按可比条件分组比较 → 用户保存路线决策 → 生成、编辑并保存
首轮验证方案 → 创建不可变方案快照 → 导出 Markdown 或 JSON。

P0 必须具备：

1. 课题与约束的乐观并发版本控制；旧版本和旧选择保留。
2. 一个课题关联多篇论文，同一方法允许多个实验设置；设置与测量独立存储。
3. 文本和表格都可产生候选，但表格数值不自动确认；所有字段绑定可定位证据或明确来源。
4. 候选人工确认、争议、撤回与恢复；操作记录操作者、原因、前后版本。
5. 只在数据集、划分、协议、指标范围等条件兼容的组内展示数值比较；不跨组排名。
6. 用户显式保存决策；方案草稿可编辑，保存时创建版本，快照创建后不可变。
7. 字段、证据、文档版本或项目条件变化后，相关已保存方案/快照标记 `needs_review`，不静默重写。
8. 模型不可用时可读全部已保存内容；需要新生成的请求明确失败。

首版不做：自主科研、自动复现、模型训练、自动论文写作、自动采信表格、跨协议排行榜、
多用户权限系统、自动判定科学结论正确、修改/迁移旧学习记录与 Diffusion Policy 案例。
旧 `/api/learning/compare` 继续表示“已核验主张并排查看”，不得复用为本契约的实验条件比较接口。

## 2. 通用传输规则

- 基础路径：`/api/projects`。JSON 使用 `snake_case`，UTF-8，时间使用带时区 ISO 8601 字符串。
- 所有写请求使用显式 `expected_version` 或 `expected_project_version`；版本从 1 开始，只有成功写入才递增。
- 创建方案前的草稿可使用 `version=1`、`id=null`；首次保存请求的 `expected_plan_version=0`。
- 未知字段一律 422；缺失必需字段一律 422；服务端不得忽略多余字段。
- 空值 `null` 表示该字段目前没有值，不等于论文未报告。未报告语义必须由 `finding_status` 表达。
- 新项目异步任务统一使用字符串 ID；旧 `tasks.id` 的整数是旧接口实现细节，不能泄漏到新契约。
- 所有公共响应必须能够被对应 Pydantic 模型校验；接口未接入时返回 501 `not_implemented`，不得返回假 ID、
  空成功对象或预置“完成”结果。

### 错误格式

所有新接口错误统一为：

```json
{
  "detail": {
    "code": "version_conflict",
    "message": "项目已更新，请重新加载",
    "retryable": true,
    "fields": {},
    "current_version": 4,
    "request_id": null
  }
}
```

HTTP 状态：400 请求语义错误；404 资源不存在；409 版本或状态冲突；413 内容过大；422 模型校验失败；
429 队列已满；501 契约存在但功能未实现；503 模型、解析器或图服务不可用。推荐错误码：
`validation_error`、`not_found`、`version_conflict`、`invalid_status_transition`、`incomparable_conditions`、
`model_unavailable`、`parser_unavailable`、`graph_unavailable`、`queue_full`、`not_implemented`。

### 异步任务

`AsyncTask.status` 只能是 `queued | running | succeeded | failed | interrupted`。失败必须携带 `error`，成功才可携带
最终 `result`。进程重启后的排队/运行任务转成 `interrupted`，不得伪装续跑或成功。新生成类操作返回
`202 + AsyncTask`；查询任务不会触发执行。任务重试必须创建新任务 ID 并引用原任务（持久层内部字段由 T1 定义）。

## 3. API 冻结面

以下为 T4 唯一允许访问的业务入口。聚合响应可直接返回列出的公共模型数组；T1 可增加分页包装中的
`items/next_cursor`，但不得改变 item 结构。

| 方法与路径 | 请求 | 成功响应 | 关键失败 |
|---|---|---|---|
| `POST /api/projects` | `ResearchProjectCreate` | 201 `ResearchProject` | 422 |
| `GET /api/projects` | `status? domain? cursor? limit?` | 200 `{items: ResearchProject[], next_cursor: string|null}` | 422 |
| `GET /api/projects/{project_id}` | 无 | 200 `ResearchProject` | 404 |
| `PATCH /api/projects/{project_id}` | `ResearchProjectPatch` | 200 `ResearchProject` | 404, 409, 422 |
| `GET /api/projects/{project_id}/papers` | 无 | 200 `{items: PaperLink[]}` | 404 |
| `POST /api/projects/{project_id}/papers` | `PaperLinkCreate` | 201 `PaperLink` | 404, 409, 422 |
| `PATCH /api/projects/{project_id}/papers/{link_id}` | `PaperLinkPatch` | 200 `PaperLink` | 404, 409, 422 |
| `POST /api/projects/{project_id}/papers/{link_id}/extractions` | `ExtractionStartRequest` | 202 `AsyncTask` | 404, 409, 429, 503 |
| `GET /api/projects/{project_id}/facts` | `kind? status? paper_link_id?` | 200 `{methods, experiment_settings, measurements, evidence}` | 404 |
| `PATCH /api/projects/{project_id}/facts/{fact_id}/status` | `StatusTransitionRequest` | 200 对应事实类型 | 404, 409, 422, 503 |
| `POST /api/projects/{project_id}/comparisons` | `ComparisonRequest` | 200 `ComparisonResult` | 404, 409, 422 |
| `GET /api/projects/{project_id}/decisions` | 无 | 200 `{items: ResearchDecision[]}` | 404 |
| `POST /api/projects/{project_id}/decisions` | `ResearchDecisionCreate` | 201 `ResearchDecision` | 404, 409, 422 |
| `POST /api/projects/{project_id}/plans/generate` | `PlanGenerateRequest` | 202 `AsyncTask` | 404, 409, 429, 503 |
| `GET /api/projects/{project_id}/plans` | 无 | 200 `{items: ValidationPlan[]}` | 404 |
| `PUT /api/projects/{project_id}/plans/{plan_id}` | `PlanSaveRequest` | 200 `ValidationPlan` | 404, 409, 422 |
| `POST /api/projects/{project_id}/snapshots` | `SnapshotCreateRequest` | 201 `ProjectSnapshot` | 404, 409, 422 |
| `GET /api/projects/{project_id}/snapshots` | 无 | 200 `{items: ProjectSnapshot[]}` | 404 |
| `GET /api/projects/{project_id}/snapshots/{snapshot_id}` | 无 | 200 `ProjectSnapshot` | 404 |
| `GET /api/projects/{project_id}/snapshots/{snapshot_id}/export` | `format=markdown|json` | 200 文件流 | 404, 422, 501 |
| `GET /api/projects/{project_id}/snapshots/{snapshot_id}/projection` | 无 | 200 `GraphProjectionStatus` | 404 |
| `POST /api/projects/{project_id}/snapshots/{snapshot_id}/projection/retry` | 无 | 202 `AsyncTask` | 404, 409, 429 |
| `GET /api/projects/tasks/{task_id}` | 无 | 200 `AsyncTask` | 404 |
| `POST /api/projects/tasks/{task_id}/retry` | 无 | 202 新 `AsyncTask` | 404, 409, 429 |
| `GET /api/projects/{project_id}/graph` | `snapshot_id` 必需 | 200 `GraphQueryResult` | 404, 503 |

`POST .../comparisons` 是纯读取/计算，不保存用户选择。只有 `POST .../decisions` 表示用户选定路线。
删除论文关联使用 `PaperLink.status=removed`，不得物理删除历史。方案快照不可 PATCH/DELETE。

## 4. 事实与来源语义

核心结构见公共模型：

- `ResearchProject`：课题、领域、约束和项目版本。
- `PaperLink`：项目到论文的带角色关联；冻结时引用具体文档 ID/版本。
- `MethodCard`：方法定义，不混入某次实验数值。
- `ExperimentSetting`：某方法在具体数据、划分、预处理、超参数、资源和评估协议下的一次设置。
- `Measurement`：只属于一个实验设置；指标名、范围、数值、单位、聚合和不确定性分开。
- `EvidenceRef`：原文/表格/图注/用户注释定位。表格可用 `table_id + row_label + column_label`，不能因定位成功而自动确认。
- `FieldEvidence`：逐字段说明来源和查找结果；同一记录不同字段允许来自不同来源。
- `ResearchDecision`：用户输入来源的路线选择，保存考虑过的候选和理由。
- `ValidationPlan`：可编辑方案内容；`ProjectSnapshot`：冻结后的不可变交付对象。

`source_kind` 必须区分：

- `literature_report`：论文或其固定文档版本中报告的内容；不表示结论正确。
- `user_input`：用户填写、修正或选择；不得改写成论文声称。
- `model_suggestion`：模型归纳或建议；没有人工确认前仍是候选，模型不能成为论文事实的来源。

`finding_status` 与审核状态正交：

- `unknown`：尚未判断；
- `not_found`：已在当前冻结范围查找但未找到；
- `not_parsed`：源内容存在或可能存在，但当前解析能力未覆盖；
- `conflicting`：来源之间有冲突，必须有 `conflict_group_id`；
- `reported`：来源确实报告了该值，仅说明可追溯。

记录状态及允许转换：

```text
candidate -> user_confirmed | disputed | withdrawn
user_confirmed -> disputed | withdrawn
disputed -> user_confirmed | withdrawn
withdrawn -> candidate
```

恢复到 `candidate` 后必须重新人工确认。任何转换都要校验 `expected_version`、记录操作者和原因，并新增审计事件。
事实内容修改不原地覆盖历史；创建新版本，旧版本仍可被旧快照引用。

## 5. 比较规则与领域配置

T3 必须先按领域配置生成条件签名，再形成 `ComparisonGroup`。字段缺失不会自动推断相等；缺失关键条件的候选
可以展示，但组标记 `comparable=false` 并列出原因。禁止只按方法名或指标名排序。

### 图像异常检测 `image-anomaly-v1`

比较维度：数据集及版本、类别/缺陷范围、监督设定、训练制度、图像分辨率、预处理、图像级/像素级得分范围、
阈值选择、划分、评估协议。常见指标：image AUROC、pixel AUROC、AP、AUPRO，范围必须保留，不能混为同一列。

### 时间序列预测 `time-series-forecasting-v1`

比较维度：数据集及版本、目标变量、预测窗口、上下文长度、频率、划分、协变量、缩放、滚动/静态评估协议。
常见指标：MAE、RMSE、MAPE、sMAPE、MASE。预测窗口、频率、划分或目标范围不同不能直接排名；百分比指标在
零值处理未知时必须标记不可比。

完整机器可读配置由两端 `DOMAIN_PROFILES` 常量冻结。

## 6. 快照、失效与复核

保存决策必须冻结：项目版本、约束版本、选中方法 ID+版本、实验设置 ID+版本、被决策引用的测量/证据 ID、
用户理由。创建方案快照还必须冻结：领域配置版本、所有关联论文的 `paper_uid/document_id/document_version/content_hash`、
方案版本、决策 ID+版本，以及方案实际使用的全部事实 ID+版本。

下列事件只标记 `review_status=needs_review` 和原因，不修改快照内容：

1. 被引用事实产生新版本或状态变为 `disputed/withdrawn`；
2. 被引用证据撤回、冲突状态改变或对应文档被新版本替代；
3. 项目约束、研究问题或领域配置版本变化；
4. 决策被取代/撤回；
5. 方案引用的论文关联被移除。

旧快照永远可读、可导出；复核后创建新方案版本和新快照，不能把旧快照改回 `current` 来掩盖差异。

## 7. SQLite 与 Neo4j 边界

SQLite 是业务事实真源，保存项目、论文关联、文档版本引用、证据、字段绑定、事实各版本、审计、决策、方案、
不可变快照、任务与待复核原因。所有这些业务写入只由 T1 执行。

Neo4j 是可重建的查询投影：T5 只接收完整 `ProjectSnapshot` 构建 `GraphProjection`，边必须携带 `fact_ids[]` 与
`evidence_ids[]`，不得沿用旧关系上的单一 `knowledge_id/passage_id` 作为新项目事实模型。Neo4j 不分配业务 ID、
不决定状态、不反写 SQLite。图服务失败不回滚已经提交的 SQLite 事实；任务明确失败，稍后按同一快照幂等重建。

## 8. 模块函数边界与调用方向

签名中的类型均来自 `app.models.research`。

### T1：存储与业务编排

```python
create_project(conn, request: ResearchProjectCreate) -> ResearchProject
update_project(conn, project_id: str, request: ResearchProjectPatch) -> ResearchProject
link_paper(conn, project_id: str, expected_project_version: int, request: PaperLinkCreate) -> PaperLink
save_candidate_bundle(conn, bundle: CandidateBundle) -> CandidateBundle
transition_fact(conn, project_id: str, fact_id: str, request: StatusTransitionRequest) -> MethodCard | ExperimentSetting | Measurement
save_decision(conn, project_id: str, request: ResearchDecisionCreate) -> ResearchDecision
save_plan(conn, project_id: str, request: PlanSaveRequest) -> ValidationPlan
save_snapshot(conn, snapshot: ProjectSnapshot) -> ProjectSnapshot
mark_dependent_snapshots_for_review(conn, changed_refs: list[VersionRef], reasons: list[str]) -> int
```

T1 是所有业务 SQLite 写入和事务边界；可调用 T2/T3/T5，不允许后者直接写业务表。

### T2：结构化候选

```python
extract_candidates(input: ExtractionInput) -> CandidateBundle
```

输入只含固定文档版本及 passages；输出候选、逐字段来源与 warnings。不得打开业务数据库、确认候选或投影图。

### T3：比较、决策校验与方案组装

```python
compare_conditions(request: ComparisonRequest, facts: CandidateBundle) -> ComparisonResult
validate_decision(request: DecisionValidationRequest) -> DecisionValidationResult
build_plan_draft(input: PlanBuildInput) -> ValidationPlan
build_snapshot_content(input: SnapshotBuildInput) -> ProjectSnapshot
```

这些函数不写数据库。生成失败抛出明确异常，由 T1/API 转成统一错误；不得返回预置成功方案。

### T4：前端

只通过第 3 节 API 访问业务数据；不得直接依赖旧学习工作区内部结构，也不得在浏览器中自行更改版本或审核状态。
前端保留并展示来源标签、未知/未解析/冲突状态、不可比原因和 `needs_review`。

### T5：图投影

```python
build_graph_projection(snapshot: ProjectSnapshot) -> GraphProjection
project_graph(projection: GraphProjection) -> GraphProjectionResult
query_project_graph(query: GraphQuery) -> GraphQueryResult
```

调用方向固定为 API → T1；T1 → T2/T3；成功保存快照后 T1 排队调用 T5。T4 → HTTP API。
T2/T3/T5 之间不得互调，任何模块不得反向调用 T4。

## 9. v1.1 集成修订记录

T0 在第二阶段根据 T3、T4、T5、T6 的正式 handoff 做两项同步修订：

1. `ComparisonRequest.domain` 改为必需字段。调用方必须使用当前 `ResearchProject.domain`，服务端校验两者一致；
   T3 不再根据指标名猜领域。影响 Python/TypeScript 模型、T1 编排、T3 比较、T4 请求和相关测试。
2. 新增 `GraphProjectionStatus` 及投影状态/重试端点。保存快照后自动排队投影；失败保留 SQLite 快照，用户可按
   snapshot 明确查看状态并创建新的重试任务。影响 Python/TypeScript 模型、T1 API/service、T4 API 和测试。

契约版本从 `research-v1` 提升为 `research-v1.1`。首阶段没有生产项目数据，因此不执行数据迁移；所有新持久化
对象写入 v1.1。旧阶段文档和测试夹具同步更新，不提供把 v1 对象伪装为 v1.1 的静默转换。

## 10. 兼容与未实现行为

### 2026-10-04 比赛增强接线补充（wire schema 仍为 v1.1）

- 新增 T0 内部 `structured_chat(messages, *, schema, prompt_version, schema_version) -> str`、
  `suggest_plan(input: PlanBuildInput) -> dict` 与 `validate_suggestions(payload, input) -> dict`。
  T1 调用 provider，T2 只调用无数据库运行适配层；业务写入仍集中在 T1。
- 生产 `build_plan` 先校验路线，再调用并严格校验 provider，再由 T3 组装草稿。
  provider 异常、空步骤、非法 Schema 或被拒绝步骤必须失败，不把 T3 纯函数的离线模板当生产生成成功。
  T3 单独调用 `build_plan_draft` 的模板能力保持不变，人工方案 API 保持不变。
- Research 外部模型默认关闭，需 `RESEARCH_MODEL_ENABLED=true`。不更改旧学习模块调用行为。
  每个后台任务使用独立调用预算，不自动重试；配置和外发范围见 README。
- 任务沿用 `failed` + `ErrorDetail`，增加实际错误 code：`model_not_authorized`、`model_not_configured`、
  `model_input_budget_exceeded`、`model_request_budget_exceeded`、`model_timeout`、`model_http_error`、
  `model_connection_failed`、`model_invalid_response`、`model_incomplete_response`、`model_empty_response`、
  `model_response_too_large`、`model_invalid_plan_json`、`model_invalid_plan_schema`、
  `model_unsafe_or_ungrounded_plan`、`model_provider_failed`。code 本来即为字符串；Python/TS wire 类型无需变更。
- 成功方案标题标明“模型建议·待人工确认”，不能标成结构化离线模板或已实测结果。
  私有抽取提示词升级至 v2（缓存版本随之变化），正文与定位元数据分离；公共事实结构不变。
- 原始来源定位不证明名称边界或科学正确性。保守名称拒收、词面检查均需真实论文评测；不宣称幻觉已消除。

以下为首阶段的历史说明，不覆盖以上补充及最新集成清单：

旧论文、学习记录、路线、案例和 `/api/learning/*` 保持原样；新项目通过新表和新路由增量接入。
本阶段没有注册 `/api/projects` 路由、没有数据库迁移、没有任务类型实现。调用任何尚未接入的接口时必须得到 404
（路由尚未注册）或接入后的 501 `not_implemented`，绝不能伪造 2xx。**契约 READY 不等于业务功能完成。**
