# PaperStride 1.0 文件归档与清理记录

日期：2026-10-30。**当前状态：后端与前端最终回归通过后，已完成本轮受限清理。** 历史文件删除 369 项，旧测试缓存文件删除 421 项，共计 790 文件、220,440,098 字节（约 210.2 MiB）。本记录按实际结果统计；其余缓存保留，未以清空工作区作为目标。

## 已完成的保护与归档

升级前源码和数据已保存在本机 `.local-backups/pre-unification-20261030-0920/`。其中标准数据备份 `standard-data-backup.zip` 已用项目 `data_archive.py verify` 实际校验通过：`research-atlas-data-backup-v1`、37 文件。恢复命令与资产重定位要求见[本地恢复说明](../local-data-recovery.md)。

历史归档为 `.local-backups/history-20261030-095056.zip`：492 文件，原始总量 271,358,676 字节。ZIP CRC 与全部文件 SHA-256 已回读验证，压缩包 SHA-256 为：

```text
5f818d1647fc870d10be5cb8d94a8e692c6f940508b49732c1990e3ddd2a3221
```

归档覆盖旧阶段文档、旧 README、历史设计预览、多轮报告/幻灯片制作副本和旧源码包；每个文件保留原相对路径、大小、用途及 SHA-256。逐文件引用和保留理由在本机 `.ui_validation/history-cleanup-plan.json`、同名 Markdown 以及 ZIP 旁侧 JSON 中。ZIP 内为初始准备清单；旁侧与工作区清单为安全复查后的 revision 2，文件内容及哈希未改变。

## 已执行的历史文件清理

revision 2 已移除 **369 文件、103,470,035 字节（约 98.7 MiB）**，候选中的 **123 文件原位保留**。

| 区域 | 已移除文件数 | 说明 |
| --- | ---: | --- |
| 旧 `.releases` 源码包/摘要 | 7 | 已归档；仍用于正式佐证的历史包保留 |
| `aic_review` 旧制作目录 | 97 | 排除正式及源码幻灯片目录 |
| `design-previews` | 40 | 历史预览 |
| 历史阶段文档与旧 README | 19 | 当前安装、契约、恢复和验收说明保留 |
| 旧 `reports` 草稿/重复输出 | 206 | 排除正式材料、仍被引用的素材和并行编辑目录 |

计划 SHA-256 为 `05eac52182d0e98bcf17f8e6c6cb7ddd3fd357e249709baf87bfa2799dae5679`。PowerShell 默认只预演；执行时要求提供这个明确的计划摘要。每个目标先校验绝对路径在工作区内、祖先无 junction/链接、当前文件与归档哈希一致；全部目标通过后才开始逐文件移除，不执行目录递归清空。

执行前再次预演：369 个目标通过，文件锁定 0、内容变化 0。随后逐文件删除全部 369 项，执行结果为 `complete`，详见本机 `.ui_validation/history-cleanup-result-20261030-101448.json`。未递归删除制作目录，也未强行处理占用或变化项。

恢复历史文件时，先将 `.local-backups/history-20261030-095056.zip` 解压到新的核对目录，再依据 ZIP 旁侧 JSON 的原相对路径与 SHA-256 选择性复制回工作区；不要直接覆盖当前版本或正在编辑的正式材料。旧 README 也在该归档内。数据恢复使用上文的标准数据备份，与历史草稿 ZIP 分开。

## 已执行的受限缓存清理

盘点范围仅包含根 `.tmp/pytest-*`、`backend/.tmp/pytest-*`，以及现有 `scripts/clean-workspace.ps1` 的明确缓存白名单：pytest/ruff 缓存、后端 `.pytest_tmp*`、源码目录下的 `__pycache__` 和前端 TypeScript 增量缓存。源码和运行脚本未发现对旧生成文件的读取依赖；文档中的 `--basetemp` 只是可再次生成的测试输出目录。

共盘点 258 个目标，其中 171 个完整保留；59 个目标在 2026-10-30 当天修改，139 个包含日志、截图或证据名称（两类有重叠），均整目录保留。运行进程命令查询受当前环境限制，因此采用“当天修改即保留”的更严格边界。原始资料、真实数据库、模型、工具、依赖、`.ui_validation` 和正式验收材料不在清理范围内。

