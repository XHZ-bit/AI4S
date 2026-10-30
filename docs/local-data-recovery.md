# 本地数据备份与任务恢复

适用范围：单机单用户。备份包含 `DATA_DIR/atlas.db` 和同一目录下的普通文件（包括 `pdfs/`）；SQLite WAL/SHM 临时文件由在线备份生成的数据库快照替代。备份包有文件大小、SHA-256 和 SQLite 完整性检查。命令不会覆盖已有备份或恢复目标。

## 备份与恢复

从项目根目录运行。为保证数据库记录与 PDF 文件处于同一操作时段，建议先停止前后端和后台任务，再执行备份；运行中的 SQLite 数据库本身可生成一致快照，但多个独立文件不能由 SQLite 保证为同一事务。

```powershell
backend\.venv\Scripts\python.exe backend\scripts\data_archive.py backup --data-dir backend/data --output .local-backups/atlas-data-new-backup.zip
backend\.venv\Scripts\python.exe backend\scripts\data_archive.py verify --archive .local-backups/atlas-data-new-backup.zip
backend\.venv\Scripts\python.exe backend\scripts\data_archive.py restore --archive .local-backups/atlas-data-new-backup.zip --target-dir .ui_validation/restored-data-check

# 启动恢复副本前必做：按哈希验证原件并重定位统一知识资产路径
backend\.venv\Scripts\python.exe backend\scripts\migrate_knowledge_workspace.py --data-dir .ui_validation/restored-data-check --relocate-from backend/data

# 核对迁移输出后，在空闲端口读取恢复副本；不会替换原资料目录
.\start.ps1 -Mode Local -DataDir .ui_validation/restored-data-check -BackendPort 8012 -FrontendPort 5182 -Offline
```

备份路径必须位于数据目录外。恢复目标必须尚不存在；先在隔离目录核对论文、PDF、图谱、路线、课题和任务，再按实际运行环境切换 `DATA_DIR`。校验失败不会创建最终恢复目标。工具拒绝数据目录中的符号链接及压缩包内越界路径。

`restore` 负责恢复原始字节，不自动重写数据库内的 `kw_assets.path` 绝对路径。因此仅解包后启动不足以证明恢复正确：若旧资料仍在，原文可能继续从旧目录读取。上面的 `--relocate-from` 必须指定**生成这份备份时的原数据根目录**；示例是 `backend/data`，自定义资料库请替换为实际旧根路径。迁移器分别处理根库与 `users/` 账号范围，逐资产校验目标原件的哈希后再更新路径，不调用模型。缺失、越界或哈希不符时停止，不猜测匹配文件。

恢复后核对迁移输出的 `asset_paths`，打开带来源定位的节点与原文，确认文件路径均落在恢复目标内。不要把仍指向旧目录的副本当作独立恢复成功。迁移会保留历史内容与修订；需要逐字节回退时，先保留备份原包，在新的目标目录再次恢复。

## 本机 1.0 升级前备份

2026-10-30 的现有工作区已生成标准格式备份 `.local-backups/pre-unification-20261030-0920/standard-data-backup.zip`，`data_archive.py verify` 已实际通过：格式 `research-atlas-data-backup-v1`，37 个文件。它只保存在本机，不随源码发行包分发；其他机器应先创建自己的备份。

```powershell
backend\.venv\Scripts\python.exe backend\scripts\data_archive.py verify --archive .local-backups/pre-unification-20261030-0920/standard-data-backup.zip
backend\.venv\Scripts\python.exe backend\scripts\data_archive.py restore --archive .local-backups/pre-unification-20261030-0920/standard-data-backup.zip --target-dir .ui_validation/restore-before-unification
backend\.venv\Scripts\python.exe backend\scripts\migrate_knowledge_workspace.py --data-dir .ui_validation/restore-before-unification --relocate-from backend/data
```

该标准 ZIP 的 SHA-256 为 `f54de0b540680c9daabf7cab5eb10bf1ce142193ce2cc5ee37e8e28cd98508c9`。同目录的早期自定义 recovery ZIP 仅作历史备用，本说明不要求用户使用自定义格式恢复。

服务重启时，旧版任务标为失败、课题任务标为中断；历史记录保留。两类任务的重试仍由各自原接口发起。同一失败任务的重复重试请求返回同一个尝试 ID；运行者只能原子领取一次已排队任务，旧进程不能把中断后的状态改回成功。不会自动重发模型调用或外部下载请求。

## 验收

`backend/tests/test_data_archive.py` 覆盖数据库与 PDF 恢复、错误校验和不覆盖目标；`test_sqlite.py` 覆盖旧任务表迁移；任务测试覆盖中断和重复领取。完整后端回归通过 `backend/.venv/Scripts/python.exe backend/scripts/test.py -q` 运行。恢复测试只使用隔离数据；实际数据迁移与冻结结果以当前验收记录为准。
