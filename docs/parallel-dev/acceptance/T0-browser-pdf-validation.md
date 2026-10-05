# T0 浏览器与 PDF 实测记录

日期：2026-10-04。范围：隔离的合成验收数据、真实 Chromium 渲染与“打印为 PDF”；不连接生产数据库，不调用真实模型，不写 Neo4j/GROBID。

## 测试环境

- 数据目录：`evaluation/research_atlas/.tmp/browser-fixture-20261004-t6`
- fixture 清单：`browser-fixture.json`；`scientific_result=false`、`external_calls_made=false`
- 项目：`project-df7def7625e245c2b547b8df1b046d4c`
- 方案：`plan-ed09cc9deb964c04a0824a477fa389b6`，`source_kind=user_input`
- 快照：`snapshot-0291a25b57a344f0a85911ad700c683d`
- 临时后端：`127.0.0.1:18000`；临时前端：`127.0.0.1:15173`
- 浏览器：本机安装的 Google Chrome headless；临时代理配置在测试后删除。

## 实际执行与结果

1. fixture 生成测试通过，独立 SQLite 中包含一篇合成论文、一个已确认方法、两个独立实验设置、两条测量记录、用户决策、人工方案和不可变快照。
2. 通过前端代理读取项目与快照成功。页面截图中两个实验设置与测量值保持分离；资源、耗时和真实科研指标仍显示未知，没有被补造。
3. Chrome 实际渲染项目页与打印页，截图未见遮挡、越界或内容重叠。
4. Chrome 实际打印得到 2 页 PDF；文件大小 397886 bytes，SHA-256 为 `D5EE6C6DC72CD27678792A401F6424017E3F46D9C5E993C510D2557C5F04C9AC`，两页均有可提取文本。
5. PDF 规范化文本能够检出标题、目标、未知项、验证步骤、冻结引用，以及 `method-synthetic-probe`、`setting-synthetic-a`、`measurement-synthetic-a` 和 `synthetic-browser-document-001`。截图视觉显示中文正常。
6. 停止并重启后端后，从同一隔离数据目录读取相同快照和 JSON 导出成功：`contract_version=research-v1.1`、`frozen_project_version=2`、1 个冻结文档、4 个冻结事实、人工方案仍为 `user_input`。

证据文件：

- `.ui_validation/20261004-next-browser/project-page.png`
- `.ui_validation/20261004-next-browser/print-page.png`
- `.ui_validation/20261004-next-browser/research-snapshot.pdf`

## 限制与缺陷

- Windows CUA 初始化连续两次失败：`windows sandbox failed: helper_unknown_error: apply deny-read ACLs`。依照工具恢复规则停止重试，改用真实 Chrome headless。因此本轮验证了真实浏览器渲染、打印、API 读取和进程重启持久性，但没有完成鼠标/键盘驱动的人工编辑、保存、窄屏与刷新操作。
- PDF 视觉结果正常，但 Chrome PDF 文本层存在少量 CJK 兼容部首映射（例如“页面”“风险”的部分字形）以及长标识符内插空格。NFKC 后主要内容和关键引用可检出，但全文检索/无障碍文本质量仍需在 10—14 日使用目标演示机的“打印为 PDF”人工复核。
- 本轮没有把 mock/fixture 当作科学结果；没有真实模型调用、论文解析、图写入、训练或性能验证。

结论：浏览器渲染、隔离数据持久性、不可变 JSON 导出与真实 PDF 生成通过；交互式人工浏览器验收和 PDF 文本层质量仍未关闭，不能据此声明发布验证全部完成。
