# Research Atlas：GitHub 开源技术调研与接入建议

调研日期：2026-10-19。范围是现有 React、FastAPI、SQLite 个人空间、论文证据与科研方案工作台；部署约束沿用项目现有小规模低成本方案。结论来自本地源码核对、官方 GitHub 的 README/LICENSE 和官方文档。未安装候选框架、下载模型或测试新的生产部署；以下接入收益为工程判断，内存、速度和质量收益尚需实测。

## 结论

优先完善五项能力：**可回到原文的结构化解析、段落级检索、按问题组织证据、可重复的质量评测、可恢复的公开服务**。保留现有个人空间、人工方案、证据状态和不可变快照，通过小型适配器引入新能力。

项目已经有 FTS5 trigram 全文索引，`api/search.py` 的 `/v2` 已用加权倒数排名融合词法与语义结果。真正的检索缺口是词法候选仍按手写命中数排序、每篇仅取首个匹配片段，以及结果未完整返回证据定位字段；不应再从零建设一套重复的混合检索。

## 一、直接改善科研与学习体验

### 1. Docling：先在开发电脑试验结构化论文解析

**已核实**：项目提供文档转换与结构化表示，代码为 MIT。适合评估复杂版面、阅读顺序、表格和定位信息；具体模型、OCR 引擎和权重需按所选组合另查许可。[仓库](https://github.com/docling-project/docling)、[代码许可](https://github.com/docling-project/docling/blob/main/LICENSE)。

**本项目接法**：在 `backend/app/parser/service.py` 增加可选适配器，转换为现有 `ParsedPaper/Section`；把页码、坐标、表格结构与解析器信息保存在 `metadata`，供证据抽屉和 PDF 高亮使用。保留快速本地解析路径。先在开发机离线处理代表性论文并导入结果，不能假定它能在 2GB 服务器上与 API 常驻运行。

**版本边界**：当前文档/片段 ID 与 PDF 哈希及顺序有关。同一 PDF 换解析器时，应新增解析产物版本，绑定 PDF SHA-256、解析器/模型/配置版本；不能用新坐标覆盖旧证据和旧快照。表格、公式解析成功也不能自动变成“已核实科研事实”。

**验收**：固定一组有授权的双栏、中文、跨页表格和扫描 PDF，比较阅读顺序、表格单元格/单位、定位覆盖、耗时和峰值内存；只对确有提升的类型启用。

### 2. SQLite FTS5 + sqlite-vec：改进已有检索，向量扩展按需选装

**已核实**：SQLite FTS5 提供 `bm25()` 与 trigram 检索；短于三个字符的 trigram 全文查询有明确限制。sqlite-vec 把向量查询放入 SQLite，提供 MIT/Apache-2.0 双许可；其稳定性与具体版本边界见专项记录。[FTS5 官方文档](https://www.sqlite.org/fts5.html)、[sqlite-vec 仓库](https://github.com/asg017/sqlite-vec)。

**本项目接法**：先修改 `backend/app/search/service.py`，把候选从论文级提升为段落级，比较 FTS5 BM25 与现有排序；保留中文短词回退。复用 `api/search.py` 已有的融合方法，输出 `passage_id/document_id/page/quote`，支持直接跳到原文。现有每用户数据库继续独立，不增加全站共享私有索引。

已有摘要向量规模较小时，可以继续使用现有余弦计算；只有基准显示需要时才加 sqlite-vec。向量表应记录模型、维度、内容哈希和索引版本，避免换模型后混用向量。扩展包、操作系统架构和 SQLite 加载能力必须在 Windows、容器与 CI 上检查。

**验收**：固定中文/英文/同义词/缩写/短词查询与目标段落，比较 Recall@k、MRR、延迟、索引体积和双账号隔离。达到改进门槛后再替换默认排名。

### 3. PaperQA2：借鉴“检索—证据整理—带引文回答”方法

**已核实**：PaperQA2 明确分为论文搜索、证据收集与答案生成，并提供带引文的科学文献问答；代码 Apache-2.0。[仓库及算法说明](https://github.com/Future-House/paper-qa#paperqa2-algorithm)、[许可](https://github.com/Future-House/paper-qa/blob/main/LICENSE)。

**本项目接法**：在现有 `guidance.py`、`assistant` 和科研方案模块之上增加按问题检索：先选证据，再生成有范围限制的解释。证据保留文档版本、原文、页码和实验条件，每条主张绑定证据；资料不足时明确缺口。复用已有 `EvidenceRef` 和快照机制，不另造一套事实状态。

优先借鉴算法，暂不整体嵌入默认 agent。其多轮搜索、摘要与重排可能增加模型请求、外部元数据访问和费用，必须经过项目统一预算入口；当前多人模型关闭策略不能被新库旁路。其公开评测成绩不代表本项目接入后的质量。

### 4. Promptfoo / Ragas：让真实质量变化可测量

**已核实**：Promptfoo 为 MIT，支持 Python provider、确定性断言和 CI；Ragas 为 Apache-2.0，提供检索相关与回答忠实度等指标，部分指标需要额外模型调用。[Promptfoo](https://github.com/promptfoo/promptfoo)、[Python 接入](https://www.promptfoo.dev/docs/providers/python/)、[确定性断言](https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/)、[Ragas](https://github.com/vibrantlabsai/ragas)、[指标及调用边界](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)。

**本项目接法**：扩展现有 `evaluation/research_atlas`，先把已保存输出和模拟 provider 接入确定性评测，再对批准的小样本调用真实模型。优先检查：引用存在、引文可定位、结论是否保留否定和实验条件、无依据时是否拒答、来源变更是否标记旧方案待复核。

用固定标注集测检索命中与人工核对的主张支持率；模型评分作为辅助信号，不直接等同科学结论正确。CLI 在本机运行不代表数据不会外发，远程 provider/评判模型仍需要单独限定资料与费用。建议先选 Promptfoo 承载回归，后续有明确指标需要时再选用 Ragas，避免重复维护两套完整评测栈。

### 5. Py-FSRS：为论文学习加入有依据的复习计划

**已核实**：Py-FSRS 提供间隔复习调度、卡片和 ReviewLog，MIT；基础包仅依赖 `typing-extensions`，优化器为可选依赖。[仓库](https://github.com/open-spaced-repetition/py-fsrs)、[依赖与可选优化器](https://github.com/open-spaced-repetition/py-fsrs/blob/main/pyproject.toml)、[许可](https://github.com/open-spaced-repetition/py-fsrs/blob/main/LICENSE)。

**本项目接法**：在个人 SQLite 增加复习卡和复习记录，卡片绑定概念、练习与来源版本，在统一任务页显示到期复习。保存用户回忆难度与调度结果，暂不部署参数训练，也不额外调用模型。来源改变后提示回看原文。

复习完成、测验答对和用户确认掌握继续分开记录，不自动改写 `workflow_mastery`。它适合辅助长期学习，不能据此声称已证明科研能力或知识掌握。

## 二、让服务更完整的工程选型

| 候选 | 解决的缺口与建议接法 | 判断 |
|---|---|---|
| [uv](https://github.com/astral-sh/uv) · MIT/Apache-2.0 | 给后端引入锁文件、固定 Python 与依赖，在 CI/镜像执行锁定安装；保留现有前端 npm 锁文件 | 近期优先，构建工具，不增加常驻服务 |
| [Caddy](https://github.com/caddyserver/caddy) · Apache-2.0 | 公开入口的 HTTPS 与证书续期；新增生产配置，API 直接反代后端，静态内容沿用原前端 | 近期优先；需同时验收可信代理、Host、Origin 和 Secure Cookie |
| [restic](https://github.com/restic/restic) · BSD-2-Clause | 对完整多人数据暂存快照做加密、增量、异机备份，并做隔离恢复演练 | 近期优先；先保证 SQLite/PDF 一致，再上传备份 |
| [Huey](https://github.com/coleifer/huey) · MIT | SqliteHuey 可运行独立 consumer、持久化待执行任务和调度；适配 `tasks.py/jobs.py` | 按需求引入，先用于本地解析/索引；不是“永不丢任务”保证 |
| [PyrateLimiter](https://github.com/vutran1710/PyrateLimiter) · MIT | SQLite 后端按账号和操作限制突发请求，在昂贵解析/生成之前做准入 | 按需选装；现有登录已有保护，不能把请求次数限制当费用账本 |

Huey 官方明确不保证至少一次执行，强杀 consumer 可能丢失正在执行的任务。因此必须保留现有任务台账、幂等检查、取消、恢复和租户验证；跨进程显式传递账号 ID，再建立个人空间，不能依赖 ContextVar 自动跨进程传播。可以借鉴事务发件箱及租约方法把业务落库和投递衔接起来。付费调用不得因为框架默认重试而自动重发。[SqliteHuey](https://huey.readthedocs.io/en/latest/api.html#SqliteHuey)、[consumer 关闭边界](https://huey.readthedocs.io/en/latest/consumer.html#consumer-shutdown)。

备份应包含 `identity.db`、全部个人业务库和 PDF。先停止并等待全部写入者退出，生成一致的不可变暂存副本，再恢复服务并异机备份；或另行设计并验证在线多文件快照。现有 `data_archive.py` 的单业务库快照不等于完整多人备份。Caddy/restic/uv 的具体来源与迁移验收见运维专项记录。

## 三、应谨慎或暂缓的方案

- **FastAPI Users**：MIT，但官方明确为 maintenance mode，并非无人维护。当前已有账号与租户边界，单纯为了注册/邮件重写整套认证收益有限；先补令牌、邮箱流程和审计，确需 OAuth/OIDC 时再通过 Authlib 适配。[维护声明](https://github.com/fastapi-users/fastapi-users#readme)。
- **LiteLLM 完整 Proxy**：可借鉴统一入口、用量与预算方法。公开用户预算涉及数据库与具体版本/功能边界，不能把配置 `max_budget` 当作无条件硬账单上限；不在当前小服务器上直接叠加完整网关。先让项目新旧模型入口共享原子预留/结算台账。[仓库](https://github.com/BerriAI/litellm)、[预算文档](https://docs.litellm.ai/docs/proxy/users)。
- **Litestream**：可选的 SQLite 持续复制方案，不是完整多人文件备份。新版本支持多库目录发现，暂缓理由是跨库与 PDF 的一致恢复、版本清单和恢复演练尚未建立。[仓库](https://github.com/benbjohnson/litestream)。
- **LangGraph / LightRAG**：前者可用于有明确需要的可恢复多步研究 agent，后者可借鉴图与文本检索结合的方法；先保留现有工作流和经核验知识边界。全量迁移会增加状态、模型调用和存储适配，不自动解决个人空间授权、科学证据与成本控制。[LangGraph](https://github.com/langchain-ai/langgraph)、[持久化边界](https://docs.langchain.com/oss/python/langgraph/persistence)、[LightRAG](https://github.com/HKUDS/LightRAG)。
- **Marker / MinerU**：需按当前版本分别核对代码、附加条款与模型权重，不能沿用“全是 GPL/AGPL”或“都是纯 Apache”的旧概括。近期优先用许可与模型组合明确的 Docling 做隔离比较，具体证据见文档解析专项记录。

## 四、建议执行顺序与完成标准

1. **先建立基线和可恢复交付**：锁定依赖；固定检索/证据样本和可重复评测；补完整多人备份、隔离恢复与 HTTPS 配置。完成条件是新环境能复现运行、旧数据能恢复、代理链下登录和文件访问通过测试。
2. **再改进科研业务能力**：在当前 FTS5/融合检索上做段落排名及定位输出，随后试验 Docling 解析和 PaperQA2 式证据组织。完成条件是相同样本下能展示具体改进，且旧来源/快照、隔离与费用边界保持有效。
3. **再增强长期学习与独立任务执行**：增加来源绑定的 FSRS 复习；确需独立 worker 时评估 Huey。完成条件是状态可追踪、重启可解释、取消与重复执行安全，用户不会因调度结果被自动认定掌握。

本次调研没有给候选工具宣称任何本项目实测的资源占用或准确率提升。上线选型应固定发布版本、依赖和模型快照，重新核查相应许可及维护声明。

## 专项证据

- [账号、任务与模型预算](github-backend-notes-2026-10-19.md)
- [论文解析、检索与权重边界](github-document-search-notes-2026-10-19.md)
- [部署、备份与可重复构建](github-operations-notes-2026-10-19.md)
