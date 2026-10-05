# 本次实现验证记录

日期：2026-09-30

- 后端：95 项测试全部通过（隔离 SQLite、模拟 HTTP/模型/图数据库边界）。
- 前端：5 个测试文件、7 项行为测试全部通过。
- Python 静态检查：ruff check app tests scripts 通过。
- 前端生产构建：TypeScript + Vite 通过。
- 本地服务：/health、/api/learning/tasks、前端首页均返回 HTTP 200；临时验证服务已停止，使用独立数据目录。
- 浏览器视觉验证：未完成，工具在启动时遇到 Windows 沙箱 apply deny-read ACLs 错误。
- 真实 Neo4j 联调：未完成，本机 Python 环境缺少 neo4j 驱动；项目依赖声明已包含它，部署需安装项目依赖或重建容器。
- 真实模型、GROBID、GPU 复现实测和用户对照试用：未执行，不由上述自动化测试替代。
- 自动知识发布：保持关闭；未宣称达到 95% 的知识准确率。

人工工作包位于本目录：quality-labels.jsonl 为 200 个待标注槽位，seed-review.json 为 20 篇资料待核验清单，user-trials.csv 为 8 名参与者的交叉顺序记录表。它们是未填写的工作表，不是真实评测结果。
