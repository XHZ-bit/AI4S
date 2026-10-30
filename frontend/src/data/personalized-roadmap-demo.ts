export const demoSources = {
  imitation: {title: "What Matters in Learning from Offline Human Demonstrations for Robot Manipulation", short: "RoboMimic · 离线模仿学习", url: "https://arxiv.org/abs/2108.03298v2", focus: "示范数据、行为克隆与评估设置"},
  diffusion: {title: "Denoising Diffusion Probabilistic Models", short: "DDPM · 扩散模型基础", url: "https://arxiv.org/abs/2006.11239v2", focus: "前向加噪、去噪训练与采样算法"},
  policy: {title: "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion", short: "Diffusion Policy · 动作生成", url: "https://arxiv.org/abs/2303.04137v4", focus: "条件动作生成、动作序列与滚动执行"},
};
export type ModuleId = "imitation" | "diffusion" | "policy" | "validation";
export type Foundation = "imitation" | "diffusion";
export interface DemoModule {
  id: ModuleId; title: string; purpose: string; source: keyof typeof demoSources;
  tasks: {title: string; action: string; output: string}[];
  question: string; answer: string; artifact: string;
}
export const demoModules: Record<ModuleId, DemoModule> = {
  imitation: {
    id: "imitation", title: "建立机器人模仿学习的问题框架", source: "imitation",
    purpose: "先明确示范数据、策略输入输出和评估对象，避免把生成质量直接当作机器人任务成功率。",
    tasks: [
      {title: "梳理示范数据", action: "阅读 RoboMimic 对离线示范与任务评估的介绍，区分观察、动作、轨迹和任务。", output: "画出 observation → policy → action 数据流，标注哪些量来自示范。"},
      {title: "理解行为克隆", action: "用监督学习解释行为克隆，讨论训练数据覆盖不足时，执行状态如何偏离示范分布。", output: "写出一个执行偏离的具体例子，区分训练误差与任务成功率。"},
      {title: "设计最小比较", action: "固定任务、观察与动作接口，列出比较两种策略前必须控制的条件。", output: "完成数据来源、划分、观察模态、训练预算、测试条件五项核对表。"},
    ],
    question: "训练误差相近，是否足以说明两个策略的机器人任务表现相近？",
    answer: "不足以。闭环执行会产生新的状态分布，训练误差不能代替同一任务、环境与测试条件下的执行评估。还需要检查示范覆盖和测试协议。",
    artifact: "任务：桌面推块。观察：图像与机器人状态。动作：控制接口规定的向量。比较时使用同一批离线示范，统一观察、动作和测试条件；训练误差只反映对示范的拟合。",
  },
  diffusion: {
    id: "diffusion", title: "理解扩散模型的训练与采样", source: "diffusion",
    purpose: "把去噪训练与多步采样分开理解，再把生成对象从图像换成动作序列。",
    tasks: [
      {title: "读懂加噪与去噪", action: "对照 DDPM 的训练和采样算法，画出干净样本、噪声样本、噪声水平与去噪网络的关系。公式在 PDF 中核对。", output: "一张变量对照表，说明训练阶段已知什么、预测什么。"},
      {title: "写一个玩具过程", action: "用二维点或短向量演示逐步加噪，检查形状、噪声水平和重构接口。", output: "保存输入形状、每步噪声水平与输出形状的运行记录。"},
      {title: "迁移到动作序列", action: "把生成对象替换为动作片段，解释条件信息如何约束生成，记录推理步数的计算开销。", output: "解释去噪迭代次数和执行动作步数为什么是两个不同的量。"},
    ],
    question: "扩散模型的去噪迭代步数，就是机器人执行动作的步数吗？",
    answer: "不是。去噪迭代发生在生成动作序列的过程中；执行步数描述生成后交给控制器的动作数量。两者处于不同层次，需要分别记录。",
    artifact: "训练时从示范动作构造含噪输入，并在指定噪声水平下学习去噪。推理时从噪声逐步生成动作序列。这个玩具练习用于理解机制，尚未验证机器人任务表现。",
  },
  policy: {
    id: "policy", title: "连接视觉条件、动作预测与滚动执行", source: "policy",
    purpose: "把模仿学习和扩散基础连接成完整策略，重点检查时间窗口与张量接口。",
    tasks: [
      {title: "阅读策略数据流", action: "对照论文方法图，追踪观察条件、动作预测和滚动执行的先后关系。", output: "画出观察窗口、预测序列与实际执行片段的数据流。"},
      {title: "核对时间窗口", action: "在交互专题中设置 B=2、To=3、Do=20、Ta=4、Da=2，计算形状，再改变 To 和 Ta。", output: "观察 [2,3,20]、动作 [2,4,2]；解释 To 与 Ta 可以不同，Da 由动作接口决定。"},
      {title: "对照源码接口", action: "打开固定版本源码，核对输入字典、动作输出字段及模型预测窗口与执行窗口。", output: "记录源码位置、版本、变量含义和一个待核对的接口问题。"},
    ],
    question: "模型预测一段动作后，一定会把整段全部执行完再接收观察吗？",
    answer: "不一定。滚动执行通常只执行预测序列的一部分，再根据新观察重新规划。预测长度与执行长度应分别核对具体实现和配置。",
    artifact: "接口笔记：观察窗口说明使用多少历史信息；预测窗口说明生成多长动作序列；执行窗口说明更新观察前执行多少动作。不能因为三者都以时间步表示，就把它们混为一谈。",
  },
  validation: {
    id: "validation", title: "形成验证方案与学习报告", source: "policy",
    purpose: "把理解变成有输入、有产出、有验收范围的下一步，保留实验条件和未解决问题。",
    tasks: [
      {title: "完成源码检查", action: "用专题工具检查固定源码与接口，记录工具没有运行的实验。", output: "保存源码检查记录，明确检查通过能够证明什么。"},
      {title: "制定最小实验", action: "列出算力、数据和时间，选择可完成的接口或小规模实验，写明评价指标和失败判据。", output: "实验表包含目的、输入、配置、资源预算、预期产物和失败判据。"},
      {title: "整理证据与问题", action: "分别记录论文阅读、接口练习和源码检查，列出待验证假设。", output: "完整学习报告与下一轮行动清单，不填写未经运行的成功率。"},
    ],
    question: "源码版本和接口检查通过了，能否写“已经复现论文成功率”？",
    answer: "不能。源码与接口检查的范围小于真实策略评估。论文结果复现还需要相应数据、训练或权重、环境、配置与重复运行记录。",
    artifact: "验证计划：先保存接口检查日志；数据和硬件就绪后，在一个固定任务上小规模评估。统一观察、动作和协议，记录随机种子、运行次数及失败类型。当前没有真实策略成功率。",
  },
};
export const demoLearners = [
  {id: "robotics", name: "梁同学", role: "机器人方向", weeklyHours: 6,
    background: "熟悉行为克隆和 PyTorch，接触过机器人示范数据，还没有系统学习扩散模型。",
    known: ["imitation"] as Foundation[], goal: "理解 Diffusion Policy 的生成机制，并能核对策略接口。",
    constraint: "普通笔记本；先做向量与源码练习，暂不安排大规模训练。",
    rationale: "已有模仿学习基础，补齐扩散机制后进入动作策略和验证方案。",
    dialogue: [
      {question: "我会行为克隆，为什么还要先看 DDPM？", answer: "你已经理解从示范学习策略；现在的缺口是动作分布如何通过去噪生成。先把训练和采样分清，再读动作扩散。"},
      {question: "我把 To 和 Ta 都设成 4，程序能运行，说明它们必须相等吗？", answer: "这个例子只能说明该设置可用。把 To 改成 3，Ta 保持 4，再核对输入 [B,To,Do] 和输出 [B,Ta,Da]，检查理解是否依赖偶然相等。"},
      {question: "源码检查通过了，报告里怎么写？", answer: "写明已核对的固定版本与接口，列出检查产物。把真实策略评估列为后续工作，记录当前数据与算力限制。"},
    ], reflection: "原先把动作生成当作一次回归；现在能分别解释去噪过程、预测窗口与执行窗口。仍需核对具体控制任务中的动作参数化。",
    next: "选择可获得数据的固定任务，核对动作接口和官方评估配置，再决定是否做小规模训练。"},
  {id: "generative", name: "许同学", role: "生成模型方向", weeklyHours: 9,
    background: "熟悉 DDPM 训练与采样，能读去噪网络代码，缺少机器人闭环策略和示范数据经验。",
    known: ["diffusion"] as Foundation[], goal: "理解动作扩散与图像生成的区别，设计公平的策略比较。",
    constraint: "可用一张 GPU，但机器人数据与评估环境尚未准备。",
    rationale: "跳过扩散基础，先补示范数据与闭环评估，再学习策略时间窗口。",
    dialogue: [
      {question: "生成的动作序列平滑，就代表策略更好吗？", answer: "平滑只是动作的一个属性。任务表现还取决于观察、反馈和测试条件，要在同一任务与评估协议下记录结果。"},
      {question: "我熟悉扩散，能直接开始训练吗？", answer: "先检查示范数据中的观察和动作定义、训练与测试划分以及评估环境。能训练网络不等于设置已经匹配。"},
      {question: "比较行为克隆，需要统一什么？", answer: "核对示范数据、观察模态、动作接口、测试任务和协议，同时明确训练与推理预算。把差异写进报告。"},
    ], reflection: "原先用生成样本质量思考策略；现在会先检查闭环执行和评估，能说明同一动作分布在不同接口下为什么不能直接比较。",
    next: "准备固定任务的数据与评估环境，建立行为克隆基线；核对比较条件后再投入训练预算。"},
  {id: "starter", name: "陈同学", role: "跨方向入门", weeklyHours: 6,
    background: "具备 Python 与基础监督学习知识，尚未学习模仿学习和扩散模型。",
    known: [] as Foundation[], goal: "建立完整概念链，完成可解释的接口练习与学习报告。",
    constraint: "每周 6 小时、CPU 笔记本；先完成概念与接口验证。",
    rationale: "保留两个基础模块，先明确学习问题，再理解生成机制，最后连接成策略。",
    dialogue: [
      {question: "公式很多，需要先把每个推导都看完吗？", answer: "先明确公式描述的对象、变量与所在步骤，在 PDF 中核对版面。第一轮以解释数据流为目标，把不理解的推导记成后续问题。"},
      {question: "没有 GPU，还能完成什么？", answer: "可以完成论文阅读、短向量加噪、形状练习和源码检查。把完整训练和机器人评估单独列为后续范围。"},
      {question: "什么笔记能说明理解了？", answer: "用自己的话解释输入输出，给出一个参数变化例子，指出原文或源码位置，并保留仍不理解的问题。"},
    ], reflection: "能从示范数据讲到去噪生成，再讲到动作执行；已完成的是概念与接口学习，还需补充数学推导和真实环境经验。",
    next: "挑出最不确定的一个公式或接口问题，用小例子验证理解；资源就绪后再扩大实验范围。"},
];
export function routeModules(known: Foundation[]): DemoModule[] {
  return (["imitation", "diffusion", "policy", "validation"] as ModuleId[])
    .filter(id => !known.includes(id as Foundation)).map(id => demoModules[id]);
}
