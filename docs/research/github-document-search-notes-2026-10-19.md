# 论文解析、证据定位与本地检索：GitHub 技术核查

核查日期：2026-10-19。范围：官方仓库、实际 LICENSE、官方文档与发布者模型卡；业务源码只读。本次未安装候选、下载权重、运行性能测试，以下资源判断是结合官方说明和本项目架构作出的工程判断，不能当作 2 核 2GB 的实测承诺。

近期优先两条路线：

1. **先改进现有 FTS5 段落排序和已有加权 RRF**：让检索返回真正相关的原文段、文档版本和页码，补中文短查询与相关性评测。无需新增常驻服务或嵌入模型。
2. **用 Docling 在开发电脑离线试验复杂论文解析**：保留原 PDF，将带页码、几何位置、表格结构的 JSON 经适配器导入独立解析产物版本。服务器继续使用现有轻量解析路径，重型模型不在 2GB 实例默认常驻。

FastEmbed 与 sqlite-vec 为后一阶段的可选组合：先验证本地模型、中英文查询质量、版本元数据和个人库隔离，再决定是否启用。MinerU、Marker 作为离线对照候选；不整体替换为 RAG 框架。

## 现有基础与真正缺口

| 本地位置 | 已有能力 | 应改进的部分 |
| --- | --- | --- |
| `backend/app/db/search_index.py` | `paper_search_fts`、`passage_search_fts` 均为 FTS5 trigram；有增量触发器及旧库回填 | 有全文索引，不应写成“尚无全文检索”；需要质量评测、排序和短查询策略 |
| `backend/app/search/service.py` | FTS 筛候选；短词或无 FTS 时扫描降级；已有摘要向量及 Python 余弦扫描 | 最终词法排序仍为手写标题/摘要命中数；原文只保留每论文遇到的首条片段，已有标题/摘要命中还会跳过原文；缺少最佳段落排序及定位字段 |
| `backend/app/api/search.py` | `/v2` 已按 `2/(60+lexical_rank) + 1/(60+semantic_rank)` 融合；模型不可用时保留词法结果 | 已有 weighted RRF，不是需要从零添加；需要把输入排序、融合规则和回归数据版本化 |
| `backend/app/parser/service.py`、`grobid.py`、`fallback.py` | 本机 GROBID 优先、PyMuPDF 降级；多人模式直接本地 PyMuPDF；保留 PDF 页码；GROBID 有原始表格行及说明 | 目前 PyMuPDF 是整页文本；GROBID 请求未开启坐标选项，适配器也未导入坐标；不能把“GROBID 本身支持定位”误写为“本项目已保存 bbox” |
| `backend/app/models/paper.py`、`backend/app/db/workspace.py` | `Section.page`、`kind`、`metadata`；`passages.metadata_json`；文档、段落及引用版本化基础 | 需要解析器版本、坐标系、来源块 ID、表格结构和失败覆盖信息的明确契约 |
| `backend/app/tenancy.py`、`backend/app/db/sqlite.py` | 每个账号独立 SQLite 和资料目录，任务继承个人空间 | 新的索引、离线产物、缓存及回填必须继续按个人空间隔离 |

