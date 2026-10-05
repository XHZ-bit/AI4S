# T0 真实交互、PDF 与服务验收（2026-10-04）

本记录覆盖此前 NOT RUN。所有业务写入使用合成课题或 Linux 临时 SQLite；现有生产数据库、论文和 Docker 数据卷未访问或修改。没有下载或升级依赖、镜像和模型。

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Chrome 点击、键盘输入、保存、刷新 | PASS | Playwright 驱动真实 Chrome；原生 Windows CUA 仍初始化失败 |
| 390px 窄屏 | PASS | scrollWidth=390，无横向溢出 |
| 浏览器断网保存/重连恢复 | PASS | offline 模式保存明确失败，输入保留，重连刷新恢复 |
| PDF 视觉/文本 | PASS | 2 页 A4，PyMuPDF/pypdf 原样检出关键 ID，无 CJK 部首替代 |
| Neo4j 认证/写入/查询 | PASS | 内部网络、临时随机凭据、全新 tmpfs 数据 |
| GROBID PDF 解析 | PASS | 真实两页合成 PDF，6 个正文片段 |
| 无网络后端启动/读取/导出 | PASS | Docker --network none，真实 ASGI/SQLite，无服务 mock |
| Qwen 真实调用 | PASS | 3 次 HTTP 成功，只发送合成文本 |
| Qwen 方法名质量 | FAIL | 模型把资料声明并入方法名，严格断言失败 |

不能把所有项标记为绿色。生产 plan_suggestion_provider 仍未接入，本轮 smoke 不是完整生产模型生成链路验收。

## 修复与浏览器证据

保存后刷新选中最早方案的问题通过项目级 selected-plan 本地记录修复；未保存人工草稿仍优先恢复。390px 卡片头部原本溢出 48px，已在 Research 方案面板窄屏范围启用工具栏换行和缩减内距。PDF 冻结引用改为独立不拆行单元，明确字体，增加快照 ID、A4 12mm 页边距，标题避免悬挂页末；打印前等待 document.fonts.ready。

脚本：`evaluation/research_atlas/browser_live_validation.cjs`。数据/输出：`evaluation/research_atlas/.tmp/live-validation-20261004`。

实测流程：新建人工草稿 → 点击/键盘输入 → 添加步骤 → 刷新恢复未保存内容 → 确认保存/实际 PUT 200/user_input → 刷新恢复已保存方案 → 390×844 窄屏编辑 → 浏览器断网 → 保存明确失败且输入保留 → 重连刷新恢复 → 打印原始不可变快照。非 localhost 请求全部拦截，本地 API 无响应 mock，pageerror=0。

证据文件：live-browser.json、desktop-interaction.png、narrow-interaction.png、print-page.png、pdf-page-1.png、pdf-page-2.png、validated-snapshot.pdf。

最终 PDF：152258 bytes，2 页，SHA-256 `e29ff91f41437c74cdfc1a5a8fe4b5414dd110e34ff3c5818c6cf4795f30acdb`。两页渲染检查无裁切/重叠。两个文本引擎均直接检出 method-synthetic-probe、setting-synthetic-b、synthetic-browser-document-001、sha256:synthetic-browser-content-v1，无需 NFKC 或删除空白。U+2E80—U+2FFF 部首计数为 0。

## Neo4j、GROBID 与断网

本机已有 Neo4j 5.26.30 镜像，--pull never。最终实例 atlas-live-neo4j-final-20261004 位于内部网络 atlas-live-net-20261004，未映射宿主端口，/data、/logs 使用 tmpfs。随机凭据只在进程环境传递，未打印或保存。

真实认证成功。生产 build_graph_projection/project_graph 与查询实现验证了重复投影幂等；依据路径 12 节点/13 边，方法上下文 3 节点/1 边，影响路径 6 节点/4 边；不同 project_id 无法访问同一快照；v2 后 v1 仍可查询且 current=false。结果：live-graph.json。

首次 Neo4j --network none 启动 exit 3，改内部网络后成功。首次共享 Windows SQLite 出现 I/O 错误，因此容器验证使用 Linux 原生临时目录重新生成合成库，没有改变生产配置。

