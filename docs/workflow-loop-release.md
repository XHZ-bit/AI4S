# 统一学习与研究执行闭环

更新日期：2026-10-09。适用范围：本地单用户工作空间。

## 使用路径

1. 打开 `/workflow` 查看正式路线、论文阅读与理解回答、案例检查、课题快照步骤。首页和各工作区底部也显示当前活动摘要。
2. 在原页面阅读、回答或完成案例练习；统一任务清单从这些原始记录计算状态，不复制一份可漂移的进度。阅读、用户作答和固定题目检查通过分别显示来源与依据级别。
3. 课题方案保存后创建不可变快照，步骤才进入执行清单。在 `/workflow` 记录步骤产出；快照待复核时保留历史记录并暂停继续确认。
4. 在 `/workflow` 选择已有人工核验关系的概念或方法，填写理由，可选关联活动，再明确确认掌握；也可以记录理由后撤销。
5. 打开正式路线，先“预览调整”，检查复习建议、每周排期和沿用的完成记录，再“确认生成新路线版本”。旧路线保留在历史中。

## 数据与接口

- `GET /api/workflow/v1/overview`：四类状态计数、下一步活动和需要创建快照的方案数量。
- `GET /api/workflow/v1/activities?source_kind=&source_id=&project_id=&offset=&limit=`：活动分页。每项包含来源类型、来源 ID 与版本、状态、依据级别、原页面地址及证据 ID。
- `GET /api/workflow/v1/mastery`、`GET/POST /api/workflow/v1/mastery/{concept_uid}`：掌握记录。写请求需 `expected_version`、`action=confirm|revoke` 和理由；版本冲突返回 409。
- `GET/POST /api/workflow/v1/projects/{project_id}/snapshots/{snapshot_id}/steps/{step_id}`：课题步骤执行记录。写请求需 `expected_version`、`done`、`outcome`；完成必须提供产出，旧快照待复核时返回 409。
- `POST /api/roadmap/{id}/replan-preview`：请求体为 `expected_version`，返回新路线预览、输入指纹和排期摘要；不保存。
- `POST /api/roadmap/{id}/replan`：请求体为 `expected_version` 与预览返回的 `input_fingerprint`；重新计算后匹配才创建新路线，旧路线保持可读。重复提交返回 409。

增量 SQLite 表分别记录掌握操作及其历史、课题步骤操作及其历史、路线父子关系。旧路线 `done` 仍表示任务完成，升级不会把它写成掌握。论文和案例记录仍保存在既有表中。重新规划只使用当前 `human_verified` 且可定位的关系；原画像中的自由文本“已掌握概念”不会自动变成新掌握记录。

阅读估算沿用论文工作区的片段字数启发式，每段至少 5 分钟；固定练习复习暂按 15 分钟估算。其他无可靠时长的任务保留未排期状态。这些是排程辅助值，不是实测耗时。固定练习答对不自动确认概念掌握，课题步骤产出也不自动证明科学结论。

## 验证

从项目根目录运行：

```powershell
cd backend
python scripts/test.py -q
python -m ruff check app tests scripts
cd ../frontend
npm test
npm run build
```

隔离 Chromium 验收沿用 `docs/interactive-workspace-release.md` 的夹具与启动命令，现增加统一任务页、课题步骤填写、刷新后记录仍在的检查。夹具是合成资料；真实使用需要先由维护者核验相应知识关系。模型和 Neo4j 关闭时，活动投影、掌握记录、步骤记录及路线重排仍由 SQLite 支持。
