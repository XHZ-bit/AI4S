# Research Atlas · 知识图谱驱动的科研方案工作台

Research Atlas 同时保留原有单篇论文学习工作台，并新增课题工作流：**建立课题 → 关联多篇论文 → 提取并确认方法与实验条件 → 比较候选 → 用户选定路线 → 编辑、保存和导出首轮验证方案**。原文证据与知识图谱提供上下文，但来源可定位不代表科学结论正确。

课题工作台使用方法见 [课题工作台使用说明](docs/research-project-workspace.md)，原学习工作台边界见 [科研工作台说明](docs/research-workspace-release.md)。真实集成状态见 [集成检查清单](docs/parallel-dev/02-integration-checklist.md)。早期原型文档中的测试数量、自动合并和创新信号描述不代表当前发布行为。

## 已提供

2026-10-04 真实验证已覆盖 Chrome 编辑/保存/刷新/窄屏/离线草稿恢复、PDF 文本与版式、隔离 Neo4j 认证写入查询及 GROBID 合成 PDF 解析。真实 Qwen 调用成功但方法名质量门槛失败；之后已实现默认关闭的生产方案 provider 与抽取防护，但尚未重新进行真实模型质量验收。历史记录见[真实验收记录](docs/parallel-dev/acceptance/T0-live-validation-20261004.md)，新增实现和测试边界见[T0 交接](docs/parallel-dev/handoffs/T0.md)。

- PDF 持久化上传、后台全文解析、证据定位、候选质量检查与维护者核验。
- 论文阅读任务、辅助解读、理解回答、实验记录、研究问题与跨论文证据比较。
- 后台任务中心、失败重试、路线历史、并发进度保护和图谱探索。
- 课题、论文关联、方法卡、独立实验设置与测量、字段级证据、人工决策、可编辑方案和不可变快照。
- 按数据集、划分、协议和指标范围分组的条件比较；条件不兼容时不跨组排名。
- JSON / Markdown 快照导出和浏览器打印页；证据或事实变化后标记既有快照待复核。
- 人工标注与用户试用记录工具；没有假定这些真实评测已完成。

## 启动

使用现有 Docker Compose：

```powershell
.\start.ps1
```

服务地址：前端 http://localhost:5173，后端 http://localhost:8000。
模型凭据使用系统环境变量 DASHSCOPE_API_KEY。不要把密钥提交到仓库。
缺少模型服务时仍可浏览已保存原文、课题、事实、方案和快照。Research 候选抽取与方案生成默认关闭外发；任务明确失败，不返回预置成功草稿。用户可改用“人工创建空白草稿”，以 `user_input` 来源编辑、保存、创建快照和导出。旧学习辅助功能保持原调用方式，本开关不是全站离线开关。

### 比赛版模型接入（默认关闭）

先批准供应商、资料范围与费用上限，再在运行环境配置下表；不需要修改或展示密钥文件。本轮实现没有代为开启真实调用。

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `RESEARCH_MODEL_ENABLED` | `false` | 审批后设为 `true`，开启 Research 抽取和方案生成 |
| `RESEARCH_MODEL_RESPONSE_FORMAT` | `json_object` | 仅在目标模型确实支持时选 `json_schema`；失败不静默切换 |
| `RESEARCH_MODEL_TIMEOUT_SECONDS` | `60` | HTTP 超时及流读取时间检查 |
| `RESEARCH_MODEL_MAX_OUTPUT_TOKENS` | `2048` | 供应商输出参数，不是总推理 token 或金额的硬上限 |
| `RESEARCH_MODEL_MAX_INPUT_CHARS` | `60000` | 单请求消息 JSON 字符上限，超限明确失败 |
| `RESEARCH_MODEL_MAX_REQUESTS` | `16` | 每个后台 Research 任务的最多请求数；无自动付费重试 |

模型沿用 `LLM_MODEL` / `LLM_API_BASE` / `DASHSCOPE_API_KEY`。配置变更需重启相应后端；本次没有重启生产服务或升级生产数据库。
抽取会发送单个正文片段及定位元数据；方案生成会发送课题约束、用户选择、所选事实和绑定的证据片段。
默认日志只含调用 ID、任务 ID、模型与提示词/Schema 版本、耗时、状态及供应商实际返回用量，不含正文、输出或密钥。
预算限制针对单任务请求，不是账户月账单限额；重复创建任务仍会产生新费用。真实评测前另行批准金额与样本量。