生产 parse_with_grobid 向本机 GROBID 0.8.0 提交 2389-byte 两页合成 PDF，返回 6 个正文片段，保留 Synthetic Probe 和 not reported。保留 PDF、原始 TEI、解析 JSON、live-grobid.json。首个一页短文未返回正文，断言失败；改用明确正文的两页文档后通过，不代表任意论文解析都成功。

离线验证使用 ai4s-backend:latest 现有依赖、当前源码、Linux 临时 SQLite 和 --network none。应用生命周期启动后，TestClient 调用真实 ASGI 路由读取快照与 JSON；外网 TCP 不可达，图连接明确失败后冻结事实完整。证据：live-offline.json。这不是生产 Compose 升级或宿主机物理断网演练。

## 真实模型：执行完成，质量未通过

live_model_smoke.py 在现有后端进程环境中调用 dashscope.aliyuncs.com / qwen3.7-flash。Settings(_env_file=None) 禁止读取 .env，应用内部使用已有凭据，工具未输出凭据，不导入业务数据库模块。仅合成文本离开本机。

共 3 次请求，temperature=0、max_tokens=1024，无自动重试。第三次增加排除元数据/声明/句首/泛称的通用字段规则后仍失败，已停止调用。

第二次方法名为 `SYNTHETIC VALIDATION INPUT, NOT SCIENTIFIC RESULTS. The Synthetic Probe method`；第三次仍含声明前缀，只去掉末尾泛称。两个设置/数据集关联正确，显存、耗时、成绩均为 null。严格断言拒绝响应，未写入事实库，未对固定字符串写特判。

第二次 usage：prompt=100、completion=654、total=754；第三次 prompt=124、completion=1704、total=1828，其中 reasoning=1595。服务统计包括推理 token，不能把请求 max_tokens=1024 当作已验证的总消耗上限。首轮未记录 usage，不编造总量或费用。

后续需按生产 T2 schema 和独立人工标注样本验证名称边界、引用绑定与跨设置归属；小型直连 smoke 不能替代该评估。

## 实际命令与测试

```powershell
python evaluation/research_atlas/prepare_browser_fixture.py --output-dir <新隔离目录>
node evaluation/research_atlas/browser_live_validation.cjs <隔离目录>
python evaluation/research_atlas/live_validation.py grobid --data-dir <隔离目录>
# graph 在独立内部网络容器中执行，注入临时 NEO4J_URI/NEO4J_PASSWORD
python evaluation/research_atlas/live_validation.py graph --data-dir <报告目录>
# offline 在 --network none 容器中执行，ATLAS_NETWORK_NONE=1
python evaluation/research_atlas/live_validation.py offline --data-dir <报告目录>
Get-Content -Raw evaluation/research_atlas/live_model_smoke.py | docker exec -i ai4s-backend-1 python -
cd frontend
npm test -- --run src/__tests__/research/workspace-panels.test.tsx src/__tests__/research/print.test.tsx --maxWorkers=1 --no-file-parallelism
# 2 files / 10 passed
npm test -- --run --maxWorkers=1 --no-file-parallelism
# 11 files / 34 passed
npm run build
# 成功，4030 modules transformed
```

新增 Python 脚本 Ruff 通过。没有后端生产代码改动，未重复先前通过的 Research 108/旧后端 116 套件。实测脚本显式 opt-in，不加入默认 mock runner，不由默认测试触发模型调用。

## 复跑和清理

浏览器复跑前，在根目录运行 `python evaluation/research_atlas/live_validation.py serve --data-dir <隔离目录>`，并在 frontend 运行 `npm run dev -- --config .live-validation.vite.config.ts`。Node 的 ATLAS_PLAYWRIGHT_PATH 可指向已经安装的 playwright 包；本次使用桌面运行时的 bundled 包，没有改依赖清单。验收配置只代理本机 18000 后端。

本轮创建的三个临时 Neo4j 实例和内部网络已按精确名称检查并删除；仅临时合成图被销毁，现有容器/卷不变。临时前后端进程已停止。上述隔离目录内的 SQLite、截图、PDF、TEI 和结果 JSON 保留供复核。原生 CUA/Node helper 初始化 ACL 错误是工具环境问题，未修改 Windows 安全设置。Ant Design 有 Spin tip/静态 message 的开发告警；浏览器 pageerror 为 0，不将开发告警隐瞒为零 console 输出。
