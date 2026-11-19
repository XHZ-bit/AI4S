"""Authored introductory lessons used as optional, source-independent supplements."""

FOUNDATIONS = {
    "dot_product": {
        "pattern": r"dot[ -]?product|inner[ -]?product|点积|内积|query vector|key vector|查询向量|键向量",
        "label": "向量点积",
        "summary": "把同位置的两个分量相乘，再把乘积相加，得到一个标量。点积分数需要结合向量长度、量纲和后续计算理解。",
        "url": "https://numpy.org/doc/stable/reference/generated/numpy.dot.html",
        "sections": {
            "overview": "把两个向量想成两张按同一顺序列出的特征表。点积先比较每个位置，再把各位置的贡献加起来。每个位置的名称和顺序需要一致。",
            "definition": r"对两个长度相同的实向量，$q^T k=\sum_{i=1}^{d}q_i k_i$。例如 $q=[1,2]$、$k=[2,3]$，点积为 $1\times2+2\times3=8$。",
            "derivation": "先算第一维的贡献1×2=2，再算第二维的贡献2×3=6，最后相加得到8。改变一个分量，可以在交互演示中看到该位置怎样改变总分。",
            "prerequisites": "先确认向量表示哪些量、分量顺序和长度。若长度不一致，需要先检查原文定义及代码的张量形状。",
            "implementation": "交互演示固定两个维度，逐项计算并显示乘积。当前论文采用的实际维度、缩放和归一化方式需回到原文核对。",
            "limitations": "本页是通用教学补充。点积的数值可以为负或大于1；把它解释为相关性或注意力分数时，需要给出当前模型的定义和条件。",
        },
    },
    "scaled_attention": {
        "pattern": r"scaled[ -]?dot|缩放点积|注意力|attention|\bQK\b",
        "label": "缩放点积与注意力权重",
        "summary": "先将点积分数除以键向量维度的平方根，再沿一组候选位置做softmax。缩放分数和最后的权重处在不同计算步骤。",
        "url": "https://arxiv.org/abs/1706.03762v7",
        "sections": {
            "overview": "对一个查询位置，可以先给每个候选位置打分，再把这些分数一起变成权重。缩放操作位于点积和softmax之间。",
            "definition": r"教学计算采用 $\operatorname{Attention}(Q,K,V)=\operatorname{softmax}(QK^T/\sqrt{d_k})V$。$d_k$为键向量维度，softmax需要指定候选位置这一轴。",
            "derivation": r"给定教学点积分数 $[8,4,0]$、$d_k=4$，除以 $\sqrt{4}=2$ 后得到 $[4,2,0]$，再做softmax约为 $[0.8668,0.1173,0.0159]$。之后按这些权重对V加权求和。",
            "prerequisites": "可先看向量点积，接着区分任意实数分数与概率权重，再观察softmax怎样同时使用多个分数。",
            "implementation": "修改教学点积分数和d_k，逐列观察缩放分数及权重。此演示没有训练模型，也没有替当前论文提供缺失的实现。",
            "limitations": "4.0是本教学输入下softmax之前的单个分数。完整注意力输出还取决于其他位置、掩码和V。论文是否采用此机制及其维度需要按各自原文核对。",
        },
    },
    "softmax": {
        "pattern": r"softmax|归一化权重|注意力权重|normalized weights?|概率权重",
        "label": "softmax与归一化权重",
        "summary": "对一组分数取指数，再分别除以指数之和，得到总和为1的正权重。每项权重同时依赖其他候选的分数。",
        "url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.softmax.html",
        "sections": {
            "overview": "softmax把同一组候选放在一起比较。一个位置的分数提高时，它的权重通常增加，其他位置的权重也会随之改变。",
            "definition": r"对有限实数分数，$p_i=\exp(s_i)/\sum_j\exp(s_j)$。每项严格大于0，总和为1。数值实现可以先从所有分数减去相同的最大值。",
            "derivation": r"对 $[4,2,0]$，先减去4得到 $[0,-2,-4]$，指数约为 $[1,0.1353,0.0183]$，除以总和后约为 $[0.8668,0.1173,0.0159]$。",
            "prerequisites": "需要知道指数函数为正，以及一组互斥且穷尽的候选权重总和为1。原分数仍可以为负或大于1。",
            "implementation": "交互演示采用减去最大值的计算方式。将所有分数同时加10，权重保持相同，可检查它主要依赖分数之间的差异。",
            "limitations": "softmax的归一化形式本身不保证模型预测经过校准。掩码、计算轴和温度等额外设置需要结合实际方法核对。",
        },
    },
    "probability": {
        "pattern": r"probabilit|概率|随机事件|事件空间|sample space|normalized weights?|softmax|置信度",
        "label": "概率、计数与观察频率",
        "summary": "概率描述指定随机机制下事件发生的可能性。有限次观察的频率会波动，分数与概率需要分别识别。",
        "url": "https://openstax.org/books/introductory-statistics-2e/pages/3-1-terminology",
        "sections": {
            "overview": "先说明随机过程、所有可能结果，以及关心的是哪个事件，再讨论它的概率。观察到的次数可以用来计算频率。",
            "definition": r"事件概率满足 $0\leq P(A)\leq1$。当有限样本空间中每个结果等可能时，$P(A)=|A|/|S|$。观察频率为事件发生次数除以试验次数。",
            "derivation": "教学袋中有3个红球、2个蓝球、1个白球，各球被等可能抽到。有放回抽取时红球概率为3/6=0.5。抽取12次后红球出现次数可以随抽样而变。",
            "prerequisites": "明确事件、样本空间、是否等可能，以及每次抽取后是否放回。不同随机机制会改变概率计算。",
            "implementation": "交互演示允许修改球的数量并模拟有放回抽取12次，分别显示理论概率和本次实际计数。",
            "limitations": "有限次观察的频率可以偏离给定概率。论文中的模型置信度、概率密度和原始打分各有定义，需先核对术语及计算步骤。",
        },
    },
    "research_design": {
        "pattern": r"研究设计|实验设计|实验条件|对照组|实验组|控制变量|随机分配|自变量|因变量|study design|experimental design|control group|random(?:ly)? assign|randomi[sz]ed|controlled trial|treatment|delayed recall|延迟回忆",
        "label": "研究变量、对照与实验条件",
        "summary": "比较研究需要说明改变了什么、测量了什么，以及各组哪些条件相同。随机分配和随机抽样回答不同的问题。",
        "url": "https://openstax.org/books/introductory-statistics-2e/pages/1-4-experimental-design-and-ethics",
        "sections": {
            "overview": "阅读研究时，可以先找研究者改变的因素和记录的结果，再检查组间其他差别。它们共同决定结论可以怎样解释。",
            "definition": "教学例中，学习方式是比较因素，随后回忆出的项目数是结果。材料、学习时长、测试间隔及评分办法需要逐项记录，随机分配描述参与者怎样进入各组。",
            "derivation": "若一组学习5分钟后立即测试，另一组学习10分钟后一周再测试，观察到差异时同时涉及学习时长和测试间隔。把这些条件对齐，可以缩小解释差异的范围。",
            "prerequisites": "先区分被比较的因素、测量结果、实验单位和其他可能影响结果的变量。随后核对分组方式及测量过程。",
            "implementation": "交互演示允许改动两组学习时长、测试间隔和分组方式，并列出尚需核对的差异。数值均为自编教学设置。",
            "limitations": "随机分配帮助减少分组选择带来的混杂，仍需核对样本规模、执行过程、测量与统计不确定性。真实论文的因果结论需要其完整设计与证据。",
        },
    },
    "sampling": {
        "pattern": r"样本|总体|抽样|随机抽取|志愿报名|代表性|sample size|sampling|population|participants|受试者|研究对象",
        "label": "样本、总体与结论范围",
        "summary": "样本是实际观察的对象，总体是希望讨论的对象范围。样本量与抽样方式都影响如何解释和推广观察结果。",
        "url": "https://openstax.org/books/introductory-statistics-2e/pages/1-2-data-sampling-and-variation-in-data-and-sampling",
        "sections": {
            "overview": "阅读结果之前，先问实际观察了谁，以及结论想适用于谁。参与者来自哪个群体、怎样被选入，都应保留。",
            "definition": r"教学总体有N人，实际观察n人，其中k人支持某方案，则样本比例为 $\hat p=k/n$。总体中的支持比例需要额外信息。",
            "derivation": "例如从1000人中观察100人，其中30人支持方案，已观察样本的比例为30%。仅凭这个计数，无法确定其余900人的选择。",
            "prerequisites": "区分总体、抽样框、样本和样本统计量。随机抽取描述谁进入样本，随机分配描述样本内谁接受哪种处理。",
            "implementation": "交互演示修改总体人数、样本量、支持人数和抽样方式，检查样本比例以及结论适用范围。",
            "limitations": "增加来自同一便利渠道的样本，仍可能保留选择偏差。比例、误差区间和推广范围需要结合抽样、未回应及实际研究条件判断。",
        },
    },
}


def catalog():
    return {key: {field: value[field] for field in ('pattern', 'label', 'summary', 'url')}
            for key, value in FOUNDATIONS.items()}


def sections(key):
    item = FOUNDATIONS.get(key)
    return dict(item['sections']) if item else None


def references(keys):
    return {key: '\n\n'.join(FOUNDATIONS[key]['sections'].values())
            for key in dict.fromkeys(keys) if key in FOUNDATIONS}
