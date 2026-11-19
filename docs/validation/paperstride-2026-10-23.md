# PaperStride 验收记录 · 2026-10-23

## 环境与范围

Windows，本机 React/Vite `5173`、FastAPI `8000`、Python 3.11、SQLite。浏览器验收使用已安装 Chrome 和真实运行服务，账号数据与其他用户隔离。Neo4j 未启动，检查的是本地图谱降级路径。

## 已完成的验证

| 检查 | 结果与证据 |
|---|---|
| 后端集成回归 | `test_paperstride.py`、`test_personal_learning.py`、`test_workbench_services.py`、`test_reading_position.py`：48 项通过，183.61 秒。日志 `.tmp/paperstride-backend-final.log` |
| 最后一次证据生成修正 | 新增功能 9 项再次通过，21.41 秒。`.tmp/paperstride-focused-final.log` |
| 教学记录与课题开关收尾 | 新功能及个人学习回归 18 项通过，89.51 秒。`.tmp/paperstride-last-regression.log` |
| 科研条件比较 | 新机器人领域的相同、不同、缺失条件及既有两个领域回归共 35 项通过。`.tmp/paperstride-domain-tests.log` |
| 前端针对性回归 | ShellNavigation、Graph、project-graph、PaperReaderPosition：18 项通过。`.tmp/paperstride-front-final.log` |
| 阅读与导航收尾 | 新增课题开关之后再次执行阅读位置和导航回归，8 项通过。`.tmp/paperstride-last-front.log` |
| 账号管理 | 原测试在异步表单事件封装处超时；改用提交表单事件后，真实组件创建/停用请求测试通过，未提升超时门槛。`.tmp/paperstride-admin-test.log` |
| 生产构建 | TypeScript 与 Vite 构建通过。`.tmp/paperstride-build-final.log`；仍有主资源块大小提醒，不作为性能提升幅度的依据 |
| 真实用户流程 | 注册测试账号 → 打开三篇论文示例课题 → 阅读 → 编辑单元格 → CSV 下载 → 浏览器 Python → 保存实验解释 → 保存方案版本 → 探索。`.tmp/paperstride-browser.log` |
| 五个教学单元 | 每单元参考实现及边界检查实际执行通过；每单元错误代码被拒绝，小测产生反馈。无限循环在 5 秒后停止，主动停止保留代码。`.tmp/paperstride-lessons.log` |
| PDF 原文 | 等待 PDF 文本层实际渲染后验收，截图 `.tmp/paperstride-reading-rendered.png`；另有后端测试确认未解析的已保存 PDF 可读取 |
| 布局 | 深浅主题下矩阵分别检查 390、768、1440 宽度，页面无整体横向溢出；实践页检查三种宽度。截图 `.tmp/paperstride-matrix-<theme>-<width>.png`、`.tmp/paperstride-dark-<width>.png` |
| 功能开关 | 浏览器关闭课题学习和图谱支持后实践入口消失；后端拒绝关闭后的练习、图谱请求。恢复开关后可继续 |
| 数据与并发 | 单元格手改保护、候选缓存、列规则增量更新、409 冲突、历史、依赖循环、跨账号拒绝访问均由测试覆盖 |
| 课题范围与图谱收尾 | 新增课题来源隔离测试；PaperStride、本地图谱与批处理回归共 16 项通过，23.61 秒。`.tmp/paperstride-scope-final.log` |
| 在线引用画布 | 浏览器真实发现并显示 21 个节点、20 条有向引用元数据关系，没有页面错误。`.tmp/paperstride-citations.log` |
| 迁移恢复 | 四份升级前数据库复制到隔离目录，重复迁移不改变原表条数，全部 `integrity_check=ok`。`.tmp/paperstride-migration.json` |

## 在线服务实测

### 平台模型

默认 Qwen 的真实请求成功；最小连通检查返回 HTTP 200（0.656 秒）。最终证据矩阵接口真实返回 HTTP 200，保存待审核解释与服务器绑定的原文，模型阶段记录 **2.141 秒**。这仅是当次请求，不代表稳定响应时间或速度对比。

首次方案让模型返回引文，实测模型拼接了不连续文字，被校验拒绝并保留旧内容。最终方案改为从一段真实来源生成解释，由服务器提供来源文本与页码；未描述为整篇论文分析。失败、不自动重复付费请求、非法引文及缓存命中另有隔离 HTTP 测试。原始结果 `.tmp/paperstride-external.json`、`.tmp/paperstride-provider-check.json`。

### 文献与源码

Semantic Scholar 曾出现不可用路径，接口保留本地内容；后续真实请求成功返回 20 条参考文献，重复请求命中缓存。引用方向、分页参数、429 限流路径由隔离测试覆盖。实时后续引用的大规模检索及不同账号服务配额未进行负载测试。

固定源码 `5ba07ac6661db573af695b419a7947ecb704690f` 的三份文件真实读取为 HTTP 200：`base_lowdim_policy.py`、`diffusion_unet_lowdim_policy.py`、`eval.py`。加噪第 227 行、损失第 248 行、评估第 51 行等定位已核对。记录 `.tmp/paperstride-sources-verified.json`。

## 未作出的保证

- 未运行真实机器人、完整 GPU 训练、权重评测；教学成绩不是论文复现成功。
- 没有真实用户教学效果实验、与竞品的对照实验或生产规模压测；不宣称学习效果或服务速度优于竞品。
- 外部模型、文献网络与 Neo4j 部署的长期可用性未验证。
- 此次为针对性回归及浏览器验收，没有声称重新运行仓库全部历史测试。
- 当前模型候选只覆盖匹配的一段原文，仍需人工核对；未知项及不同实验条件不会被补为确定结论。
