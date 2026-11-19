# PaperStride 公式渲染排查与验收（2026-11-17）

## 问题与修复范围

本轮针对多头注意力讲解中 `\begin{aligned} ... \end{aligned}` 直接显示为 LaTeX 源码的问题，检查知识学习、引用、笔记、图谱详情、比较和练习中的公式展示。

已确认的渲染根因：

1. 原 `MathText` 只识别 `$…$`、`$$…$$`、`\(…\)`、`\[…\]`，没有把裸 LaTeX 环境交给 KaTeX。
2. `mathAwareText` 仅在正文恰好等于 `metadata.latex` 时补定界符。正文已有明确公式但没有独立 LaTeX 字段时，不能通过该判断进入数学排版。
3. 原 `KnowledgeText` 另行按链接、代码、公式分段，缺少对裸环境的完整保护。多行公式需要先作为整体识别，不能按段落或 Markdown 链接拆开。
4. 部分引用、符号说明和学习记录直接输出字符串，绕过共享渲染；另有公式字段直接拼接 `$$`，可能重复包装已经带定界符的内容。

本轮只改变展示，不修改保存的公式、源码、证据、练习输入或个人笔记，也不补造数学字母、维度和来源。

## 统一渲染规则

- 使用 `MathText.mathTextParts` 统一识别代码、链接、显式数学定界符、完整 LaTeX 环境及明确的独立 LaTeX 公式，再由同一个 `renderMath` 调用 KaTeX。
- 四种常用定界符均保留支持；裸 `aligned`、`align`、`gathered`、矩阵、`cases`、`array` 等环境整块解析，包括内部换行、空行与嵌套矩阵。具体语法仍以 KaTeX 实际支持为准，不承诺任意 LaTeX 宏包兼容。
- `displayMath`、`inlineMath` 对已带定界符的字段不重复包装。没有 `metadata.latex` 也可渲染正文中已经明确给出的公式。
- 仅对明确 LaTeX 语法或紧凑公式左项后的数学命令识别为裸公式，不把普通英文、文件路径和自然语言任意推断为公式。
- KaTeX 设置 `trust:false`、`throwOnError:true`、有界宏展开。未知命令不产生一大段红色错误源码，也不执行来源中的 HTML 或脚本。
- Windows CRLF 在渲染视图中按正常换行处理；保存内容不变。控制字符、可疑双重命令转义、损坏 PDF 字形、未闭合数学内容均不猜修成数学符号。
- 无法排版时保留周围解释，显示简短提示。在正文、原文及笔记等阅读区域可点击“查看原式”，按需展开保存的表达；控制字符明确显示为 `\uXXXX`，避免看起来像已修好的公式。可以点击“收起原式”关闭。
- 已有公式原图和原文按钮继续保留。`SourceFormulas` 的无效转写优先回到公式原图或对应原文，不把原图转成猜测公式。
- 长公式在自身区域横向滚动，不撑开节点侧栏或整页。

## 展示入口审计表

