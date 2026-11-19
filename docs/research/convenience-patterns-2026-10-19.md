# 从开源产品借鉴的便捷性改进

核验日期：2026-10-19。范围是当前界面的查找、资料组织、导入和继续阅读；本轮不引入学术调研流水线或新的托管服务。以下来自本地源码只读审查与官方 GitHub/产品文档实查，交互建议与项目实际边界分开说明。

## 官方源与取舍

| 项目 | 已核验许可证 | 值得借鉴的部分 | 本项目接入方式 |
| --- | --- | --- | --- |
| [dip/cmdk](https://github.com/dip/cmdk) | [MIT 原文](https://github.com/dip/cmdk/blob/main/LICENSE.md) | 命令分组、键盘选择、搜索别名、异步加载与无结果状态 | 先用现有 React/Ant Design 实现小型全局搜索/导航面板，保留清晰的键盘与焦点行为。 |
| [zotero/zotero](https://github.com/zotero/zotero) | [COPYING：AGPL v3](https://github.com/zotero/zotero/blob/main/COPYING) | 个人资料库、资料的多重组织方式、保存筛选条件、回到上次资料 | 借鉴交互与数据关系；本轮自行实现个人收藏/稍后读，不复制 Zotero 源码，也不部署或同步 Zotero 服务。 |
| [transloadit/uppy](https://github.com/transloadit/uppy) | [MIT 原文](https://github.com/transloadit/uppy/blob/main/LICENSE) | 每文件状态、批次结果、重试、区分上传完成与后处理完成 | 先为已有上传接口做轻量顺序队列；需要复杂恢复后再评估特定插件。 |

实查时 `https://github.com/pacocoursey/cmdk` 跳转到 `https://github.com/dip/cmdk`，本文使用最终官方仓库地址。没有安装上述三个项目的新依赖；没有实测其包体积、浏览器存储成本或服务器资源，不能据此给出性能承诺。

## 五处实际使用阻力

下表记录本轮开始时的基线与处理方向；代码位置可能随随后实现移动。

| 阻力与确证位置 | 用户实际遇到什么 | 本轮或下一步处理 |
| --- | --- | --- |
| 导航入口较多，已有局部快捷键：`Shell.tsx:8`、`Workspace.tsx:51` | 全局找论文要先选页面；局部空间已有 Ctrl/Cmd+K 监听，直接叠加全局快捷键会打开两层面板。 | 本轮全局面板承担 Ctrl/Cmd+K；局部资源搜索改为 Ctrl/Cmd+Shift+K，并保留显式按钮。 |
| 账户模式能力未贯通：`Manage.tsx:15/17`、`RuntimeStatus.tsx:17`、`access.py:54` | 多人界面仍显示远程采集和模型抽取，点击后才得到服务受限错误；首页只显示部署模式，用户难以判断能继续什么。 | 共享已经验证的会话 mode；多人入口解释限制；运行状态直接提供论文库、处理进度和行动清单的入口。 |
| 上传缺少预期和关联：`Manage.tsx:14`、`api/papers.ts:20`、后端 `papers.py:175` | 目前是单文件提交；未提前显示可配置配额；成功回包含 uid/task_id，但只给通用进度入口，用户要自己认领结果。 | 本轮显示服务器返回的实际配额；后续增加每文件队列，保留 uid/task_id，区分“文件已保存”和“解析已完成”。 |
| 资料只有列表与解析筛选：`Manage.tsx:17/18` | “这篇想保留”和“这篇稍后读”不能形成稳定入口，也不宜把个人偏好混入掌握度或解析状态。 | 本轮为个人资料增加独立收藏/稍后读字段和筛选；不改变阅读、掌握或任务完成状态。 |
| 继续位置仅在当前浏览器：`Home.tsx:12`、`Workspace.tsx:55-61`、`SessionGate.tsx:42/63` | 同一浏览器可以恢复 URL/页码；退出或过期时会清空 Atlas 缓存，因此同账号重登或换设备没有可靠继续位置。 | 保持会话清理。后续以当前用户的服务端记录保存最少的文档版本、页码与更新时间；收藏/稍后读本轮不等于阅读位置同步。 |

相关本地源码：[Shell](../../frontend/src/components/Shell.tsx)、[Manage](../../frontend/src/pages/Manage.tsx)、[Workspace](../../frontend/src/components/workspace/Workspace.tsx)、[Home](../../frontend/src/pages/Home.tsx)、[SessionGate](../../frontend/src/components/SessionGate.tsx)、[访问边界](../../backend/app/access.py)。这些是源码审查结论，没有把它们描述成整套真实用户可用性研究。

## 命令面板：查找后直接去做

cmdk 官方 README 展示了分组、别名、异步状态和键盘操作，并明确快捷键需要应用自己接管。[官方 README](https://github.com/dip/cmdk#readme)。本项目可以采用以下小范围行为：

- 空查询展示常用导航；输入后分组显示个人论文、科研课题和工作台入口。标题之外加入“论文库/资料/PDF”等中文别名。
- 显示加载、无匹配与加载失败三种不同状态；慢请求取消或忽略旧响应，避免旧查询覆盖新结果。
- Enter 打开当前选择，方向键移动，Esc 关闭；关闭后焦点回到触发按钮。保留可点击入口，触屏用户也能使用。
- 面板查询只读当前账户的现有 API；导航和搜索不会自动发起采集、上传、抽取、外部模型调用或任务写入。
- 提供页面可用性提示。前端隐藏入口改善体验，实际授权仍由服务器执行；默认 local 的 UI context 不能替代服务端检查。

本轮把有限的导航/搜索交互留在现有组件栈内；若后续交互规模明显扩大，再以锁定版本评估 cmdk，不能仅凭上游演示认定其键盘、中文输入法与本项目弹窗组合已经验证。

## Zotero：资料身份与个人组织分离

Zotero 的 collection 可以引用同一条资料而不复制资料；保存搜索保留条件，结果随库内容更新。[Collections and Tags](https://www.zotero.org/support/collections_and_tags)、[Saved Searches](https://www.zotero.org/support/searching#saved_searches)。其集合导航的实际实现可查 [collectionTree.jsx](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/collectionTree.jsx)。

适用于当前项目的最小模型是“资料内容 + 个人标记”：同一份 PDF 不因收藏而重复导入；收藏和稍后读独立；取消标记不删除 PDF；两种标记可以同时保存，本轮按其中一种标记筛选。标记属于当前用户的数据目录，资料不在该用户库中时返回找不到，而不是建立指向别人的引用。

后续可把常用筛选保存为条件，例如“收藏且未读”，不存一份静态结果，也不建立第二套全文搜索引擎。完整的层级 collections、自动标签、Zotero 账户/云同步与导入转换器暂缓；当前每用户小型资料库先验证简单标记是否足够。

## Uppy：先把上传和解析状态讲清楚

Uppy 的核心把文件、进度、限制及上传批次作为状态；官方文档特别区分上传完成与后处理完成，并说明类型过滤只是客户端提示。[Uppy Core](https://uppy.io/docs/uppy/)、[核心源码](https://github.com/transloadit/uppy/tree/main/packages/%40uppy/core)。本项目适合先实现一个现有接口上的小队列：

1. 选择多个 PDF 后先展示名称、大小、数量与实际配额，明确开始提交；每条显示等待、上传、解析、完成或失败。
2. 多人模式按一条处理链提交，上一条解析达到终态后继续，匹配当前同用户最多一个后台任务的限制。429 或临时失败显示原因和手动重试，不循环猛发请求。
3. 保存回包 uid/task_id，每条可以去对应资料或任务。已保存但解析失败的文件应重试解析，避免用户误以为必须再次上传。
4. 提供批次摘要和逐条失败原因；一条失败保留其他结果。取消等待项、停止上传和取消已入队解析任务是不同操作，界面分别命名。
5. 前端大小/后缀提示之后，服务端继续验证 PDF 内容、页数、数量、原文件空间与账户权限。

XHR/分块传输、Tus 与 Companion 并非当前 FastAPI 上传接口自动具备的能力。没有服务端协议支持时，不显示“断点续传”或“离线已上传”等承诺；当前 5MiB 默认单文件限制也没有迫切理由先部署新上传服务。

## Local-first 的 recall/resume 边界

这里的 recall/resume 指恢复资料与上下文。现有后端运行且无需外部模型时可阅读、检索和整理；服务完全断开时，这个应用尚不是一套已验收的离线 PWA。

Uppy Golden Retriever 会持久化浏览器状态，并可在 IndexedDB 中保留小文件；恢复不到文件时会要求用户重新选择。[插件源码/README](https://github.com/transloadit/uppy/tree/main/packages/%40uppy/golden-retriever)、[官方恢复与存储说明](https://uppy.io/docs/golden-retriever/)。当前 `clearBrowserDrafts()` 清理 localStorage/sessionStorage，未清理 IndexedDB，直接启用该插件会引入新的个人 PDF 残留面，需先补账户隔离、过期和退出清理。

因此近期先保存最少的继续位置：资料 uid、原文版本、页码、允许的标签页和更新时间；回到旧版本时明确提示重新定位。服务端从认证身份确定记录归属，浏览器仅作为按账户隔离的缓存；退出后继续清空本机私人缓存。不要把原文、模型提示、凭据或完整草稿塞进 URL，也不要把浏览器缓存称为备份。

## 近期顺序与验证

近期顺序为：全局面板与快捷键冲突消除 → 个人收藏/稍后读 → 账户模式能力与实际配额提示 → 小批量顺序上传队列 → 跨会话阅读位置。前三项适合本轮小步完成，后两项应单独做状态机和身份边界验收。

本轮独立改进为 `SessionContext/useAccessMode` 与运行状态指引：复用 SessionGate 已确认的会话，不再发一次鉴权请求；默认 local 供独立组件使用；未确认或已过期时工作台不挂载；多人界面只显示“个人空间”，不回显服务器绝对目录。状态刷新失败时移除上次健康结果，并显示重试和维护者处理指引。

对应定向验证已通过：会话门禁 10 项、运行状态 4 项。既有行动清单保存用例在并行运行时发生一次 15 秒超时，独立复验通过，未修改超时或该业务逻辑；整站最终测试结果另由本轮实施记录汇总。

验证需覆盖：快捷键只打开一个面板、登录前不请求个人搜索、过期后工作台及 context 消失、不同用户看不到彼此标记、刷新后标记保留、收藏不触发模型任务、旧状态不能覆盖新请求、多人状态不泄露服务器路径。后续队列还需覆盖部分失败/重试/429/取消与刷新恢复；当前未将这些后续场景记为已通过。
