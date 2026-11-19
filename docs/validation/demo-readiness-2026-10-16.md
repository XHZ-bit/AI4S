# 本地演示验收记录（2026-10-16）

结论：本机离线功能演示已具备独立资料、启停入口及可复跑的浏览器验收。三篇固定真实论文用于原文与候选路线预览；课题、实验条件和方案示例明确标识为合成资料及人工输入。本次没有调用付费模型。

机器摘要见 [demo-readiness-2026-10-16.json](demo-readiness-2026-10-16.json)。原始日志、截图与导出样本位于仓库的 `.ui_validation/demo-readiness-20261016/`。

## 使用

在项目根目录 PowerShell 中执行：

```powershell
.\demo.ps1
.\demo.ps1 -Action Status
.\demo.ps1 -Action Restart
.\demo.ps1 -Action Stop
```

前端为 `http://127.0.0.1:5173`，API 为 `http://127.0.0.1:8000`。首次准备需要前后端依赖及已缓存的三篇固定 PDF。脚本不自动联网获取资料；需要时用 `-PdfDir` 指定缓存位置。已准备的演示库无需原缓存即可重复启动。

默认演示数据位于 `.demo/data`，包括三篇真实论文、一篇合成资料、五条候选关系、一个合成课题、人工方案及快照。它与 `backend/data`、Docker 卷和旧演示库独立。重复 Prepare/Start 保留使用中的修改、学习记录及新增论文；损坏的必需资料或非演示的非空目录会明确失败，不重新填充覆盖。

首页“体验个性化路线”进入双画像预览；“进入科研课题”进入合成课题。完整性校验使用 `-Action Check`，仅准备数据使用 `-Action Prepare`。

## 已修复

1. **测试进度不可见。** Vitest 5 在代理环境默认选择精简报告器，健康运行时也可能只显示 RUN。现显式使用常规报告器，CI 保留 GitHub Actions 报告。
2. **首页测试时序问题。** 原测试为状态接口返回论文列表结构，异步渲染偶发崩溃。现按接口提供正确 fixture，并等待状态及任务摘要加载；没有跳过测试或放宽原断言。
3. **备份恢复路径解析。** Windows 受限环境能正常读写及获取元数据，但严格句柄路径解析报 WinError 5。现逐级检查存在性与链接元数据，拒绝 symlink、junction 和其他 reparse point；通过文件系统身份检查阻止短路径别名绕过目录边界。新增 12 项回归。
4. **启停依赖与离线配置。** 端口检查和进程停止不再依赖受限的 CIM；停止前核对 PID 与创建时间。离线启动不读取项目 `.env`，Demo Start 拒绝复用其他运行配置，临时环境变量在调用后恢复。
5. **手机端长标题。** 390px 方案页曾被版本选择器撑到 512px。现选择器有界收缩、选中标题省略、展开项换行；未使用全局隐藏溢出掩盖问题。

## 验收结果

| 验收 | 结果 | 本地原始记录 |
|---|---|---|
| 后端完整回归 | 342 项通过，退出码 0 | `backend-final.txt` |
| 备份恢复及路径边界 | 15 项通过 | `backend-archive-tests.txt` |
| 演示准备保护与保留记录 | 11 项通过，包含于后端完整回归 | `backend-final.txt` |
| 前端完整回归 | 19 文件、56 项通过 | `frontend-test-final.log` |
| TypeScript 与生产构建 | 通过 | `frontend-build.log` |
| Python 全量 Ruff | 通过 | `ruff-all.txt` |
| 新增真实 Chrome 走查 | 16 项通过，无非预期页面错误 | `browser-release/demo-browser.json` |
| 既有平台真实 Chrome 回归 | 10 项通过 | `platform/platform-browser.json` |
| Demo 启停及数据保留 | 9 项通过 | `runtime-check.json` |
| 原有 Local 启停回归 | 3 项通过 | `local-runtime/runtime-check.json` |
| 主机交付地址复核 | 独立进程及真实浏览器 3 项通过 | `host-runtime.json`、`demo-home.png` |
| 导出 PDF | 2 页，逐页渲染及目视检查通过 | `browser-release/snapshot.pdf`、`pdf-page-1.png`、`pdf-page-2.png` |

新增浏览器流程使用真实 Chrome 155、真实本地 API 和隔离 SQLite，阻断外网访问，不替换业务接口响应。覆盖双画像差异、画像修改重算、原文弹窗、论文跳转和 PDF 渲染、未保存草稿刷新恢复、保存刷新、创建快照、实际下载 JSON/Markdown、打印 PDF、旧快照冻结内容保持不变及待复核标记更新、投影尺寸与窄屏、长版本名称展开可读。

既有平台回归覆盖自有 PDF 上传、解析覆盖提示、阅读和掌握分离、行动清单版本、重启恢复、来源变化、局部失败、步骤产出、任务中心、断网恢复与手机布局。以上测试数据为合成资料。

PDF 由 Chrome 的打印页生成，再使用 Poppler 渲染两页核查。中文、步骤和冻结引用可读，未见裁切或文字重叠。导出样本与浏览器修改均保存在隔离验收库；交付的 `.demo/data` 保留初始示例。

## 复跑

以下目录必须是新的空目录。验收脚本使用独立端口并在结束后停止测试服务，不占用默认演示端口。

```powershell
python backend/scripts/test.py -q
python -m ruff check backend/app backend/tests backend/scripts evaluation/research_atlas
cd frontend
npm test
npm run build
cd ..
python backend/scripts/prepare_demo.py --data-dir .ui_validation/demo-replay/data --pdf-dir .demo/data/pdfs
node evaluation/research_atlas/run_demo_browser.cjs .ui_validation/demo-replay/data .ui_validation/demo-replay/evidence
python evaluation/research_atlas/prepare_platform_fixture.py --output-dir .ui_validation/platform-replay
$env:ATLAS_PLAYWRIGHT_PATH = (Resolve-Path frontend/node_modules/playwright).Path
$env:ATLAS_CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
node evaluation/research_atlas/run_platform_browser.cjs .ui_validation/platform-replay
powershell -ExecutionPolicy Bypass -File evaluation/research_atlas/check_local_runtime.ps1
```

浏览器验收需要已安装的 Playwright 和 Chrome，可用 `ATLAS_CHROME_PATH` 指定其他 Chrome/Chromium 路径。

## 边界与环境记录

- 演示使用本地 PyMuPDF，不执行 OCR。模型关闭；Neo4j 快照投影不可用时按设计显示提示，方案、快照和导出仍可用。该预期降级单独记录，不算作图服务验收通过。
- 先修关系仍是演示教学假设，自动检查不证明语义正确或真实学习效果。科研性能、模型质量和真实用户效果不在本次验收范围。
- 内置浏览器控制工具因 Windows 沙箱 ACL 初始化失败，本次使用可运行的真实 Chrome/Playwright完成交互及截图，不把 jsdom 结果作为浏览器证据。
- 沙箱内部分测试日志包含 Anaconda 路径定位及 `pyreadline3` 退出警告；测试退出码均为 0，原始警告保留。
- 曾出现的验收脚本接口路径、下载临时目录、快照复核字段和选择器定位假设均已纠正。失败尝试保留在相邻目录，最终结论仅引用 `browser-release/demo-browser.json`。