| 入口 | 共享处理 | 原文与代码边界 |
|---|---|---|
| 学习讲解六节正文 | `KnowledgeLearning → mathAwareText → KnowledgeText → MathText`；裸环境不再依赖节点元数据 | 人工修订输入保留原始文本，重新生成规则不由本轮改变 |
| 节点基础讲解、例子、易混淆点、思考题 | `NodeStudyGuide → KnowledgeText` | 教学内容仍保留原有归属，不变成论文事实 |
| 原文文本与公式内容块 | `SourceReader → displayMath / MathText` | PDF 继续显示真实 PDF；代码资料和代码块仍逐行 `pre/code`；没有 LaTeX 字段的明确公式也可排版 |
| 原文表格 | 普通单元格使用 `MathText` | 结构化对象以原有 JSON 展示，不猜字段含义 |
| 公式原图与转写 | `SourceFormulas → renderMath → displayMath` | 无法渲染时优先原图，保留“查看公式原文”和“核对公式原图” |
| 图谱节点说明、节点公式、连线解释 | `NodeInspector` 已有 `MathText`，公式字段改用 `displayMath` | 画布中的短名称、SVG 标签继续作为名称展示；全文数学在详情区域查看 |
| 图谱节点直接原文片段 | `NodeInspector → EvidenceQuote` | 有源码路径或行号的证据以原样 `pre/code` 展示 |
| 引用列表、问答引用、笔记依据、练习依据 | `EvidenceList / NodeQuestion / NodeNotebook / KnowledgePractice → EvidenceQuote` | 正文公式可渲染；代码证据不按数学解释；原文定位操作保留 |
| 节点问答正文 | `NodeQuestion → KnowledgeText` | 问题编辑框和选入笔记的保存文本保持原样 |
| 符号表、含义、维度、条件 | `FormulaContext → inlineMath / MathText` | 使用已保存字段，不猜补未知维度或符号定义 |
| 节点笔记摘要和编辑预览 | `NodeNoteSummary / NodeNotebook → KnowledgeText` | 摘要通过限制显示高度收起，避免切断公式字符串；编辑框保持源码；可展开全文 |
| 笔记与比较成果预览 | `NodeNotebook / ComparisonOutcome → KnowledgeText` | 阅读预览排版；“查看 Markdown 原文”保留可核对的原始导出文本，下载内容不变 |
| 比较表正文、兼容性说明、关系解释 | `KnowledgeComparison / KnowledgeComparisonRelations → MathText` | 修改表格内容的输入框不改；图谱短名称不变 |
| 跨论文概念定义、条件、历史判断 | `ConceptCorrespondence → MathText` | 双方证据仍通过 `EvidenceList` 核对；状态与保存逻辑不变 |
| 论文与代码对应关系 | 论文片段和说明使用 `KnowledgeText`；所选依据使用 `EvidenceQuote` | 代码片段和所选代码内容原样保留；“复制原文片段”保留准确的证据原文供绑定校验，不要求从渲染公式复制 |
| 代码练习题目、提示、教学假设、预期观察、运行预测与解释、AI 分析 | `KnowledgePractice → KnowledgeText` | Python 编辑器、参考代码、检查代码、历史源码、JSON 输入和程序输出不自动解释为数学 |
| 学习路线依据与历史节点说明 | `LearningRoute → EvidenceQuote / MathText` | 路线修订、核对、跳过、完成状态和依据版本不变 |
| 教学检查问题、选项、反馈和回答历史 | `LearningCheck → MathText` | 选项值、回答状态、理由编辑框与提交逻辑不变 |
| 学习记录与阶段建议 | `LearningProgress → MathText` | 原状态保存和建议生成流程不变；只替换记录及建议正文的展示 |
| 节点修订历史、知识路径的关系解释 | `KnowledgeReview / KnowledgePathPanel → MathText` | 历史快照和用户判断不变 |
| 通用课程、AI 导师正文 | 既有 `MathText` 入口继承本轮共享修复 | 课程代码练习与字面输入不经过数学改写 |

文件名、按钮标题、筛选项、图谱短名称、原始编辑输入、代码、机器输出及明确标注的 Markdown 原文不强制转成数学。这些内容承担标识、编辑或精确复制功能。

## 自动化验收

专项测试新增和覆盖：

- 裸多头注意力 `aligned`，含空行、两行等式和嵌套 `bmatrix`，只有一个完整数学块；MathML 的原始 TeX annotation 与输入一致。
- `align`、`gathered`、`cases`、`pmatrix`、`array`，以及无元数据的独立分数和缩放公式。
- 四种常见定界符、已带定界符的元数据不会重复包装。
- 未知宏不泄漏红色源码，可展开及收起精确原式。
- JSON 解码后的制表符、回车、行内意外换行、双重转义、未闭合环境不被猜修为正确数学。
- CRLF 多行公式正常排版，输入字符串保持原样。
- fenced code、inline code、代码证据与真实代码阅读器不把公式字符串、美元符号或反斜杠解释为数学。
- 普通原文内容块即使没有 `metadata.latex` 也能渲染明确的裸公式。
- 符号、含义、维度和条件使用同一渲染链路。

