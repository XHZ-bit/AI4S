# 本机 Neo4j / GROBID 服务验证

验证日期：2026-10-04  
执行范围：T0 下一阶段计划中的本机服务只读检查  
结论：**现有 Neo4j 与 GROBID 容器均在运行且健康；只读健康/版本请求通过。写入级集成验证为 NOT RUN。**

## 安全边界

- 未调用真实模型，未下载模型权重或训练数据。
- 未执行 `docker pull`、`docker compose up`、镜像构建、容器重启或卷操作。
- 未读取或输出 `.env`、Neo4j 密码、API key 或其他凭据。
- Compose 校验使用进程内占位密码并通过 `--env-file NUL` 禁止读取项目 `.env`。
- 未建立 Neo4j 驱动认证会话，未执行 Cypher，未创建约束、节点或关系。
- 未向 GROBID 提交论文或 PDF，仅调用无状态的健康与版本 GET 接口。
- 未访问或修改 SQLite、`neo4j_data`、`backend_data` 等生产/现有数据卷。

## 配置核对

项目 `docker-compose.yml` 定义：

| 服务 | 镜像/构建 | 本机端口 | 数据边界 |
| --- | --- | --- | --- |
| Neo4j | `neo4j:5-community` | HTTP `127.0.0.1:17474`；Bolt `127.0.0.1:7687` | 命名卷 `neo4j_data` |
| GROBID | `lfoppiano/grobid:0.8.0` | HTTP `127.0.0.1:8070` | 未声明数据卷 |
| backend | 本地构建 | `127.0.0.1:8000` | 命名卷 `backend_data` |
| frontend | 本地构建 | `127.0.0.1:5173` | 无业务数据卷 |

Compose 静态解析结果：通过。解析出的服务为 `neo4j`、`backend`、`frontend`、`grobid`；目标镜像引用与上述声明一致。

## 运行时与现有资源

| 检查项 | 实际结果 |
| --- | --- |
| Docker CLI / Engine | `29.2.1` / `29.2.1` |
| Docker Compose | `v5.0.2` |
| Docker context | `desktop-linux` |
| Engine | Docker Desktop，Linux containers，`x86_64` |
| `neo4j:5-community` 镜像 | 已存在，ID `sha256:3388e05ee53c8313d01acdf33e63ad175af95a92226dc8551160564439ce2c8c` |
| `lfoppiano/grobid:0.8.0` 镜像 | 已存在，ID `sha256:72ea75c660304ee005027f417beb7c695abf0a62f5c64d5d793027984e7bbd2c` |
| `ai4s-neo4j-1` | `running / healthy`，restart count `0` |
| `ai4s-grobid-1` | `running / healthy`，restart count `0` |

以上容器在检查前已经运行约两小时；本次验证没有启动它们。

## 端口和只读健康请求

| 目标 | 结果 |
| --- | --- |
| `127.0.0.1:17474` | TCP 可达 |
| `127.0.0.1:7687` | TCP 可达；未认证、未执行图查询 |
| `127.0.0.1:8070` | TCP 可达 |
| `GET http://127.0.0.1:17474/` | 可达；报告 Neo4j `5.26.30`、Community edition |
| `GET http://127.0.0.1:8070/api/isalive` | HTTP 200，响应 `true` |
| `GET http://127.0.0.1:8070/api/version` | HTTP 200，响应 `0.8.0` |

这些结果只能证明检查时刻的本机容器、端口和无认证健康接口可用，不能证明应用认证、AtlasV2 Cypher、投影重试、PDF 解析质量或故障恢复正确。

## 实际执行的命令

以下命令均为只读；占位值不是真实凭据。

```powershell
docker version --format 'client={{.Client.Version}} server={{if .Server}}{{.Server.Version}}{{else}}unavailable{{end}}'
docker info --format 'os={{.OperatingSystem}} type={{.OSType}} arch={{.Architecture}} containers={{.Containers}} running={{.ContainersRunning}} images={{.Images}}'
docker compose version
docker context show

docker image inspect --format '{{.Id}}' neo4j:5-community
docker image inspect --format '{{.Id}}' lfoppiano/grobid:0.8.0
docker ps -a --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'
docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}|{{.RestartCount}}|{{.Config.Image}}' ai4s-neo4j-1
docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}|{{.RestartCount}}|{{.Config.Image}}' ai4s-grobid-1

$env:NEO4J_PASSWORD='<validation-placeholder>'
docker compose --env-file NUL config --quiet
docker compose --env-file NUL config --services
docker compose --env-file NUL config --images
Remove-Item Env:NEO4J_PASSWORD

Test-NetConnection -ComputerName 127.0.0.1 -Port 17474 -InformationLevel Quiet
Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -InformationLevel Quiet
Test-NetConnection -ComputerName 127.0.0.1 -Port 8070 -InformationLevel Quiet
Invoke-RestMethod -Uri 'http://127.0.0.1:17474/' -Method Get -TimeoutSec 5
Invoke-WebRequest -Uri 'http://127.0.0.1:8070/api/isalive' -Method Get -TimeoutSec 10 -UseBasicParsing
Invoke-WebRequest -Uri 'http://127.0.0.1:8070/api/version' -Method Get -TimeoutSec 10 -UseBasicParsing
```

补充尝试的 `docker system df --format ...` 因 Docker 29.2.1 的模板字段不兼容而失败；该命令与服务验收无关，没有重试，也没有造成状态变化。

## NOT RUN 与限制

- **NOT RUN：**Neo4j 用户认证和驱动 `verify_connectivity()`；这需要使用凭据。
- **NOT RUN：**AtlasV2 约束创建、快照投影、三类图查询、失败重试及并发行为；这些操作会写图。
- **NOT RUN：**GROBID `processFulltextDocument`；即使服务自身通常无状态，也会传输原始资料，需使用获准的合成 PDF。
- **NOT RUN：**停止、重启、断网、容器重建和数据恢复演练；会影响当前共享服务。
- **NOT RUN：**生产 Compose 全栈重建；不得读取生产 `.env`、写现有卷或影响其他窗口。
- 镜像标签和健康接口通过不等于镜像内容完成许可、安全或漏洞审查。

## 后续隔离写入验证方案

执行前应由 T0 明确授权，并按以下边界建立一次性环境：

1. 使用独立 Compose project name，例如 `ai4s-validation-202610`，不得复用当前 `ai4s` 项目。
2. 为 Neo4j 使用新的精确命名卷和不同主机端口；SQLite 使用临时目录；不得挂载或复制 `neo4j_data`、`backend_data` 或用户数据库。
3. 通过当前进程或专用临时凭据文件注入随机验证密码；日志和报告只记录“已设置”，不记录值。
4. 仅写入合成项目、合成快照、合成证据；验证 AtlasV2 幂等投影、版本切换、查询、失败重试和项目隔离。
5. 为 GROBID 仅提交无版权与隐私风险的最小合成 PDF，验证 `isalive -> processFulltextDocument -> TEI` 和服务不可用时的 PyMuPDF 降级。
6. 先记录基线，再做容器停止/启动与网络故障；确认 SQLite 原始资料和历史快照仍在，图投影可从 outbox 重建。
7. 验证结束后，仅在再次核对精确 Compose project 与卷名后清理该一次性环境；当前共享容器和卷始终不在清理目标内。

