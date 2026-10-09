# Research Atlas 交互工作空间交付说明

更新日期：2026-10-08。

## 本轮交付

| 入口 | 体验 | 数据边界 |
| --- | --- | --- |
| 首页 | 继续上次任务、最近论文、研究与学习入口 | 最近位置保存在本机浏览器 |
| 课题 → 联动画布 | 稳定节点位置、局部展开、返回焦点、筛选与来源检查器 | 当前关系直接读取 SQLite，不要求 Neo4j 在线 |
| 课题 → 资源推演 | 最多四种情景、显存/设备/时间/费用控件、数据与指标范围、候选矩阵和用量条 | 服务端统一检查；预览不保存到正式约束或决策 |
| 论文 / 来源检查器 | PDF 页码、缩放、文字选择、唯一原句高亮；版本不匹配时显示抽取文字 | 本地打包 PDF.js worker、字体、CMap 和 WASM；同时最多渲染三页 |
| 案例 → 交互实验室 | 张量形状、可暂停/单步/重置的时间窗口、固定源码定位、自动练习 | 动画为教学示意，不执行策略或宣称科研效果 |
| 来源与教练 → 下一步 | 自动发现字段缺失、失效引用、条件冲突和版本影响；学习建议随记录更新 | 规则计算不调用模型；论文/案例最多三项建议 |
| 课题 → 变化解释 | 当前与快照、两个历史快照的字段及步骤差分、受影响成果 | 读取 SQLite 历史版本；历史缺失明确列出 |

工作空间采用浅色画布、深色导航和青蓝强调。宽屏检查器可拖动或用方向键调整至 280–480px；中等屏幕使用侧边面板，手机使用底部导航与详情面板。支持可见键盘焦点和系统减少动态效果设置。

选择、页码、视图通过 URL 分享及前进/后退恢复；画布坐标、缩放、最近位置、动画参数和草稿保存在本地。页面刷新保留草稿，明确显示“本地草稿”与“服务端已保存”。版本冲突保留作答和输入，重新加载版本后可以重试。

本轮没有新增人工验证流程。原有资料状态继续显示；候选可以直接参与分析，“匹配”只表示已报告需求满足当前条件。

## 接口与一致性

新增 `assistant-v1`，保留 `research-v1.1` 的既有字段语义。

| 接口 | 返回或行为 |
| --- | --- |
| `GET /api/projects/{id}/insights` | 自动体检、候选检查、行动及来源引用、输入指纹 |
| `GET /api/projects/{id}/canvas` | 当前 SQLite 引用关系，独立于 Neo4j 投影 |
| `POST /api/projects/{id}/scenarios/evaluate` | 1–4 个情景与基准比较；项目版本或指纹失效返回 409 |
| `GET /api/projects/{id}/snapshots/{sid}/diff?against=current或快照ID` | 字段、约束、步骤变化与影响范围 |
| `GET /api/learning/papers/{uid}/coach` | 论文学习建议 |
| `GET /api/cases/{id}/sessions/{sid}/coach` | 案例建议、练习及已保存结果 |
| `POST /api/cases/{id}/sessions/{sid}/practice/{exercise_id}/answers` | 服务端判题和会话版本锁；冲突返回 409 |
| `GET /api/resources?scope=project或paper或case&id=…` | 来源、版本、适用任务及内容目录，附输入指纹 |
| `GET /api/papers/{uid}/documents/{did}/file` | 文档身份与原文件 SHA-256 校验；缺失 404、版本不匹配 409 |
| `POST /api/assistant/explain` | 按需解释既有行动；每个请求最多一次模型调用 |

情景输入立即显示，250ms 后计算，取消过期请求，期间保留上次结果并标为待更新。资源缺失、不可靠字段或无法换算的单位保持未知；不把多个设备配置拆散组合。时间和内存按固定单位换算，费用只比较同币种，前端不另做适配结论。

练习使用现有会话 JSON：`practice` 保存各题最新结果，`practice_history` 追加改变的作答记录。旧会话缺失字段默认为空。相同作答重复提交不增加尝试次数和练习历史；仍需提交当前会话版本。读过、原有理解题、交互练习与源码检查分别记录。

