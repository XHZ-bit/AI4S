# Research Atlas — 科研知识图谱智能平台设计文档

- 日期：2026-09-21
- 状态：已与需求方对齐，待评审
- 范围：MVP（第一阶段），面向 CS 具身智能 + 强化学习方向

## 1. 项目定位与目标

面向具身智能（Embodied AI）与强化学习（RL）方向的新手科研人员，构建"论文 → 知识点 → 资源"知识图谱平台，提供：

1. **论文解析与图谱构建**：从公开数据源与用户上传 PDF 中解析论文，用 LLM 抽取实体关系，经人工审核后入图
2. **多模态资源关联**：论文/方法/概念挂载代码库、视频、博客、课程等外部资源
3. **科研路线推荐**：基于图谱拓扑 + LLM，为新手生成个性化学习路线——读什么论文、复现什么实验、有哪些创新点
4. **可解释性**：每个推荐项携带图谱证据链，可回溯推荐依据

### 需求对齐结论

| 决策项 | 结论 |
|---|---|
| MVP 范围 | 知识图谱 + 科研路线推荐闭环（解析管道、问答助手等后置） |
| 领域方向 | 具身智能 + 强化学习 |
| 数据来源 | 公开 API 为主（arXiv / Semantic Scholar / Papers With Code）+ 用户上传 PDF 混合 |
| 图谱构建 | LLM 抽取 + 人工审核 |
| 路线推荐 | 图算法 + LLM 混合 |
| 使用场景 | 个人/小团队验证原型，不考虑多用户与注册体系 |
| 技术栈 | FastAPI + React + Neo4j Community + OpenAI 兼容 LLM API |

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                     React 前端 (Vite)                     │
│  图谱可视化页 / 论文详情页 / 路线规划页 / 审核工作台 / 数据管理 │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│                    FastAPI 应用层                         │
│  papers / graph / roadmap / review / search / collect    │
└──┬───────────────┬───────────────┬──────────────────────┘
   │               │               │
┌──▼─────┐  ┌──────▼──────┐  ┌────▼─────────┐
│collector│  │  pipeline   │  │   roadmap    │
│+ parser │  │ 构建管道服务  │  │ 路线推荐服务   │
└──┬─────┘  └──────┬──────┘  └────┬─────────┘
   │               │              │
