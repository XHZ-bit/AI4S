# 多人版整站备份与恢复

本工具借鉴 [restic](https://github.com/restic/restic) 的先生成一致快照、校验清单、再复制到异地的流程。当前实现使用 Python 标准库和 SQLite Backup API，不增加常驻服务。ZIP 未加密，包含账号密码哈希、私人论文和个人记录；请将其保存在受控位置，异地存储可再使用 restic 加密。

## 一致性与覆盖范围

- 单独的 `site_archive.py` 处理 `identity.db`、所有已创建的 `users/<账号ID>/atlas.db` 和相邻原始文件。尚未建立资料库的账号也保留。
- 先停止后端及其他写入命令。多人后端和账号 CLI 注册操作系统文件锁，备份发现活跃写入者会退出；维护期间新的服务和账号命令也不能进入。进程崩溃后锁由系统释放，不靠可能过期的 PID 判断。
- SQLite 数据通过 Backup API 读取，包含已提交的 WAL 内容；归档不携带 WAL、SHM、journal。每个文件保存长度和 SHA-256，所有数据库执行 `integrity_check`，账号与个人目录交叉校验。
- 账号目录不匹配、链接/Windows junction、混有旧本机数据库的根目录、备份输出在数据目录内部，都会中止。旧本机数据仍使用原单库工具，不自动混入共享部署。
- 备份期间外部脚本也必须停止；不要绕过写入锁直接操作数据文件，不支持关闭 ASGI lifespan 后运行多人服务。

## 本机 Python 环境

以下命令在项目根目录执行。替换为实际多人数据目录及备份文件名，并使用项目安装环境的 Python；不要指向现有本机版资料目录。

```powershell
# 停止多人后端，等待其退出；不要删除数据目录
python backend/scripts/site_archive.py backup --data-dir D:/atlas-multiuser-data --output D:/atlas-backups/site-20261019.zip
python backend/scripts/site_archive.py verify --archive D:/atlas-backups/site-20261019.zip

# target-dir 必须尚不存在；可先用隔离目录演练
python backend/scripts/site_archive.py restore --archive D:/atlas-backups/site-20261019.zip --target-dir D:/atlas-restored-data
```

成功输出只含格式、时间、账号数、个人库数和文件数，不输出密码、会话或论文内容。失败退出码为 1。恢复会完整校验、提取到临时目录、清除旧会话，再移动到新目录；任何校验失败都不生成目标目录，已有目标会被拒绝。恢复路径须由维护者独占，不应有其他进程同时创建同名目录。恢复后的用户需要重新登录，密码及停用状态保持。

ZIP 发布使用 Windows 的不可覆盖重命名，或 Unix 同卷硬链接，拒绝最后检查之后被抢先创建的同名文件。Unix 输出文件系统须支持硬链接；不支持时直接失败，不退回可能覆盖文件的发布方式。

## Compose 卷

先创建宿主机备份目录，并保证容器的 `appuser` 可写。下面使用 PowerShell 与项目现有的多人 Compose 文件；此处 `run` 是一次性工具容器，不启动 API 或后台任务。

```powershell
New-Item -ItemType Directory -Force ./backups | Out-Null
$atlasBackupDir = (Get-Item ./backups).FullName
docker compose -f docker-compose.multiuser.yml stop backend
docker compose -f docker-compose.multiuser.yml run --rm --no-deps -v "${atlasBackupDir}:/backups" backend python scripts/site_archive.py backup --data-dir /app/data --output /backups/site-20261019.zip
docker compose -f docker-compose.multiuser.yml run --rm --no-deps -v "${atlasBackupDir}:/backups" backend python scripts/site_archive.py verify --archive /backups/site-20261019.zip
docker compose -f docker-compose.multiuser.yml up -d backend
```

若备份命令失败，先处理错误并重新验证；即使恢复服务，也应把本次备份标记为失败。Linux 宿主机需按实际容器 UID 设置备份目录权限。不要执行 `down -v`。恢复到新目录或新卷后再单独切换挂载，先在回环地址验证账号、两个用户间的资料隔离、PDF 和导出。

## 验收与限制

自动回归覆盖两个个人库使用同一论文 ID、原始文件一致性、提交到 WAL 的数据、跨进程写入互斥、停机后的锁释放、旧会话撤销、校验和篡改、越界路径和目录别名、未知账号与现有目录保护。锁与 ZIP 逻辑均覆盖 Windows/Linux 路径。

格式为 `research-atlas-multiuser-backup-v1`；清单最多 4MiB、文件最多 100,000 个、单文件最多 8GiB、总文件最多 64GiB。校验和用于发现损坏，不能证明归档来源可信。尚未自动调度、上传云端或执行保留策略，也未在此机器上执行 Docker 卷恢复演练；这些应在选定部署环境后验证。
