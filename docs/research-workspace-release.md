# 科研学习工作台：实现与验收说明

本版本保留单机 React / FastAPI / SQLite / Neo4j 架构。普通用户既可从论文出发使用阅读、实验记录和研究问题三个旧工作区，也可从 `/research` 建立多论文课题。课题流程、状态语义和当前发布阻断项见 [课题工作台使用说明](research-project-workspace.md)。知识审核位于维护者入口；导航分流不是多用户权限隔离，不应当作公网上的权限系统。

课题工作台使用独立的 research 增量表，并保留旧论文、学习记录、路线与固定案例。SQLite 是课题事实真源，Neo4j 只保存按不可变快照构建的可重建投影。新方案生成在外部 provider 未获授权时明确失败，不用结构化模板伪装异步任务成功；用户可创建 `user_input` 人工空白草稿继续保存和快照流程，已保存课题、事实、方案和快照不依赖模型可用性。

## 主要行为

- PDF 先保存，按内容哈希去重。后台解析全文，保存文档版本、章节片段和可获得的页码；GROBID 表格保留行列与标题、说明，不自动转成数值结论。公式、图片、OCR 仍标记为未覆盖。
- arXiv 采集使用 HTTPS。论文页面可提交全文下载；仅支持明确允许的 arXiv 域名，限制大小与重定向次数。
- 抽取逐段进行，精确匹配原文引用。结构、语义检查和同一主张的冲突信号分别记录；同名向量接近不能自动证明实体一致。
- 自动检查通过仍不等于人工核验。模型新增先修关系保留为候选；正式路线只使用已人工核验且来源可定位的关系。
- 尚无独立人工评测数据，因此**没有启用关系自动发布，也没有宣称达到 95% 准确率**。维护者先核验小范围专题基础，其他用户可直接阅读原文和使用明确标识的辅助解释。
- 维护者可以录入教材、课程与论文原文来创建候选，核验、标争议、撤回和恢复为候选。已发布候选需先撤回再编辑。审计记录保存修改前后内容。
- 撤回会标记相关路线和同篇辅助解读待更新，保留用户完成状态；不自动改写学习历史。
- 阅读勾选不代表掌握；理解回答可记录为待思考、已回答或跳过。实验记录区分示例、小规模验证与论文结果复现，默认只是用户自述。
- 辅助解读和研究问题逐章节生成，引用必须指向输入片段；资源约束随输入提供。结果带未人工核验标识，按文档和画像缓存，断开模型服务仍能查看已保存结果。
- 路线不再让模型任意补论文、实验或“创新点”。维护者尚未发布足够证据时，返回明确的资料缺口；研究问题在论文工作区中单独生成，并标明待验证。
- 论文列表使用服务端分页。图谱候选由用户选择，支持增量展开、返回、筛选、画布适配和来源跳转。
- 后台最多执行 4 个任务，接收中的统一任务最多 24 个。任务和阶段状态持久化；重启把运行与排队任务标为中断，可重试，不自动假装续跑。
- 所有普通浏览与学习记录不依赖模型可用性。语义检索故障时返回关键词结果，并明确告知降级。

## 新接口

- `GET/PATCH /api/learning/papers/{uid}`：工作区、版本号、学习记录；冲突返回 409。
- `POST/GET /api/learning/papers/{uid}/guide`：异步生成与读取已保存辅助解读。
- `GET /api/learning/evidence/{passage_id}`：原文片段与版本。
- `POST /api/papers/upload-async`、`POST /api/papers/{uid}/fetch-fulltext`：持久化上传和允许域名的全文下载。
- `GET /api/learning/tasks`、`GET /api/learning/tasks/{id}`、`POST /api/learning/tasks/{id}/retry`：统一任务中心。
- `POST /api/learning/sources`：维护者录入有原文的教学关系候选，不自动发布。
- `GET /api/learning/quality`、`POST/PATCH /api/learning/quality/{id}`：质量状态、审计与候选编辑。
- `POST /api/learning/papers/{uid}/feedback`、`PATCH /api/learning/feedback/{id}`：用户困难反馈与维护者处理。
- `GET /api/learning/compare?uids=...`：并排查看已核验主张；没有完整同条件指标时不做数值排名。
- `PUT/GET /api/learning/papers/{uid}/protocol`：维护者登记复现协议。普通界面只展示显式标记已实测的记录。
- `POST /api/roadmap/generate-async`：后台路线生成；进度更新支持 `task_id` 与 `version`，保留旧阶段参数兼容性。

## 登记实测路径

维护者需提供 `scope`（example / small_scale / paper）、HTTPS `repository`、`commit`、`environment`、`resources`、`evidence_ids`、`maintainer`、`tested_at`、`test_log` 和 `verified`。每一步包含 `title / inputs / operation / expected_output / acceptance / troubleshooting`。

`verified=true` 是维护者对真实实测记录的声明，不是系统自动运行的结果。没有真实日志时保留 false。平台不会执行生成命令、下载大型训练数据或启动付费算力。

## 评测与人工工作包

在项目根目录执行：

```powershell
python backend/scripts/prepare_validation.py docs/validation
python backend/scripts/evaluate_quality.py docs/validation/quality-labels.jsonl --output docs/validation/quality-report.json
```

第一条创建 200 条**未标注**样本槽位、20 篇种子资料核验槽位及 8 名参与者的交叉顺序试用表。第二条只接受完整人工标签，拒绝空标签、重复样本与开发/测试重复；按关系类型输出 precision / recall / F1、证据支持率和精确率 Wilson 区间。

试用表不填写虚构受试者结果。将通用助手与原文阅读作为对照，分别记录阅读、复现、研究判断的时间、成功情况、求助次数与外部评分。样本小，结果只能作为探索性证据。

## 迁移、验证与运行边界

数据库采用新增表与新增列迁移，旧论文和进度保留。旧知识默认 legacy_unverified；读取旧路线时补齐稳定任务 ID。升级前建议备份数据卷；恢复时使用整个 SQLite 数据库及原文件目录，不单独覆盖图数据库。

```powershell
cd backend
python -m pytest -q --basetemp=.pytest_tmp_release
python -m ruff check app tests scripts
cd ../frontend
npm test
npm run build
```

测试禁止真实模型与 HTTP 服务请求，使用临时 SQLite 与模拟服务。生产 Neo4j、GROBID、真实模型和 GPU 复现仍需部署环境验收，不能从单元测试推断通过。

## 尚需真实参与者完成

- 约 20 篇真实专题论文、课程基础和先修关系的领域核验。
- 指定官方代码版本的真实基础复现实测及日志登记。
- 200 条真实样本的人工作答与质量评测。
- 6—10 名新手的对照试用及独立评分。

这些内容未伪造为已完成。自动发布校准、复杂公式/图像理解、经过外部评估的掌握度判断、广泛领域覆盖与多用户权限不属于当前已验证能力。