成功结果仍为 `model_suggestion` 草稿，必须人工确认；JSON 合法和引用存在不证明科学结论正确。
模型超时、截断、空建议、非法结构、陌生证据和已识别危险步骤会令生成任务失败；已保存方案保持可读。
当前没有用户取消运行中模型请求的 API；后台重启中断语义沿用原实现。

### 比赛演示与开放边界

打开 `/research`：建立异常检测课题 → 关联资料 → 核对候选与原文 → 比较条件 → 人工选择 → 编辑保存方案 → 创建快照 → PDF/JSON 导出 → 修改依据并查看待复核提示。
无模型演示必须标注人工路径；合成测试不可宣称真实科研效果。时间序列作为跨领域验证，不把异协议成绩直接排名。
报告正文建议 15 页以内、PDF ≤10MB；视频 MP4 3—5 分钟、≤300MB。开放成果计划包括核心源码和评测工具，但项目 LICENSE、依赖义务与持续有效链接仍待权利人审批，当前不声称已完成开源发布。
不分发凭据、生产数据、未经授权的论文全文或权重；PyMuPDF 等依赖的许可必须按实际发行物核查，不能直接给全部内容套用 MIT。

本地开发：

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --port 8000
```

另开终端：

```powershell
cd frontend
npm install
npm run dev
```

Neo4j 和 GROBID 按 docker-compose.yml 配置启动。当前为单机模式，维护者入口分流不是账号权限隔离。
课题入口为 http://localhost:5173/research 。开发测试必须把 `DATA_DIR` 指向独立临时目录，不能复用生产数据目录。

## 验证

```powershell
cd backend
python -m pytest -q --basetemp=.pytest_tmp_release
python -m ruff check app tests scripts
cd ../frontend
npm test
npm run build
```

没有已核验种子知识时，平台不会编造正式先修路线；可以先进入论文工作区阅读和记录。真实领域核验、GPU 实验和新手试用仍需要对应人员完成。

本仓库的自动验收使用临时 SQLite、模拟模型和模拟图服务。它证明模块与错误路径可组合运行，不等于真实模型、真实 Neo4j、真实论文有效性或浏览器人工验收已经完成。

## 工作区清理与代码边界

从项目根目录运行（先停止其他窗口的测试，避免删除正在使用的测试目录）：

```powershell
# 默认只列出可再生成的缓存与测试临时目录，不删除
./scripts/clean-workspace.ps1
# 核对预览后执行
./scripts/clean-workspace.ps1 -Apply
```

白名单仅包含 pytest/Ruff 缓存、`backend/.pytest_tmp*` / `.pytest-tmp`、后端源码与测试的 `__pycache__`、前端 `tsconfig.tsbuildinfo`。
脚本验证绝对路径与链接边界，拒绝越界或含目录链接的目标；每次删除保留 `.local-backups/cleanup-*.json` 清单。
`-ArchiveLegacyPlans` 可额外归档并移除 4 份 2026-09-21 旧分阶段实施草稿，归档逐文件 SHA256 校验通过后才删除。
2026-10-04 已执行该清理，恢复旧草稿时从 `.local-backups/retired-plans-20261004-235743-787.zip` 提取指定文件到其原相对路径，不覆盖现有源码。
原始设计、当前契约、验收记录、交接记录和源码备份不是临时草稿；用户数据、浏览器资料、依赖目录、Docker 卷不在清理范围。

方案模块遵循单向依赖：`planning`（纯内容组装）和 `plan_provider`（模型适配）共同使用 `suggestion_validation`（纯结构/证据/内容校验）；
provider 不再导入 planning 私有函数。业务持久化仍由 service/存储层负责，公共 `research-v1.1` 契约没有改变。
详见 [T0 清理与修复记录](docs/parallel-dev/handoffs/T0.md)。无 Git 的恢复风险仍存在；清理脚本不会初始化 Git 或删除恢复副本。


## 新增源码入门案例
打开 http://localhost:5173/cases/diffusion-policy-intro ，无需模型 API 即可开始固定源码教学。支持理解反馈、本机检查结果导入和报告下载；源码检查不代表模型复现。
- [具体实施计划](docs/implementation-oct07.md)
- [本机教学使用说明](docs/case-study-guide.md)
- [专题来源与许可](docs/third-party-case-resources.md)

本机代理可在 .env 设置 ATLAS_HTTP_PROXY / ATLAS_HTTPS_PROXY；Docker 容器使用 host.docker.internal 访问宿主机代理。配置同时用于依赖构建和后台联网，内部服务直连。不要提交 .env。启动失败会返回错误，需检查日志。