┌──▼───────────────▼──────────────▼─────────┐
│        存储层（Docker Compose 编排）         │
│  Neo4j(图)  SQLite(元数据/任务)  FAISS(向量) │
└───────────────────────────────────────────┘
```

### 核心模块（单一职责，接口明确）

| 模块 | 职责 | 对外接口 |
|---|---|---|
| `collector` | arXiv/S2/PWC 元数据、引用、代码链接采集；接收上传 PDF | `collect_topic()`, `ingest_pdf()` |
| `parser` | PDF → 结构化文本（标题/摘要/章节/图表），全文切片 | `parse(pdf) -> PaperDoc` |
| `pipeline` | LLM 按 schema 抽取实体关系 → 审核队列；通过后写 Neo4j | `extract(paper)`, `approve()/reject()` |
| `graphsvc` | 图查询：邻域、引用链、概念依赖拓扑 | Cypher 封装查询 API |
| `roadmap` | 图算法求候选序列 + LLM 生成个性化路线 | `generate(profile, goal) -> Roadmap` |
| `search` | 摘要 embedding 语义检索（FAISS） | `semantic_search(q) -> [Paper]` |

### 关键决策

- SQLite 承担论文元数据、任务队列、审核状态、路线进度（原型期不引入 Postgres/Celery，采集与抽取用进程内任务）
- Neo4j Community 单实例；Docker Compose 一键编排全套
- LLM 调用统一走 OpenAI 兼容客户端，`base_url`/`model` 可配置（GLM/Qwen/DeepSeek 可切换）

## 3. 图谱 Schema

### 实体类型（7 类）

| 类型 | 说明 | 示例 |
|---|---|---|
| `Paper` | 论文：标题/年份/venue/arXiv ID/摘要/代码链接/复现难度 | "DreamerV3" |
| `Concept` | 抽象理论概念（知识点） | TD学习、域随机化、sim-to-real |
| `Method` | 具体方法/模型/算法 | PPO、SAC、RT-2、Diffusion Policy |
| `Dataset` | 数据集与仿真环境 | MuJoCo、Isaac Gym、D4RL、CALVIN |
| `Benchmark` | 评测基准与指标 | 成功率、ALFRED benchmark |
| `Resource` | 外部资源：代码库/视频/博客/课程 | 官方 repo、Spinning Up 教程 |
| `Author` | 作者（低优先级，仅存名字用于检索） | Sergey Levine |

### 关系类型（9 种，含可靠性来源）

| 关系 | 方向 | 来源 |
|---|---|---|
| `CITES` | Paper→Paper | Semantic Scholar API（高可靠，自动入库） |
| `PROPOSES` | Paper→Method | LLM 抽取 + 审核 |
| `USES` | Paper→Concept/Method | LLM 抽取 + 审核 |
| `EVALUATES_ON` | Paper→Dataset/Benchmark | LLM 抽取 + 审核 |
| `IMPROVES_ON` | Method→Method | LLM 抽取 + 审核 |
| `COMPARED_WITH` | Method↔Method | LLM 抽取 + 审核 |
| `PREREQUISITE_OF` | Concept→Concept | LLM 建议初值 + 人工逐条审核定稿 |
| `HAS_RESOURCE` | Paper/Method/Concept→Resource | PWC API + LLM 发现 |
| `SUBTOPIC_OF` | Concept→Concept | LLM 抽取 + 审核 |

### 设计要点

1. **`PREREQUISITE_OF` 是平台命脉**：路线推荐 = 概念依赖图上的拓扑排序。该关系对错误零容忍，是唯一强制人工逐条审核的关系；其余关系按置信度分级处理
2. **`Concept` 与 `Method` 分离**：概念对应"阅读线"（要学的知识），方法对应"实验线"（要复现的东西），直接支撑"读什么论文、复现什么实验"的产品目标
3. **可解释与可回溯**：所有实体/关系携带 `confidence`（抽取置信度）与 `source`（来源论文），推荐结果可回放证据
4. **资源扩展性**：`Resource` 类型支撑多模态资源关联，后续新增图文解析只需扩展 Resource 子类型，schema 不变

## 4. 数据管道：采集 → 解析 → 抽取 → 审核

### ① 采集（collector）

- **arXiv API**：分类 `cs.RO / cs.LG / cs.AI` + 关键词（"embodied", "reinforcement learning", "robot manipulation" 等），拉取近 5 年论文元数据与摘要，按提交日期游标增量同步
- **Semantic Scholar API**：arXiv ID 反查引用关系，自动建 `CITES` 边
- **Papers With Code**：匹配官方代码库，建 `HAS_RESOURCE` 边
- **上传 PDF**：走同一解析入口，入库标记来源

### ② 解析（parser）

- GROBID（Docker 服务）做 PDF → 结构化（标题/摘要/章节/引用）；失败降级 PyMuPDF 纯文本抽取
- 全文按章节切片存储，为抽取与后续问答预留

### ③ LLM 抽取（pipeline）

- **输入策略**：MVP 只喂摘要 + 引言 + 方法节首段（控制 token 成本，信息密度最高）；全文抽取为后续增强
- **Prompt 模式**：统一 schema 的 JSON 输出 + 领域 few-shot 示例；LLM 同时返回每条结果的 `confidence` 与原文依据片段（审核工作台据此展示证据）
- **实体对齐（去重关键）**：新实体与图内现有实体做 embedding 相似度匹配——阈值 ≥0.85 自动合并；0.6–0.85 交人工确认；避免同义实体重复建点

### ④ 审核（review）

- 分级策略：`PREREQUISITE_OF` 逐条人工审核；其余关系 `confidence ≥ 0.8` 自动通过、`0.5–0.8` 进人工队列、`< 0.5` 丢弃
- 审核工作台每条记录展示：抽取结果 + 原文高亮依据 + 现有相似实体；支持通过 / 编辑后通过 / 拒绝；拒绝原因入库用于改进 prompt

### ⑤ 入库

- 审核通过 → Cypher `MERGE` 幂等写入 Neo4j（重复导入不产生重复节点）

### 错误处理

- LLM JSON 解析失败自动重试 2 次后标记 `failed`
- 外部 API 限流：指数退避
- 解析/抽取失败论文停留在可重试状态，不阻塞队列

## 5. 路线推荐算法

**输入**：学习者画像（已掌握概念自评 + 可投入时间）+ 目标描述（如"3 个月入门具身智能，能复现操作方向论文"）

### 流程：图算法算骨架 → LLM 生成血肉

1. **目标实体定位**：LLM 将自然语言目标解析为图谱实体（语义不中时降级向量检索）
2. **依赖闭包 + 拓扑排序（阅读线骨架）**：从目标实体沿 `PREREQUISITE_OF` 反向遍历得概念闭包，Kahn 拓扑排序得学习顺序；画像中"已掌握"概念剪枝
3. **论文候选排序（填充阅读线）**：候选 = `PROPOSES`/`USES` 该概念的论文；`teaching_score = w1·log(引用数) + w2·综述/教程加权 + w3·有无 Resource + w4·年份新近度`；每概念取 top 2–3（1 精读 + 1–2 泛读）；`CITES` 链保证开创性论文先于讲解型论文
4. **实验线生成**：从目标 Method 沿 `IMPROVES_ON` 反向走改进链得复现序列（经典 baseline → 中间改进 → 目标方法）；优先有官方代码版本；标注复现难度（LLM 依据代码/数据完备性打分，人工可改）
5. **创新点建议（图谱统计信号）**：
   - 信号 A：`COMPARED_WITH` 边稀疏但引用增长快的新兴 Method
   - 信号 B：`IMPROVES_ON` 链末端无后继的方法
   - 信号 C：热门 Benchmark 上方法覆盖薄弱的方向
   - LLM 消费结构化信号 + 论文摘要，生成 3–5 条创新建议，每条附图谱证据
6. **LLM 包装输出**：结构化路线 JSON → LLM 结合用户背景补充"为什么学"与周粒度阶段划分
7. **进度跟踪**：路线存 SQLite，前端勾选进度后重算剩余路径

### 可解释性保障

路线中每个推荐项携带 `evidence` 字段（依赖概念 / 引用数据 / 图谱证据链），前端展示"推荐理由"——区别于纯 LLM 生成的核心卖点。

### 测试策略

- 图算法层：构造小型图谱 fixture，验证拓扑序正确性、闭包完整性、剪枝正确性
- LLM 层：mock 测试 JSON 合规性
- 端到端：以"RL 零基础 → 具身智能操作方向"标准画像为验收用例，人工评审路线合理性

## 6. 前端页面与 API

### 前端 5 页面（React + Vite + Ant Design + Zustand）

| 页面 | 核心交互 |
|---|---|
| 图谱可视化 | `react-force-graph-2d` canvas 渲染；节点按类型着色、大小=引用数；点击出详情卡；类型过滤、搜索定位、邻域展开 |
| 论文详情 | 元数据/摘要、图谱关联区（引用上下游/提出方法/使用概念/挂载资源）、"在路线中的位置"入口 |
| 路线规划 | 画像表单 → 生成 → 周粒度阶段化时间线（论文/实验/资源卡片 + 推荐理由 evidence）→ 勾选进度自动重算；创新点建议区 |
| 审核工作台 | 待审队列（按关系类型分组，`PREREQUISITE_OF` 置顶）、左证据右结果、通过/编辑/拒绝、批量通过高置信项 |
| 数据管理 | 触发 arXiv 采集（分类+关键词+时间范围）、上传 PDF、任务状态列表与重试 |

### API 设计（REST，`/api` 前缀）

```
POST /api/collect                触发采集任务
POST /api/papers/upload          上传 PDF
GET  /api/papers/{id}            论文详情（含图谱关联）
GET  /api/graph/nodes?type=&q=   节点检索
GET  /api/graph/neighbors/{id}   邻域子图（按需加载）
POST /api/roadmap/generate       生成路线
GET  /api/roadmap/{id}           路线详情
PATCH /api/roadmap/{id}/progress 更新进度（触发重算）
GET  /api/review/queue           待审核列表
POST /api/review/{id}/decision   通过/编辑/拒绝
GET  /api/search?q=              语义检索
```

**约定**：图谱节点带稳定 `uid`；路线 JSON 契约由 pydantic schema 单点定义，TS 类型同步生成（避免两处手写漂移）；错误统一 `{code, message}`。

## 7. 部署与项目结构

### Docker Compose

```
services:
  neo4j       # 图库（Community 单实例）
  grobid      # PDF 结构化解析
  backend     # FastAPI + uvicorn
  frontend    # nginx 静态托管
