# PaperStride 1.0 工作区文件用途

本索引用于区分可发行源码、用户资料、正式参赛材料和本机历史归档。源码包只包含安装运行所需源码、锁文件、当前说明与必要验收；表中的本机资料目录不会随源码包分发。

| 路径 | 用途 | 保留与交付规则 |
| --- | --- | --- |
| `README.md`、`docs/unified-release.md` | 当前安装、图谱工作流与升级说明 | 源码包主阅读入口 |
| `backend/app/knowledge/` | 统一来源、节点、关系、证据、学习及比较服务 | 活跃源码 |
| `backend/app/` 其余模块 | 账号、资料库、旧接口兼容、方案及历史读取 | 兼容模块仍使用，不能仅凭旧名称删除 |
| `frontend/src/` | 图谱工作台、原文、学习、比较、练习及导航 | 活跃源码 |
| `backend/tests/`、`frontend/src/__tests__/` | 自动回归 | 隔离数据测试，随源码保留 |
| `evaluation/` | 可复算评估工具与合成样例 | 必要工具保留，历史运行输出不混入源码包 |
| `scripts/`、根目录 `*.ps1` | 安装、启动、停止、迁移与打包入口 | 不绕过锁文件，不自动切换用户数据 |
| `backend/uv.lock`、`frontend/package-lock.json` | 依赖锁定 | 必须保留 |
| `backend/data/` 或启动指定的 `-DataDir` | SQLite、原始论文及统一知识资产；账号资料位于各自范围 | 用户数据；先备份，不作为垃圾清理或发行源码 |
| `.demo/synthetic-data/` | 独立、无密钥的原创合成演示与用户演示修改 | 可从空目录生成；重复准备保留现有修改 |
| `.env` | 本机配置，可能含敏感配置 | 不发行；只发行无真实密钥的 `.env.example` |
| `.tmp/models/`、`.tmp/minicpm-ocr/` | 已下载解析/OCR模型 | 不作为垃圾；不进入源码包 |
| `backend/.venv/`、`frontend/node_modules/`、`.tmp/tools/` 及本机工具目录 | 依赖、Python及安装工具 | 可由锁定安装流程准备，不混入源码包；本轮保留现有环境 |
| `frontend/public/pdf-assets/`、`frontend/public/python-runtime/` | 从本地依赖准备的浏览器资源 | 不手工编辑；启动/构建脚本恢复，发行包排除生成副本 |
| `reports/aic-2026-10-30-submission/` | 用户当前正式报告、PPT、佐证材料及编辑来源 | 全部原位保留，本轮不重写 |
| `reports/aic-2026-10-30-template/`、`reports/template/`（若存在） | 用户模板及对应工作材料 | 全部原位保留 |
| `aic_review/final_report/`、`final_slides/`、`source_slides/` | 已有正式与可编辑材料 | 全部原位保留 |
| `reports/aic-2026-10-30-dark/` | 检测到并行编辑的演示材料 | 本轮清理已排除，保留正在产生的成果 |
| `docs/validation/` | 实测记录与必要证据 | 本机证据保留；源码包仅纳入明确的当前验收与依赖声明 |
| `.ui_validation/` | 本机验收过程、引用索引、清理预演及临时运行证据 | 不无差别删除，不进入源码包 |
| `.local-backups/` | 可恢复源码/资料备份和带逐文件哈希的历史归档 | 不清理、不发行；恢复方法见下方 |
| `.releases/` | 最终源码 ZIP、清单及 SHA-256 | 以明确的 1.0.0 发行物为准；旧包若仍承担正式佐证则保留 |

历史草稿只在先归档、核对引用与哈希、通过回归后移除散落副本。仍被正式材料脚本使用的旧图像、资源 CSV 和报告源文档保留原位；不能因其目录带旧日期就整体删除。

恢复用户数据使用标准 `data_archive.py`，并在启动恢复副本前完成资产路径重定位，详见[本地数据恢复](local-data-recovery.md)。历史草稿 ZIP 保存原相对路径和 `HISTORY-MANIFEST.json`，本机旁侧清单记录安全复查后的保留项；先在新目录核对哈希，再选择需要恢复的文件，不直接覆盖当前工作。

当前清理状态与限制见[1.0 清理记录](validation/unified-cleanup-2026-10-30.md)。源码包不包含备份、用户资料、模型或正式参赛材料，受限交付不决定自研开源许可证。