FTS5 官方说明：`bm25()` 分数越小越相关；trigram 的 MATCH 对不足 3 个 Unicode 字符的查询不命中。因此“异常”等两个汉字不能简单交给现有 trigram MATCH；保留有边界的降级，并与英文长词、多词查询分开评测。[SQLite FTS5 排序](https://sqlite.org/fts5.html#the_bm25_function)、[trigram 限制](https://sqlite.org/fts5.html#the_trigram_tokenizer)。

## 六个候选与技术

| 候选 | 已核查的代码许可与模型边界 | 页码、位置、表格 | 本项目判断 |
| --- | --- | --- | --- |
| [Docling](https://github.com/docling-project/docling) | 代码 MIT；模型另行授权，不能把 MIT 扩展到全部权重、OCR 和依赖 | 统一文档对象有 provenance、可选 bbox、表格及层级；字段存在不等于每个 PDF 都能正确恢复 | 优先作为开发机离线解析对照；不默认取代在线 PyMuPDF |
| [MinerU](https://github.com/opendatalab/MinerU) | 当前核查版本为 Apache-2.0 基础上的自定义附加条款；不同权重版本许可不同 | PDF 输出包含页索引与布局几何，支持表格和公式；质量与所用 tier 相关 | 可做复杂扫描/公式离线对照；先核完整模型清单和许可，再决定引入 |
| [Marker](https://github.com/datalab-to/marker) | 当前核查代码是 Apache-2.0；Surya 权重为 modified AI Pubs OpenRAIL-M，含商业规模及竞争服务限制 | JSON 为页/块树，含 polygon；表格可输出 HTML；VLM OCR 不保证字符级框 | 不作为默认近期依赖；资源与权重限制均需单独处理 |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | MIT / Apache-2.0 双许可文件；项目明确 pre-v1 | 仅向量存储与检索，不产生页码、bbox 或表格；需关联已有段落来源 | 向量准备、版本及隔离验证后选装；不用它替代 FTS |
| [FastEmbed](https://github.com/qdrant/fastembed) | 库 Apache-2.0；每个模型单独许可；可选 BGE 小模型的发布者模型卡为 MIT | 本地 ONNX 编码；不做 PDF 解析，也不产生证据定位 | 先开发机离线编码；在线查询编码必须额外测内存、并发和中英适配 |
| [RRF 方法](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) | 排名融合方法，不是必须引入的新服务或某个框架 | 组合已有排名，不补解析覆盖、证据定位或科学正确性 | 已有加权实现，近期重点是改进输入排序并评测，而非声称首次引入 |

### Docling：最适合先试的结构化解析适配器

已直接读取 [固定代码版本 LICENSE](https://github.com/docling-project/docling/blob/0e54294231b69bc2cf7a39873235495788f76b57/LICENSE)。MIT 适用于代码；官方 README 明确模型需查看各自许可。发布者的 [Heron 模型卡](https://huggingface.co/docling-project/docling-layout-heron) 标为 Apache-2.0，[docling-models 模型卡](https://huggingface.co/docling-project/docling-models) 列出 CDLA-Permissive-2.0 和 Apache-2.0。实际部署还须核准选中的 OCR、其他增强模型和依赖版本，不能把几个已核模型推广到任意 Docling 配置。[官方仓库说明](https://github.com/docling-project/docling#license)。

`DoclingDocument` 能承载文本、表格、图片、阅读顺序和可用时的布局位置；其 [provenance 类型](https://github.com/docling-project/docling-core/blob/main/docling_core/types/doc/document.py) 提供 `page_no`、`bbox`、`charspan`。保留 JSON，比只导出 Markdown 更适合本项目回到原 PDF 核对；缺失 bbox 时必须保持空值。[文档模型](https://docling-project.github.io/docling/concepts/docling_document/)。

官方支持模型预取和指定本地 artifacts，远程服务需要显式开启。建议开发机固定模型与配置、断网执行、单任务处理；2GB 服务器仅接收校验后的结果。官方“可本地运行”不是本项目配置下的内存或吞吐保证，OCR、图片分辨率、表格识别和进程数会改变峰值。[离线及高级配置](https://docling-project.github.io/docling/usage/advanced_options/)。

接入点：新增 `backend/app/parser/docling_adapter.py` 和开发机离线脚本；映射到 `Section` 与 `passages.metadata_json`；在 `frontend/src/components/workspace/PdfReader.tsx` 后续增加 bbox overlay，但保留原 PDF、页码跳转和无框时的原文片段回退。解析文字、单位、公式、跨列表格均需抽样人工检查，不能自动升级为已核科学主张。

### MinerU：能力强，但必须区分版本、权重与运行档位

已读取 [固定版本 LICENSE.md](https://github.com/opendatalab/MinerU/blob/b7f3dd0c5f6e6d66a298239ffd02b328b873918e/LICENSE.md)：除 Apache-2.0 外，存在按关联方合并计算的商业许可门槛（月活超过 1 亿，或月总收入超过 2000 万美元），及面向第三方在线服务的显著署名义务。不能简称为无附加条件的 Apache，也不能因当前只有 20 个账号就忽略组织及关联方条件。

权重也不能一概而论：官方 [MinerU2.5-Pro-2605-1.2B](https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B) 模型卡标为 Apache-2.0，而 [MinerU2.5-2509-1.2B](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B) 标为 AGPL-3.0。当前 [MinerU-4_models_onnx](https://huggingface.co/opendatalab/MinerU-4_models_onnx) 公共模型卡缺许可元数据，列有多个 OCR、布局、公式及表格组件；本次未逐件完成其授权闭环，不能承诺整包权重都服从主仓库许可。

官方当前 README 给出的 Basic ONNX 最低 RAM 为 2GB、模型下载约 0.8GB；Standard/Advanced 的 ONNX + llama.cpp 最低 RAM 为 8GB。前者不是给 FastAPI、操作系统、20 个账号和解析任务共享的剩余内存保证，因此本项目不应在同一台 2GB 机器默认常驻。[资源说明](https://github.com/opendatalab/MinerU#model-engines-with-extras)、[档位说明](https://opendatalab.github.io/MinerU/usage/tiers/)。

4.x 的 `MiddleJson` 有版本化 schema、页索引和几何信息；`page_idx` 从 0 开始，须转换为本项目从 1 开始的页码。不能直接沿用 2.x/3.x 的 `pdf_info` 等字段，也不能把 CLI 的响应 JSON 当作中间解析格式。通过独立离线适配器导入，禁用默认远程服务及 LLM 后处理；表格/公式输出仍是候选内容。[结果契约](https://opendatalab.github.io/MinerU/reference/output_files/)、[模型与离线来源](https://opendatalab.github.io/MinerU/usage/model_source/)。

### Marker：代码许可已变，权重仍有实质限制

已读取 [固定版本代码 LICENSE](https://github.com/datalab-to/marker/blob/ad1b414d846653f4048cdc527993f6c09b829869/LICENSE)：本次核查为 Apache-2.0，不沿用旧版本 GPL 的印象。官方 README 将权重与代码分开，权重适用 modified AI Pubs OpenRAIL-M。[代码与权重说明](https://github.com/datalab-to/marker#commercial-usage)。

进一步读取官方 [Surya 权重 LICENSE](https://huggingface.co/datalab-to/surya-ocr-2/blob/main/LICENSE)：Attachment A.2 涉及上一年总收入超过 500 万美元、累计股权或债务融资超过 500 万美元的条件及个人/研究用途例外，还限制提供与许可方及关联方竞争的产品或服务；条款同时要求下游遵守使用限制。不能只依据“研究免费”或 README 的简短门槛摘要判断本项目对外服务已获授权。

Marker JSON 按页和块组织，带 polygon，表格可保留 HTML；官方特别说明 VLM OCR 路径不返回字符框。当前 CPU fast 模式仍可能为扫描页或修复启动推理服务，禁用 OCR 则会跳过相应扫描/公式能力；不据此宣称可在 2GB 在线完整解析。[输出及运行模式](https://github.com/datalab-to/marker)。如果后续试验，使用与 Docling 相同的离线适配器边界、版本清单及评测集，避免另建一套业务数据模型。

### sqlite-vec：可选的向量执行层，不是立即需要的新数据库

仓库有 [MIT](https://github.com/asg017/sqlite-vec/blob/04d28bd21773981e2d266bbf6aa4efbd011eb4f6/LICENSE-MIT) 与 [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) 许可文件。官方 README 明确 pre-v1、可能发生破坏性变更；发布页目前将 [v0.1.9](https://github.com/asg017/sqlite-vec/releases/tag/v0.1.9) 标作 Latest，另有 [v0.1.10-alpha.1](https://github.com/asg017/sqlite-vec/releases/tag/v0.1.10-alpha.1) 的 ANN 初始预发布。文档站也展示后续 alpha 版本，接入时必须匹配固定包/文档，不能写成“一概只有 alpha”，也不能把存在非预发布版本等同于稳定兼容承诺。[README](https://github.com/asg017/sqlite-vec)。

本项目的适用方向是用 C 扩展执行向量距离与 KNN，替换 Python 逐向量扫描，而不是改成独立向量服务器。非预发布版本先评测精确 KNN，不把实验 ANN 的扩展性、内存或召回率当成现成保证。[KNN 文档](https://alexgarcia.xyz/sqlite-vec/features/knn.html)。

接入点为 `backend/app/db/sqlite.py` 的连接初始化、独立向量表/迁移模块和 `backend/app/search/service.py`。只向已经授权的个人数据库连接加载固定扩展；按官方示例加载完立即关闭扩展加载权限。不要允许请求指定扩展路径，也不要把“partition key”误当访问控制。[Python 加载方式](https://alexgarcia.xyz/sqlite-vec/python.html)。

现有 `_pack()` 为 float64，`vec0` 常见 float 列和 `serialize_float32()` 使用 float32；旧 BLOB 不能直接复用。当前 `paper_embeddings` 又缺 model revision、维度、归一化和分块版本，且只有论文级向量。只有验证同一编码空间和来源后才能转换；无法追溯来源的旧向量应重建，不能静默混用。新索引可重建并应保留 FTS 回退；删除、重建、备份恢复及账号隔离必须测试，0.1.9 也有与 DELETE 相关的修复。

### FastEmbed：轻量 ONNX 方案，但“模型文件小”不等于“进程只占这么多内存”

已读取 [库 LICENSE](https://github.com/qdrant/fastembed/blob/main/LICENSE)，为 Apache-2.0。官方支持列表分别列模型许可、维度和 `size_in_GB`：`BAAI/bge-small-en-v1.5` 为 384 维、0.067GB，`BAAI/bge-small-zh-v1.5` 为 512 维、0.090GB；其 [英语 ONNX 发布卡](https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q)、[中文 ONNX 发布卡](https://huggingface.co/Qdrant/bge-small-zh-v1.5) 均标 MIT。库的 Apache 许可不能代替任意下载模型的许可。[模型列表](https://qdrant.github.io/fastembed/examples/Supported_Models/)。

`size_in_GB` 是模型描述中的大小，不能当成常驻 RSS；ONNX Runtime、tokenizer、token 数、batch、线程和进程副本都有成本。官方接口提供 `threads`、`batch_size`、`parallel` 等控制，并明确更大 batch 使用更多内存。建议先单进程、低 batch、1–2 线程实测，避免每账号或每 Uvicorn worker 各初始化一个模型，也不使用全核数据并行争抢 2 个 CPU 核。[实现及参数](https://github.com/qdrant/fastembed/blob/de502ca83baa2b81922cb5a46acf689f5e2c72a1/fastembed/text/onnx_embedding.py)。

优先在开发机按段落离线编码，服务器只接收经过版本校验的向量；但在线语义查询仍需用同一模型编码 query，这部分内存和延迟不能靠离线文档编码自动消除。首次模型下载应提前完成并固定缓存，缺模型则退回词法检索。英语模型不能承诺中文问题检索英文论文的跨语言质量；中英文模型维度不同，也不能直接混合做余弦距离。

接入点：新增独立 `backend/app/search/local_embedding.py` 和离线编码脚本，服务层只消费已定义的 encoder 接口；不要直接改 `backend/app/llm/client.py` 的通用 `embed()`，否则可能意外改变其他向量调用。记录 `model_id/revision`、ONNX 文件校验值、tokenizer、维度、距离函数、归一化、分块及文档版本，再与 sqlite-vec 联合评测。

### RRF：沿用方法，修正输入排名与来源粒度

原始 RRF 论文给出按各排名位置求倒数和的方法，并在其试验中使用 `k=60`。本项目现有 `/v2` 已使用带 2:1 权重的变体；无需引入第三方框架。`k` 和权重不是科学正确性的分数，也没有理由在本项目语料上未经评测照搬最优结论。[Cormack、Clarke、Büttcher，SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)。

先对 `passage_search_fts` 计算 BM25、选每篇的最佳证据段，保留若干支持段，再做论文级去重和现有融合；有向量时分别提供有界 top-k，无向量时照常提供词法结果。不要将浮点余弦分数与 BM25 原值直接相加。返回 `paper_uid`、`document_id`、`passage_id`、`page`、命中原因及规则版本，分开显示检索相关性和证据审核状态。

## 解析产物必须独立版本化

当前 `save_document()` 的文档 ID 来自 `uid + content_hash`，段落 ID 来自 `document_id + ordinal`；旧文档和段落使用 `INSERT OR IGNORE`，但段落的 `kind/metadata_json` 仍会被 UPDATE。上传路径又将原 PDF digest 传作 `content_hash`。同一 PDF 换解析器、模型或配置后若复用这些 ID，可能把新 bbox/表格元数据混到旧文本和旧证据上，破坏历史快照的可追溯性。

建议增加独立解析产物标识，例如：

```text
source_sha256 = SHA256(original_pdf_bytes)
artifact_id = SHA256(source_sha256 + parser_name/version + model_revisions
                     + canonical_config_hash + adapter_schema_version)
```

迁移设计应新增解析产物表/字段及段落关联，而不是盲目改变现有 `content_hash` 的去重语义。旧 `documents/passages/knowledge` 和快照继续引用原版本；新结果生成新段落 ID，显式更新当前选择，并将受影响派生结果标记待复核，不覆盖历史事实。

离线产物最少保留：原 PDF SHA、产物版本、parser/model/config 清单、原始 JSON、块 ID、原文、页码、bbox/polygon、坐标原点和单位、页宽高及旋转、表格单元格/跨行跨列/标题/单位、缺失覆盖与置信信号。坐标或页码缺失就记空；OCR 修订的文本不能冒充 PDF 文字层的精确引文。bbox 原点转换、缩放和旋转要用原页叠加验证；不靠“看起来接近”认定定位正确。

导入时还须核对个人空间、PDF SHA 和目录边界，限制 JSON/图片体积及块数；不能接受离线包里的任意文件路径或直接执行 HTML/命令。模型权重可以只读共享，账号的原文、查询、向量、缓存键和结果必须隔离。

## 2 核 2GB、20 个账号的验收边界

20 个账号不等于 20 路重型任务同时执行。近期维持单任务队列、每账号配额、超时与取消；为 FastAPI 和操作系统留内存，解析和编码放开发机。启用在线本地编码前，单独测试进程冷启动、实际峰值 RSS、低 batch、1/2 路查询及后台导入共存时的延迟；不通过就保持纯词法在线路径。

向量体积只是下界：1 万条 384 维 float32 原始值约 14.6MiB，不含 SQLite/索引/缓存/段落和模型开销；20 个个人库的磁盘大小也不等于它们全部同时常驻 RAM。不能据此保证整台服务器内存够用。

后续实施前的验收建议：

- 检索：固定中英文、两字中文、缩写、否定、表格单位、扫描页、无相关答案等查询，人工标注相关段落；记录 Recall@k、MRR/nDCG、返回定位的正确率，以及无答案时的行为。现有 `benchmark_local_search.py` 只检查固定合成词的速度和结果一致性，不证明检索相关性。
- 解析：同一批原 PDF 比较现有 PyMuPDF/GROBID 与离线 Docling；覆盖双栏、页眉页脚、旋转、跨页表、扫描和公式；抽样页码/bbox/阅读顺序、表格单元格/单位。公开基准分数不直接转写为本项目准确率。
- 版本：同一 PDF 更换 parser/model/config 后生成独立产物；旧引文、学习记录、决策和快照仍能打开；旧索引可回滚，新索引可重建。
- 隔离：两个账号导入相同 PDF、相同段落序号也不能互查资料；离线回填、向量缓存、导出/删除和后台任务均延续个人空间；不能靠应用层 top-k 后再过滤掩盖跨账号检索。
- 资源：在目标容器记录总内存、进程峰值、p95 查询延迟、任务等待时间、失败/取消和磁盘增量；事先确定门槛，再决定是否选装 FastEmbed/sqlite-vec。

以上工具只改善解析、定位或检索。能找到页码、框住文字、复原表格、得到相似向量，均不证明实验条件可比、数值无误、引文蕴含候选结论或科研结论为真；继续沿用 `backend/app/pipeline/evidence.py` 的候选、引文检查与人工核验边界。

## 核查快照

下列默认分支提交 SHA 通过官方 GitHub API 读取；MIT/自定义/Apache 许可文件已实际打开，模型许可另按上文官方模型页核查。默认分支不是推荐安装版本；实施时应再锁 release、依赖和模型 revision。

| 仓库 | 本次读取的默认分支 SHA | 提交时间（UTC） |
| --- | --- | --- |
| [docling-project/docling](https://github.com/docling-project/docling/tree/0e54294231b69bc2cf7a39873235495788f76b57) | `0e54294231b69bc2cf7a39873235495788f76b57` | 2026-10-16 09:00:46 |
| [opendatalab/MinerU](https://github.com/opendatalab/MinerU/tree/b7f3dd0c5f6e6d66a298239ffd02b328b873918e) | `b7f3dd0c5f6e6d66a298239ffd02b328b873918e` | 2026-10-11 02:21:25 |
| [datalab-to/marker](https://github.com/datalab-to/marker/tree/ad1b414d846653f4048cdc527993f6c09b829869) | `ad1b414d846653f4048cdc527993f6c09b829869` | 2026-10-14 17:56:50 |
| [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec/tree/04d28bd21773981e2d266bbf6aa4efbd011eb4f6) | `04d28bd21773981e2d266bbf6aa4efbd011eb4f6` | 2026-05-18 06:50:43 |
| [qdrant/fastembed](https://github.com/qdrant/fastembed/tree/de502ca83baa2b81922cb5a46acf689f5e2c72a1) | `de502ca83baa2b81922cb5a46acf689f5e2c72a1` | 2026-10-15 13:08:54 |