```

- 密钥（LLM API key、Neo4j 密码）走 `.env`，仓库仅提交 `.env.example`
- 后端无状态，数据全在 Neo4j/SQLite/FAISS 卷中，可随时重建

### 目录结构

```
research-atlas/
├── backend/
│   ├── app/
│   │   ├── main.py / config.py
│   │   ├── api/         # 路由
│   │   ├── collector/   # arxiv.py, s2.py, pwc.py
│   │   ├── parser/      # grobid.py, fallback.py
│   │   ├── pipeline/    # extract.py, align.py, review.py
│   │   ├── graphsvc/    # queries.py
│   │   ├── roadmap/     # graphalgo.py, generate.py, scoring.py
│   │   ├── search/      # faiss_index.py
│   │   └── models/      # pydantic schemas（含 Roadmap 契约）
│   └── tests/           # fixtures + 单测 + 端到端冒烟
├── frontend/
│   └── src/pages|components|api|stores/
├── docker-compose.yml
└── .env.example
```

## 8. 里程碑

| 阶段 | 交付物 | 验证方式 |
|---|---|---|
| M1 基础设施 | Compose 全套可启动、schema 初始化、后端骨架 | `docker compose up` 健康检查通过 |
| M2 数据管道 | 采集→解析→(mock)抽取→入库 | 命令行触发，Neo4j Browser 查到论文节点 |
| M3 LLM 抽取+审核 | 真实抽取、实体对齐、审核工作台 | 10 篇论文抽取+审核通过，边可解释 |
| M4 图谱应用 | 可视化页、论文详情、语义检索 | 浏览器交互演示 |
| M5 路线推荐 | 图算法+LLM 生成、路线页、进度跟踪 | 标准画像生成完整路线 |
| M6 验收 | 20 篇具身智能种子论文端到端 | 从零生成"零基础→复现 Diffusion Policy"路线并人工评审 |

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 图谱冷启动质量 | M6 用精选种子论文（每个核心概念的代表论文）保证初期图谱质量 |
| LLM 成本与稳定性 | 抽取只喂摘要+引言；失败重试与降级；API 供应商可切换 |
| GROBID 环境问题 | PyMuPDF 兜底路径内置 |
| 依赖关系错误导致路线失真 | `PREREQUISITE_OF` 强制人工逐条审核；实体对齐防同义节点 |
| 原型期技术债 | SQLite/进程内任务为显式妥协点，接口已按可替换设计 |

## 10. 明确不在 MVP 范围内

- 多用户注册/权限体系
- 论文全文深度抽取与公式/图表多模态解析
- 对话式问答助手（Agent 入口）
- 图片/视频资源的自动内容理解（仅做链接关联与类型标注）
- 高可用部署、横向扩展
