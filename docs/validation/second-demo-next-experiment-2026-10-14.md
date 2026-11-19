# 第二个 Demo：自动反证与路线对照实验（2026-10-14）

原始机器报告：[second-demo-next-2026-10-14.json](second-demo-next-2026-10-14.json)。报告包含本次 Python、SQLite、相关代码和三个固定 PDF 的 SHA-256，未包含论文全文。实验在新建的隔离数据库中完成，没有更改正式平台数据。

## 问题与预设门槛

检验自动核查能否拒绝来源错误、关系结构错误和先修环路；证据撤回后路线是否收缩；与不使用画像的简单基线相比，候选路线是否确实对两种画像产生不同输出。通过门槛：五种机械故障的预览 API 均返回 422；撤回先修关系后路线不扩张；推荐的原文片段均存在。

这些指标只检查软件行为。两条先修关系是固定演示资料中的教学假设，不是独立的教学正确性标签。

## 对照结果

| 方法 | 机器人方向画像 | 生成模型方向画像 | 两画像是否不同 |
|---|---|---|---|
| 固定三篇清单 | RoboMimic、DDPM、Diffusion Policy | 同左 | 否 |
| 只给目标论文 | Diffusion Policy | 同左 | 否 |
| 当前证据路线 | DDPM → Diffusion Policy | RoboMimic → Diffusion Policy | 是 |

两种原始画像的预览 API 均返回 200，当前路线使用的原文片段都可在隔离库定位。此结果证明画像输入影响了推荐输出；不能由此推断学习效率或科研能力提升。

## 故障注入结果

| 注入 | 自动核查 | 预览 API | 判断 |
|---|---|---:|---|
| 篡改引文 | 拒绝 | 422 | 达标 |
| 引文指向别的论文文档 | 拒绝 | 422 | 达标 |
| 关系端点类型不合法 | 拒绝 | 422 | 达标 |
| 删除引用片段 | 拒绝 | 422 | 达标 |
| 制造先修环路 | 拒绝 | 422 | 达标 |
| 撤回一条先修关系 | 允许剩余资料 | 200 | 路线收缩，未扩张 |
| 把一条关系的概念换成另一有效概念 | **未发现** | 200 | 语义盲点，不能宣称教学关系已获验证 |

本轮发现并修复两个工程问题：证据检查失败时曾额外报告“画像无差异”，现只报告实际故障；演示资料准备时虽有自动门槛，旧预览接口却不会在请求时重查，现每次请求重新检查，错误资料返回 422。报告中的 `ungated_planner_routes_diagnostic` 是直接调用底层规划器的诊断输出，不是已向用户提供的路线。

## 复现

从仓库根目录，使用全新空目录运行：

```powershell
python evaluation/research_atlas/evaluate_second_demo_next.py --pdf-dir .tmp/second-demo-sources --work-dir .tmp/second-demo-exp-replay --output .ui_validation/second-demo-next-replay.json
python -m pytest backend/tests/test_roadmap_generate.py backend/tests/test_roadmap_api.py backend/tests/test_m6_seed.py -q --basetemp .tmp/pytest-second-demo-replay
python -m ruff check backend/app/roadmap/auto_evaluate.py backend/app/api/roadmap.py evaluation/research_atlas/evaluate_second_demo_next.py backend/tests/test_roadmap_generate.py
```

`--pdf-dir` 是可选的本地缓存参数；没有缓存时可省略，脚本会从固定的 arXiv 版本下载并校验 SHA-256。本轮已分别跑通缓存和无缓存路径；在线下载依赖 arXiv 当前可用性，失败会显示源准备错误，可改用已校验的缓存。下载的 PDF 仅留在隔离工作目录，不随报告提交。

本轮相关测试 16 项通过，Ruff 检查通过。下一轮应针对语义盲点建立**独立来源的标签或跨来源反证**；仅靠关键词重合或让同一生成器自评，无法把教学假设提升为事实结论。
