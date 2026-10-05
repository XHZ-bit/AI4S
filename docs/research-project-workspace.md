# 课题工作台使用说明

本说明对应 `research-v1.1`。课题工作台是原单篇论文学习功能的增量扩展；旧论文、学习记录、路线和 Diffusion Policy 案例仍使用原入口与数据。

## 启动与数据安全

生产或演示前先备份 SQLite 数据库和原始资料目录。数据库升级只允许新增 research 表；不要清空数据卷，也不要把测试的 `DATA_DIR` 指向正在使用的数据目录。Neo4j 是可重建投影，不是事实真源，恢复时以 SQLite 和原始资料为准。

```powershell
.\start.ps1
```

打开 `http://localhost:5173/research`。后端 API 基础路径是 `/api/projects`。配置示例位于根目录 `.env.example`；凭据只通过环境变量提供，不能写入仓库。

## 用户流程

1. 在“科研课题”中新建课题，选择图像异常检测或时间序列预测，并填写目标、指标及资源约束。保存后每次修改都携带项目版本；409 表示内容已被其他写入更新，需要刷新后人工合并。
2. 关联资料库中已有论文。每个关联冻结具体 `document_id`、文档版本和内容哈希；移除关联是软移除，不删除论文或历史快照。
3. 对关联文档启动候选抽取。方法、实验设置和测量分开保存；同名方法可有多个设置。表格只保留待人工处理的定位，不自动采信数值。
4. 逐项核对候选并选择确认、争议或撤回。`literature_report`、`user_input`、`model_suggestion` 不能混写；`unknown`、`not_found`、`not_parsed`、`conflicting`、`reported` 含义不同。
5. 选择设置做条件比较。只有数据集、划分、评估协议、指标范围等条件兼容的组才可比较；不可比原因会显示，系统不生成跨组排名。
6. 用户保存路线决策。决策记录选中与考虑过的候选、理由、证据和事实版本，不由模型替用户作最终选择。
7. 生成方案草稿、人工编辑并保存，然后创建不可变快照。当前外部方案生成 provider 尚未授权接入，因此新生成任务会明确失败；此时可选择“人工创建空白草稿”，其来源固定为 `user_input`，除已选方法/实验设置 ID 外不会预填科学内容。已保存方案与快照仍可浏览。自动测试中的 provider 是本地 fake，不代表真实模型可用。
8. 从历史页查看方案与依据。快照可导出 JSON 或 Markdown；打印页使用浏览器“打印/另存为 PDF”。事实、证据、项目条件或论文关联变化后，受影响快照显示 `needs_review`，旧内容不会被重写。

## 图投影与恢复

创建快照后，系统把该快照排入 Neo4j 投影任务。投影失败不会回滚 SQLite 快照；界面显示失败原因，并可通过快照的“重试图投影”入口创建新任务。图查询始终限定 `project_id + snapshot_id`，不会把当前事实与历史快照混在一起。

## 开发验收

以下命令不会调用真实模型或真实 Neo4j；测试使用临时 SQLite 和显式 mock：

```powershell
cd backend
python -m pytest -q --basetemp=.pytest_tmp_release
python -m ruff check app tests scripts
cd ../frontend
npm test -- --run
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File evaluation/research_atlas/run_acceptance.ps1
```

需要准备浏览器人工验收数据时，必须指定一个全新或空的隔离目录；脚本会拒绝 `backend/data` 和非空目录：

```powershell
python evaluation\research_atlas\prepare_browser_fixture.py --output-dir D:\tmp\research-atlas-browser-fixture
```

2026-10-04 已用真实 Chrome headless 对该合成 fixture 完成页面渲染和 2 页 PDF 生成，并验证后端重启后快照/JSON 导出仍可读取。该结果不是鼠标键盘驱动的人工端到端：Windows CUA 因 ACL 初始化失败，窄屏、刷新恢复和交互式编辑仍待目标演示机复核；Chrome PDF 文本层另有少量 CJK 兼容部首映射和长标识符内插空格。详情见 `docs/parallel-dev/acceptance/T0-browser-pdf-validation.md`。真实模型、认证 Neo4j 写入、GROBID 真实 PDF 解析和断网部署仍须在隔离环境单独验收。

## 当前发布判断

最新真实验收见 `docs/parallel-dev/acceptance/T0-live-validation-20261004.md`。浏览器交互、PDF 文本层、隔离 Neo4j/GROBID 与离线读取导出已有实测；真实模型调用发现方法名质量问题，未进入确认事实。原生 CUA 工具故障仍在，浏览器由 Playwright 驱动。前文截至上一轮的“待验证”列表按此记录更新。

公共接线、人工方案 fallback、临时数据库模块组合流程和旧功能回归已通过，核心代码达到冻结门槛。真实方案生成 provider、真实服务和浏览器人工全流程仍未验证，因此当前不是“完整发布 READY”，也不能把 mock 端到端结果称为真实端到端验证。
