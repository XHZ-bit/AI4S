# PaperStride 1.0 · 知识图谱驱动的科研工作台

**Understand papers. Build your research.**

PaperStride 将资料、概念、方法、公式和依据组织到统一知识图谱中。围绕一个节点，可以回到原文、解释关系、查找前置知识、比较方法、运行 Python 教学练习并保存自己的学习状态。资料原文共享，各研究空间的修订独立保存；未归属空间的资料仍可从资料库图谱查看。

本版本面向 **Windows 本机单用户运行和受限评审交付**。源码包可在空数据目录生成原创合成演示，无需密钥、私人论文或已下载大模型。合成示例只展示软件流程，不代表模型准确率、科研效果或真人学习效果。

## 首次安装与演示

需要 Windows x64、PowerShell、curl，以及 Node.js 22.12 或更高版本。以下命令在解压后的项目根目录执行。首次安装需要联网下载固定 Python 和锁定依赖；后续演示使用本地依赖与生成的数据。

```powershell
# 安装项目内 Python 与前后端依赖；合成演示不需要额外 OCR 模型
.\scripts\setup-dependencies.ps1 -SkipParserModels

# 生成或复用独立演示库，并启动服务
.\demo.ps1 -Synthetic
```

打开 **http://127.0.0.1:5173**。选择演示研究空间，进入“知识图谱”。示例包含梯度、链式法则、高斯分布、线性残差和有界残差，以及可定位的原创 Markdown、公式、图像、比较和可运行练习。准确入口也保存在 `.demo/synthetic-data/demo-manifest.json` 的 `paths` 中。

```powershell
.\demo.ps1 -Synthetic -Action Check    # 只读检查数据与依赖
.\demo.ps1 -Synthetic -Action Status   # 查看运行状态
.\demo.ps1 -Synthetic -Action Stop     # 停止，保留数据和修改
.\demo.ps1 -Synthetic -Action Restart  # 重启后继续
```

重复准备不会重置用户修订、练习记录或旧快照。识别到旧版演示标记时，正常准备会增量补齐统一图谱；`Check` 不执行升级。未带有效演示标记的非空目录不会被覆盖。原有真实论文演示可继续用 `.\demo.ps1`，但首次准备需要已经存在的固定 PDF 缓存；发行包不分发这些论文。

安装缓存统一保存在项目的 `.tmp` 目录。安装脚本会在结束时恢复当前进程原有的缓存设置，适用于全局 npm 缓存不可写的受限账号。

准备依赖后，合成图谱、原文、参数演示、Python 运行、比较和保存可离线使用。外站教程、视频、公开链接导入和联网模型需要网络；离线时可继续阅读本地内容。PDF/Python 浏览器运行资源由安装和启动脚本从本地依赖准备，不通过 CDN 临时下载。详见[依赖安装与锁文件](docs/reproducible-dependencies.md)。

## 围绕图谱完成工作

1. **找到知识。** 首页或 `Ctrl/Cmd+K` 搜索节点、方法、公式及来源；主导航“知识图谱”可查看资料库与研究空间归属。
2. **导入与核对。** 在研究空间上传资料、关联已有论文或添加公开链接，原地查看分阶段分析进度。完成后查看新增知识，点击关系说明和依据回到原文。修订后刷新仍保留。
3. **按需学习。** 从目标节点进入前置路径、讲解、参数演示和练习。练习实际执行 Python，可输出表格、折线、柱状和散点；改变参数后需要重新运行。学习状态由本人选择，运行通过不会自动标记掌握。
4. **比较与追溯。** 选择两个方法，联动阅读比较表与关系视图，核对共同前置、机制和证据。未知条件保留未知，保存的比较可以再次打开。
5. **扩展阅读。** 节点资源按图片、论文、教程、代码和视频分类；原图保留图注和定位，视频点击后才加载，无法嵌入可前往原站。返回时保留当前学习位置。

节点提问围绕当前节点及相邻知识的来源组织回答，引用可以回到原文。原文明示、系统推断和用户补充分别标记；自动讲解、比较和笔记是关联成果，不自动成为已核验事实。公式识别、引文定位与程序测试通过均不能代替科学核验。

## 使用自己的资料

```powershell
# 首次使用可选择一个新的独立数据目录
.\start.ps1 -Mode Local -DataDir .local-data\research -Offline

# 默认资料库 backend/data；使用前确认这是目标目录
# .\start.ps1 -Mode Local -Offline

.\stop.ps1 -Mode Local
```