已完成的专项检查：

```text
node scripts/test.mjs src/__tests__/MathTextRendering.test.tsx src/__tests__/SourceFormulaReading.test.tsx --reporter=dot
2 files, 28 tests passed

node node_modules/typescript/bin/tsc -b --pretty false
passed
```

初轮广泛入口回归为 15 文件、119 项通过、3 项失败。三个失败均已定位为测试接口或 DOM 假设需要随现有功能更新：

- 概念判断历史段落现在包含共享数学组件；原测试要求文本直接属于 `p`，且同文案也存在于编辑框。定向定位到“查看原判断及版本快照”内的正文，保留历史判断可读及驳回保存断言。
- 无效 JSON 的练习测试假设全页只有一个 `alert`；学习状态读取失败也有独立提示。改为检查存在包含准确 JSON 错误的 `alert`，保留“不会启动运行器”的断言。
- 比较单元格测试仍 mock 旧 `knowledge.reviseKnowledgeComparison`，实际界面已经调用 `knowledgeComparison.reviseComparisonCell`，导致记录的 PATCH 次数为零。更新实际 helper 的 mock 并隔离依据读取请求，保留原版本、文本、自动预览及人工修改保存断言；没有为此更改比较状态逻辑。修正后保存单例通过。

最终定向复验：**5 文件、54 项全部通过**，包含上述 3 个修正测试文件和 2 个数学专项文件，未重复执行整组 15 文件：

```text
node scripts/test.mjs src/__tests__/MathTextRendering.test.tsx src/__tests__/SourceFormulaReading.test.tsx src/__tests__/ConceptCorrespondence.test.tsx src/__tests__/KnowledgePractice.test.tsx src/__tests__/KnowledgeComparisonAuto.test.tsx --reporter=dot
5 files, 54 tests passed
```

- [初轮入口回归日志](../../.tmp/math-rendering-tests.log)：15 文件、119 项通过、3 项失败，保留原始失败记录。
- [比较 helper 修正后的保存单例](../../.tmp/math-comparison-save-fixed.log)：1 项通过，原版本、文本和自动预览断言均保留。
- [最终定向复验日志](../../.tmp/math-rendering-final.log)：5 文件、54 项通过。

最后一处产品变更为 `KnowledgeSources` 对显式公式内容块的包装，时间 20:24:46；本轮最终生产构建完成于 20:25:03，已包含全部产品修改。此后仅更新测试和验收文档。上述单元及组件测试不是对数学内容正确性的科学认证。

## 真实浏览器验证

本轮隔离浏览器工程验收共 8 组通过。公式组在实际 API 人工修订并重开的讲解中完成，验证：

- `katex-display` 公式块为 2 个，分别包含多头注意力 `MultiHead/aligned` 及嵌套 `bmatrix`。
- `katex-error` 为 0；未知宏出现可恢复提示，点击“查看原式”后 `code.learning-math-original` 与固定输入完全一致。
- 已目视 1366 桌面深色状态下的两行等式和矩阵，均清晰可读。
- 完整工作台验收还检查了原文定位与返回、草稿、学习状态及不同桌面尺寸；本文件只将其中公式结果作为本轮渲染验收。

证据文件：

- [浏览器报告](../../.ui_validation/learning-desk-20261117/desk-browser/report.json)，公式检查名 `bare_aligned_and_nested_matrices_render_with_recoverable_fallback`。
- [1366 深色公式与笔记截图](../../.ui_validation/learning-desk-20261117/desk-browser/1366-dark-math-and-notes.png)。

补充的显式 `kind=formula`、无 `metadata.latex`、内容 `y=x^2` 案例由组件测试覆盖，未宣称该单项已做浏览器复核。浏览器采用固定 HTTP 模型传输桩，不能据此宣称真实外部模型输出质量得到验证。

本轮没有真实模型调用，没有修改正常研究空间数据库。浏览器验收使用隔离资料及人工修订的公式案例。
