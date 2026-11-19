# 平台收尾暂停记录

当前状态（2026-11-18）：**工程收尾已完成：前端94文件571项全部通过，后端986项及构建、浏览器、恢复检查通过。两套服务已启动，8000/5173/18179/15379健康检查均200；接下来由用户人工交付验收。** 下文保留原暂停时的证据和恢复步骤。

任务版本沿用2026-11-17的最终收尾方案。恢复后继续本轮收尾，不重新开展功能扩展。

## 用户已确定的顺序

1. 沿用Attention主线，先完成平台修复和独立案例准备。
2. 工程检查完成后，由用户亲自进行最终交付验收。
3. 上述两项完成后，再确认成果与交付边界、准备PPT和汇报。

用户尚未进行最终人工验收，不得替用户宣布科研内容或体验已经确认。

## 已完成

- F8：演示初始化同步练习指纹10项返回协议，首次准备/旧版升级不再发生9项解包错误。
- F1：新旧比较空依据内容不再标为“原文明示”；保留旧文字、修订和人工user判断。保存采用PATCH返回，显式重开验证持久化。
- F2：导出保存每次真实运行的代码、JSON输入、状态、耗时、练习/节点/来源版本、指纹及映射快照。旧缺项不借用当前草稿；动态Markdown围栏保护通过。
- save_run：由服务端保存练习修订、节点/来源版本及指纹，覆盖客户端同名值。
- F5：首页空课题进入创建空间，新建披露标题中性，“导出笔记”更名“导出学习成果”。现有布局保持。
- F3：Attention公式(1)使用完整原始区域，真实摘录包含分母；独立转写和原图已目视核对。
- F9：修订过的结构公式在默认图谱保留，并沿用祖先闭包；内容列表展示当前API范围内的结构公式，保持课题/资料范围隔离。
- Attention独立空间已准备：真实v7论文、教学除法函数、同名乘法反例、教学讲解、示例笔记。通过正常HTTP上传和继续分析，复用同版本解析缓存，未新增供应商调用。
- 浏览器完整主链7/7通过：原文与代码往返、工程确认/驳回、真实浏览器Python的4.0/2.0、保存解释、笔记、下载和重开。
- 停服备份→校验→恢复新目录→3份资产重定位已完成。恢复后原件哈希、两次运行及原选择导出逐字一致。
- 恢复副本只读浏览器4/4通过：默认入口无需搜索可进公式、完整内容可见结构公式、4.0/2.0可读；无API写入、重复运行、模型/外站请求或页面错误。

## 暂停时检查状态（历史记录）

| 检查 | 状态 |
| --- | --- |
| 全后端 | **986 passed**，日志`.tmp/platform-final-backend.log` |
| 演示/比较后端定向 | 27 passed |
| 运行导出定向 | 11 passed |
| 比较前端定向 | 13 passed |
| 入口/笔记/图谱返回定向 | 23 passed |
| 完整公式区域专项 | 5 passed |
| F9及全局图谱最终定向 | **21/21 passed**，`.tmp/f9-final-graph-tests.log` |
| 生产构建 | **通过**，`.tmp/platform-final-build.log`；保留已有大分块提示 |
| 相关Ruff与差异检查 | 通过 |
| 最后固定源码版本的完整前端 | **被用户暂停中断，尚无最终结果**。日志`.tmp/platform-final-frontend-stable.log`已记录124条测试通过，无已记录失败，但不能当作全套通过 |

先前`.tmp/platform-final-frontend.log`为568/571通过：两个F9新增断言运行时组件仍为旧模块镜像，另一个重交互用例15秒超时。最终两个文件已21/21定向通过，保留全部断言；应在固定源码下完成一次新的全量前端回归，而非删除断言或用旧结果宣布全绿。

## 保存位置与校验标识

- 当前应使用的独立演示资料目录：`.ui_validation/attention-final-20261117/restored-data`。
- 原演示目录`.ui_validation/attention-final-20261117/data`保留作恢复前副本，不要误替换当前验收资料。
- 原个人资料：`backend/data`，正常服务使用8000/5173、登录开启；演示使用18179/15379、本机匿名且离线。
- 项目：`project-998f3209875648718af3eadfb49c5330`。
- 目标节点：`0c24a1af76ef2b224ce6991d16e00d67`。
- 最新练习、映射修订及深链：`.ui_validation/attention-final-20261117/attention-demo.json`。
- 备份：`.ui_validation/attention-final-20261117/attention-data-backup.zip`；SHA256：`c4545ec78601e149aa260824b43aeaaca8f747e47720dbb1bcfbf7f86c870816`。
- 下载成果：`browser/attention-selected-learning-outcome.md`；SHA256：`7be4e7ddd130919c5046902cf78a3b464ee61b64133d6149b147294904e60e79`。
- 选择与报告：`browser/outcome-selection.json`、`browser/attention-demo-browser.json`、`browser/attention-demo-smoke.json`。
- 恢复验证：`before-recovery.json`、`after-recovery.json`。上述相对路径均在独立演示目录下。
- 源码标识：`source-manifest.json`，624文件，树SHA256：`1583af697c9c0249ec01f748c87b851d83931800def3aeed2f0177bc8db69571`。暂停前再次校验一致。源文件已有大量本轮以前的脏改动，**不得清理、回滚、覆盖或擅自提交**。

## 2026-11-18恢复进展