其余 87 个目标进入预演。实际执行使用 PowerShell 原生逐文件删除，每个待删文件先校验受限绝对路径、祖先与后代无 junction/链接、文件 hash、当天修改时间及占用状态，删除前再次校验；目录仅在确认已空时移除，没有递归清空 `.tmp`。

为优先进入最终发行包复现，完成已处理子集后停止剩余循环，随后逐项核对清单中的文件和目录是否存在，得到以下实际结果：

| 项目 | 实际结果 |
| --- | ---: |
| 已删除可再生成缓存文件 | 421 |
| 已删除缓存字节 | 116,970,063（约 111.6 MiB） |
| 已移除空目录 | 740（含 15 个完整缓存目标） |
| 预演中剩余文件，原位保留 | 1,121 / 294,032,878 字节 |

本机逐文件记录为 `.ui_validation/cache-cleanup-result-20261030-103131.json`，预演清单为 `.ui_validation/cache-cleanup-plan.json` 和同名 Markdown；计划 SHA-256 为 `5433f3528a73b12888e0ff07859210dba9b8ac059b78c858e5bbebdc04cbe956`。被删除的缓存可通过相应测试或构建重新生成，不使用历史资料归档恢复。没有继续扩大清理范围。

## 原位保留与并行工作

- `reports/aic-2026-10-30-submission/`、模板目录和 `aic_review/final_report/`、`final_slides/`、`source_slides/` 全部保留。
- 发现 `reports/aic-2026-10-30-dark/progress.md` 和 `slide_run_state.json` 在归档后继续变化，整个 dark 制作目录改为保留，避免影响另一个正在进行的制作任务。
- `reports/aic-2026-10-29/PaperStride_AIC2026_技术报告.docx` 被其他应用占用，保留当前文件，不结束用户应用。
- 正式佐证脚本仍读取旧 rewrite 目录的 `comparison.png`、`learning.png`、资源 CSV、报告源 DOCX 等，全部保留原位。
- `docs/parallel-dev/handoffs/T5.md` 仍由兼容检查脚本引用；已有验收和审计证据保留。历史 `RELEASE-MANIFEST.json` 的文件名单属于当时清单记录，已与真实运行依赖分别标记。
- 真实数据库、原始论文、凭据、模型权重、依赖、工具与备份均不在删除计划中；没有整体清空 `.tmp`。

## 当前发行包审计

打包脚本使用当前文档白名单和 `docs/validation/unified-*` 验收范围；只有此验收范围允许 PNG/JPG，避免混入其他历史私人截图。必要的依赖声明、锁文件、案例上游许可及 T5 兼容参考保留。归档、私人资料和正式参赛材料不进入源码包。

文件选择与本地 Markdown 链接已做静态检查，详细输出在本机 `.ui_validation/current-release-reference-audit.json`；它不替代从最终 ZIP 安装运行的验收。自研 `LICENSE` 尚不存在，源码交付按受限评审标识，不声称已有开源授权，也不把第三方声明清单当作完整传递依赖合规审查。

最终发行整理另将 `.releases/` 顶层的 `audit-auth-20261029.zip/json`、`audit-source-20261030.zip/json`、`research-atlas-2026.10.22-validation.zip` 与 `research-atlas-2026.10.22.1-validation.zip` 六项历史文件（6,224,667 字节）以原生 PowerShell `Move-Item` 完整移入 `.local-backups/release-history-20261030-114051/`，没有删除内容，也不计入上文删除统计。移动前后逐一核对绝对路径、无链接祖先、大小与 SHA-256；原路径、新路径及核对值见该目录 `ARCHIVE-MANIFEST.json`，清单 SHA-256 为 `f1d34d0c6966d42141328fca9760e3649c9d0f9253177603661464d75c6e3a4f`。历史审计文档中的旧路径保留当时含义；未发现这六项被当前应用、安装、最终打包或保留材料脚本读取。另一个 `PaperStride-AIC-20261030-source-review.zip` 因正式材料 `working/audit_source_evidence.py` 与 `working/final_crosscheck.py` 仍读取原路径，已在移出后按 SHA-256 `177dbb74b37c6a27bac6f7d49def3b096c681f54dfcf42e57f6165d90fd316a0` 校验并安全恢复到 `.releases/` 原位；它是历史正式佐证，不代表最终 1.0.0 软件包，正式材料目录中的同哈希副本亦保持原状。未移动任何 `PaperStride-1.0.0*` 文件或解压验证目录，未修改上述材料脚本。