模型沿用现有 `RESEARCH_MODEL_ENABLED`，默认关闭。模型解释不能改写规则结果或成绩；指纹过期、返回陌生行动或结构异常会明确失败。关闭模型时本轮核心功能正常使用。这里的离线指不依赖外部模型和图数据库；浏览器仍需连接本地后端，不包含 PWA 全站断网缓存。

## 三条连续演示

1. 打开课题的资源推演，设置显存上限，添加至四种情景，查看候选从冲突变为匹配或信息不足；正式课题约束保持原值。
2. 返回联动画布，点击可阅读依据路径或证据节点，在检查器定位 PDF 原页；修改页码、刷新、前进/后退后，选择与页码仍保留。
3. 打开 Diffusion Policy 案例，新建学习记录，修改张量参数，播放或单步时间窗口；提交练习后查看服务端反馈与更新后的教练建议。

## 自动验证与复现

后端隔离测试和静态检查：

```powershell
cd backend
python scripts/test.py -q
python -m ruff check app scripts tests
```

前端隔离测试与生产构建：

```powershell
cd frontend
npm ci
npm test
npm run build
```

从仓库根目录运行真实浏览器验收，需安装 Playwright Chromium。夹具只能写入新的独立目录，不使用生产数据：

```powershell
python evaluation/research_atlas/prepare_interaction_fixture.py --output-dir .ui_validation/interaction-demo
$env:ATLAS_PLAYWRIGHT_PATH = "$PWD/frontend/node_modules/playwright"
$env:ATLAS_PYTHON = "python"
node evaluation/research_atlas/run_assistant_browser.cjs .ui_validation/interaction-demo
```

准备浏览器依赖可在 `frontend` 执行 `npm install --no-save --package-lock=false playwright` 与 `npx playwright install chromium`。验收脚本在一个进程树启动隔离后端、Vite 和浏览器，完成后停止服务器；输出截图与 `assistant-browser.json`。测试使用合成资料，不产生真实科研结果，浏览器阻止外网资源。

已加入 `.github/workflows/ci.yml`，Windows / Linux 均执行后端、Ruff、前端、生产构建和 Chromium 验收，并上传截图与测量 JSON。远端 CI 尚未触发执行。

### 本地验收记录

- 后端：271 项测试通过；Ruff 通过。
- 前端：45 项测试通过；TypeScript 与生产构建通过；依赖审计 0 项漏洞。
- Chromium：三条连续路径、浏览器返回选择、刷新恢复、390 / 768 / 1440px 的案例/课题/论文均无页面横向溢出；键盘与减少动态效果断言通过；页面异常为 0。
- 降级：无模型、无 Neo4j、缺失/版本不匹配 PDF、损坏 PDF 文字回退、缺失来源与 SQLite 历史缺失均有自动覆盖。损坏 PDF 浏览器检查采用本地故障注入，缺失和哈希不匹配由接口测试覆盖。
- 反馈从输入或按钮点击事件记录到下一次 `requestAnimationFrame`，是本地反馈基准代理，不能等同正式 INP。网络资源完成耗时另存 `network_ms`，不计入该反馈指标。本地 35 次输入与点击反馈 P95 为 171.1ms，样本见验收 JSON。

最新本地产物目录：`.ui_validation/assistant-final/`。该目录为忽略的测试产物；工作流会生成同结构的 CI 附件。

快照差分比较冻结输入集合与当前资料集合。“added”表示该项未包含在快照冻结范围内，不能据此推断其实际创建时间；这不是项目全局事件审计。

PDF 扫描件可能没有可选择文字；未进行 OCR。只有可靠页码和匹配版本才定位原页，仅有章节时显示抽取文字，不制造精确高亮。PDF.js 按需加载，首屏不加载 PDF 引擎及 worker。

实现参考：[PDF.js 官方示例](https://mozilla.github.io/pdf.js/examples/index.html)、[交互响应指标说明](https://web.dev/articles/inp)。