- 暂停后的首次源码校验仍为上述1583…版本；备份校验通过。两套服务恢复后健康检查均200。
- 当前独立演示仍运行于`restored-data`。恢复后的只读浏览器4/4通过，无API写入、模型调用或新运行；原件和2条工程运行保留。同选择导出仍与7be4…的文件逐字一致。
- 首次恢复全前端为570/571通过：唯一失败是测试用`findByText`查询“历史D2比较”，同时匹配下拉选项和h3标题。改为精确heading角色、level=3；D2恢复和不自动生成断言均保留。修复后单文件22/22通过，未修改产品逻辑。
- 仅上述测试文件改变；原624文件快照保存在`source-manifest-before-test-selector-20261118.json`。新的`source-manifest.json`树SHA256为`b4df8e7deda785994340a3453abf833674a8d97c242ee61a9ffd0d886795c01b`。校验脚本仍可用于检查此版本。
- 标题查询修复后的双worker全量`.tmp/platform-final-frontend-accepted-20261118.log`出现两worker同步数分钟计时异常（约488/491秒、435/435秒），超出15秒测试时限。该轮已中止，不能用来断言产品逻辑故障，也不作为通过证明；未据此改产品或统一增加时限。
- 单worker中间诊断已记录163项通过，无失败，包含上述异常点；该轮已中止，保留`.tmp/platform-final-frontend-serial-20261118.log`。随后停止服务与构建，以双worker检查，日志为`.tmp/platform-final-frontend-isolated-20261118.log`。初次恢复失败基线为`.tmp/platform-final-frontend-resumed-20261118.log`，定向通过为`.tmp/platform-comparison-selector-fixed-20261118.log`；最终通过记录见下文。
- 独立条件双worker已记录348项通过，仅旧`research/next-step`跨多个面板流程触及15秒整项预算，该轮中止保留日志。此用例在旧单独/串行检查通过；现只为该用例设置30秒预算，与同类多步骤测试一致，所有路径/不自动执行断言保留，未统一放宽时限、未改产品逻辑。
- 最新固定版本完整前端输出到`.tmp/platform-final-frontend-verified-20261118.log`。源码树新SHA256：`fbf26b73fa82c31f48d3b95394e361434e9a5edfc972da44d526e6d4ac937ea4`；旧b4df…快照保存在`source-manifest-before-workflow-budget-20261118.json`。本次恢复仅修改两个前端测试（标题角色定位与单个整项时间预算）。
- **最终结果：94文件、571项全部通过，耗时717.63秒。** 本次生产构建通过，日志为`.tmp/platform-final-build-resumed-20261118.log`；恢复后只读浏览器4/4、原件哈希/2条工程运行/同选择导出一致性均再次通过。
- 服务已按顺序启动，并复核PDF静态资源和全部健康端点；最终启动后数据报告为`after-final-start-20261118.json`，仍为3原件、3已重定位资产、2工程运行、导出SHA7be4…一致。启动过程一次PDF静态文件占用重试后成功，未改产品源码和资料。

## 接下来仅做用户人工验收

使用[八步人工验收指南](validation/attention-final-user-acceptance-2026-11-17.md)。独立空间仍用15379和restored-data，原个人空间用5173和backend/data。用户确认前，不把工程确认冒认成用户确认；不进入许可证、公开发布或PPT阶段。无源码/依赖变化和新失败时，不必重复本轮全量检查或重新初始化演示资料。

## 原恢复步骤（已执行，保留备查）

1. 阅读本记录及[本轮修复记录](validation/final-platform-fixes-2026-11-17.md)，校验`.tmp/freeze_attention_candidate.py`仍通过；若有用户新改动先辨认，不能覆盖。
2. 在固定源码上完成全前端回归：在frontend目录执行`npm test -- --maxWorkers=2 --reporter=verbose`，输出到新的日志。上一轮最后命令已中止，不会自行继续。后端986通过、浏览器主链和恢复证据已完成，无新改动不必重复全套。
3. 按需要启动两套服务并检查健康。普通空间用`start.ps1 -Mode Local -DataDir backend/data -BackendPort 8000 -FrontendPort 5173`。
4. 演示在独立PowerShell会话设置`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`KNOWLEDGE_USE_DOCLING=false`、`KNOWLEDGE_FORMULA_VISION_ENABLED=false`，再执行`start.ps1 -Mode Local -DataDir .ui_validation/attention-final-20261117/restored-data -BackendPort 18179 -FrontendPort 15379 -Offline -AllowAnonymous`。
5. Codex工具环境需保持启动的托管exec会话存活；本轮用启动脚本后`while ($true) { Start-Sleep -Seconds 15 }`维持。结束托管会话会停止子服务。不要凭旧runtime.json PID强制杀其他进程。
6. 可运行`.tmp/check_attention_restore.py`验证恢复资料（参数和示例见脚本）；只读浏览器用`run_attention_demo_browser.cjs`的`--smoke`模式，明确检查restored-data。不要重跑初始化、覆盖记录或再次制造运行记录。
7. 全前端结果确定后，更新修复记录和[人工验收指南](validation/attention-final-user-acceptance-2026-11-17.md)，把15379入口交给用户。此后等待用户亲自验收。

## 暂停当时的运行状态（历史记录）

已中止最后前端测试和两套服务的托管会话，并实际检查8000、5173、18179、15379全部不可达。浏览器验收已退出，没有正在工作的子代理。文件、日志、资料、备份均已保存，可以关闭电脑。

教学内容由开发助手整理，工程确认不是用户最终科学验收。4.0/2.0为softmax前的单个缩放分数；默认编辑稿已恢复dot=8、d_k=4，历史两次运行保留。最终公开范围、许可证、源码发布和正式PPT尚未执行，按用户要求后置。
