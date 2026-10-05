# Research Atlas 隔离浏览器验收协议

状态：待人工执行。该协议只准备和读取合成资料，不调用真实模型、GROBID、
Neo4j 或其他网络服务，也不构成科研效果验证。

## 1. 安全边界

- 使用全新或已有但为空的临时目录；不得使用 `backend/data`、正在运行的
  `DATA_DIR`、Docker 数据卷或用户资料目录。
- 生成脚本必须显式传入 `--output-dir`。它会拒绝 `backend/data` 及其子目录，
  也会拒绝已有非空目标，不覆盖或自动删除任何文件。
- 夹具中的论文、方法、两个实验设置和数值全部虚构，并在页面数据中反复标记。
  `0.41` 与 `0.37` 只是界面检查值，不是性能、阈值或成功结论。
- 浏览器验收期间不要触发“候选抽取”或模型方案生成；不要打开需要 Neo4j
  的图查询作为成功项。图服务失败必须单独记录，不能用夹具冒充成功。

## 2. 生成隔离数据

从仓库根目录运行，替换为自己选择的绝对临时路径：

```powershell
python evaluation/research_atlas/prepare_browser_fixture.py `
  --output-dir D:\temp\research-atlas-browser-20261004
```

成功后目录中只有新建的 `atlas.db` 和 `browser-fixture.json`。记录脚本输出的
`project_id`、`plan_id`、`snapshot_id` 和绝对 `data_dir`。第二次对同一目录运行
会因目录非空而明确失败，这是预期保护。

## 3. 启动隔离后端和前端

新开 PowerShell 窗口，只对该进程设置临时数据目录：

```powershell
cd D:\storage\Codex_program\AI4S\backend
$env:DATA_DIR = 'D:\temp\research-atlas-browser-20261004'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

不要设置模型密钥，也不要启动 Neo4j 或 GROBID。另开窗口：

```powershell
cd D:\storage\Codex_program\AI4S\frontend
npm run dev
```

打开 `http://localhost:5173/research`。确认列表只有合成验收课题，进入项目时
核对 URL 中的 ID 与 `browser-fixture.json` 一致。

## 4. 人工检查清单

逐项保留截图或文字记录，并明确“通过 / 失败 / 未执行”：

1. 课题标题带 `[合成验收]`，约束说明“不验证算法效果”。
2. 关联资料标题带 `[合成夹具]`，来源片段可定位且显示虚构说明。
3. 方法状态为人工确认；设置甲和设置乙是两个独立实验设置，没有合并。
4. 设置乙的随机种子、计算资源保持未知，没有显示为 `0`、默认 GPU 或推测值。
5. 两个 `fixture_check_value` 分别绑定各自设置和不同 scope；不得直接显示为
   可比较排名或“甲优于乙”。
6. 决策来源为 `user_input`，理由说明只是人工选择，不是论文结论。
7. 人工方案来源为 `user_input`，能够查看、编辑并另存为新版本；旧版本仍在历史中。
8. 快照显示冻结项目、约束、决策、文档、事实和方案版本，原快照不可被编辑覆盖。
9. JSON 导出包含 `contract_version`、冻结引用、`source_kind=user_input`、未知项和
   `review_status`；不含密钥或本机环境变量。
10. 打印页明确区分合成来源、用户方案和未知项。使用浏览器“另存为 PDF”，人工
    检查分页、字体、链接、标题和内容完整性；记录 PDF 文件 SHA-256。
11. 刷新项目、历史和打印页，确认记录仍存在。停止后端再启动并重复读取，确认
    SQLite 数据没有因重启丢失。
12. 如果误点模型生成、候选抽取或图查询，必须把外部能力不可用记录为明确失败，
    不得改写成通过。

PDF 哈希可在保存目录执行：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\temp\research-atlas-browser-output.pdf'
```

## 5. 结果记录

记录浏览器名称与版本、前后端构建标识、执行时间、夹具 manifest、每项结果、
截图/PDF 路径与哈希。任何一项失败都保留原始错误，不使用 mock 截图替代。
该轮只能证明合成数据的真实浏览器读取、编辑、导出和打印行为，不能证明真实模型、
真实论文抽取、Neo4j 投影或科研有效性。

## 6. 手工清理

先关闭使用该目录的 uvicorn。读取 `browser-fixture.json` 再次确认绝对路径确实是
本轮自行创建的临时目录，并检查其中是否有需保留的截图或 PDF。随后在文件资源管理器
中删除该精确目录，或对写死的精确路径使用 `Remove-Item -LiteralPath ... -Recurse`。
不要使用通配符、环境变量、仓库根目录、`backend/data` 或任何 Docker 卷作为删除目标。
脚本不会代替用户执行清理。