默认端口为前端 5173、后端 8000。`-DataDir` 区分真实资料与演示资料；`-BackendPort`、`-FrontendPort` 可指定空闲端口。启动器不会把其他数据目录的服务当作当前服务停止。`start.ps1` 不加 `-Mode Local` 会选择原有 Docker 模式，本轮参赛流程使用上述 Local 命令。

`kw_*` 是活跃知识的主存储；旧接口通过兼容层读取统一知识。Neo4j 不决定主图谱结果，也不是审核成功的前提。旧研究方案与冻结快照保留其历史版本含义。迁移不调用模型，不能凭缺失的原文件制造证据；具体升级与回退见[1.0 升级说明](docs/unified-release.md)。

## 模型与解析边界

无密钥可以启动、阅读、运行演示和维护知识。`-Offline` 会禁用平台模型；`.\demo.ps1 -Synthetic` 使用隔离的离线配置。需要模型辅助抽取、深入讲解或生成练习时，再通过环境配置提供 `DASHSCOPE_API_KEY`、`LLM_API_BASE`、`LLM_MODEL`，并按资料外发范围设置模型开关。**不要将密钥写入源码或发行包。**

知识服务默认单次分析最多 16 次请求（可配置），深入学习和练习各最多 4 次，比较最多 8 次，节点提问最多 1 次；请求会记录用量，不自动无限重试。总费用取决于输入长度、服务商及具体操作，调用上限不等于固定价格。`RESEARCH_MODEL_ENABLED` 控制旧研究方案模型流程，`KNOWLEDGE_MODEL_ENABLED` 控制知识工作台；离线配置会同时关闭它们。

Markdown、代码和结构化文件可直接解析。复杂 PDF 的版面、OCR 与公式识别需要相应解析资源；可再次运行 `.\scripts\setup-dependencies.ps1` 准备默认解析模型。无 GPU 的本机可使用基础文本流程，实际耗时取决于文件和硬件。MiniCPM-OCR 与其他已下载权重不包含在软件包中，也不是启动合成演示的前置条件。

## 检查、故障与恢复

```powershell
# 后端回归：临时目录限制在工作区内
backend\.venv\Scripts\python.exe backend\scripts\test.py -q

# 前端测试与正式构建
Push-Location frontend
npm test
npm run build
Pop-Location
```

- **缺少依赖或启动失败：** 先运行 `start.ps1 -Mode Local -Check`；查看启动输出及 `.tmp/run/<后端端口>/`，按提示补齐依赖。只有系统代理不可用时才显式尝试安装脚本的 `-Direct`。
- **未生成深入内容：** 核对模型配置、阶段错误与来源完整性；基础原文与已保存成果仍可查看。不要将无密钥基础内容当作模型抽取成功。
- **演示校验失败：** 保留原目录，检查标记、来源文件与哈希。不要清空目录；需要新演示时为 `demo.ps1 -Synthetic -DataDir` 指定新的仓库内目录。
- **更新前备份：** 先停服务，使用 `backend/scripts/data_archive.py` 备份并校验资料目录。恢复到新目录后，启动前必须执行 `migrate_knowledge_workspace.py --data-dir <恢复目标> --relocate-from <原数据目录>`，校验原件哈希并重定位资产，再核对和切换。完整命令及本机标准备份见[本地数据恢复](docs/local-data-recovery.md)。整站账号恢复另见[多人备份说明](docs/multiuser-backup-recovery.md)。

## 软件交付

版本号为 **1.0.0**。打包入口为 `scripts/package_release.py`，生成源码 ZIP、逐文件 SHA-256 清单和包校验信息；具体发行物与实测验收以[当前交付说明](docs/unified-release.md)及随包验收记录为准。包内不含真实数据库、个人论文、凭据、模型权重、依赖目录、备份或正式参赛报告/PPT/视频。

本轮不新增公网部署。自研开源许可证尚未选择，受限评审源码交付不等于获得公开再分发许可；依赖声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。打包与本地验收不等于已在比赛后台提交。

开发结构：`backend/app/knowledge/` 为统一知识服务；`frontend/src/components/knowledge/` 为图谱、学习、比较和练习；`backend/tests/` 与 `frontend/src/__tests__/` 为回归；`scripts/` 为安装、运行和打包工具。资料、正式材料、依赖与归档的用途见[工作区文件索引](docs/workspace-layout.md)。历史迭代说明与旧 README 已移出主使用流程，仅在本机历史归档中保留，不随当前源码包分发。
