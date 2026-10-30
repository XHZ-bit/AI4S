"""Authored foundation lessons and deterministic checks; no model needed."""
from app.diffusion_curriculum import LESSONS as DIFFUSION_LESSONS

LESSONS = [
    {
        "id": "probability", "title": "概率分布与期望", "minutes": 15, "prerequisites": [], "visual": "probability",
        "summary": "读懂模型所说的“随机”：哪些结果可能出现，每个结果有多大可能？",
        "connection": "生成模型学习的是数据的分布。扩散模型的噪声和采样，首先建立在随机变量和概率分布上。",
        "steps": [
            {"question": "随机变量是什么？", "explanation": "随机变量是把随机结果映射成数值的规则。例如抛硬币，规定正面为 1、反面为 0，得到随机变量 X。X 不是固定的未知常数；重复试验时，它可以有不同取值。", "example": "一次试验得到 X=1，并不意味着以后都会是 1。概率分布描述多次重复试验的可能性。"},
            {"question": "分布为什么要加起来等于 1？", "explanation": "离散分布为每个互斥且穷尽的结果分配概率：$p_i\\geq0$，且 $\\sum_i p_i=1$。总和为 1 表示某个可能结果一定会发生。", "example": "公平骰子的六个结果各为 1/6。若只记录奇偶，则奇数和偶数各为 1/2。"},
            {"question": "期望是不是最可能出现的值？", "explanation": "期望是按概率加权的平均：$$\\mathbb E[X]=\\sum_i p_i x_i$$它不一定是某次能观察到的结果。伯努利变量取 0 或 1，若正面概率为 p，期望就是 p。", "example": "p=0.7 时，期望是 0.7，但单次结果仍然只能是 0 或 1。样本均值在独立同分布等条件下随样本量增加趋近期望。"}
        ],
        "terms": [{"term": "随机变量", "definition": "把随机试验的结果对应到数值的函数。"}, {"term": "分布", "definition": "描述随机变量各取值的概率；连续变量通常用密度及区间积分描述。"}, {"term": "期望", "definition": "按概率加权的平均，不等同于众数，也不是一次试验的结果。"}],
        "quiz": [{"question": "X 只能取 0 或 1，P(X=1)=0.8。它的期望是什么？", "options": ["1，因为它更常出现", "0.8，按概率加权", "0.5，两个取值的平均"], "answer": 1, "explanation": "E[X]=0×0.2+1×0.8=0.8。不能忽略概率权重。"}, {"question": "公平骰子的期望为 3.5，这意味着什么？", "options": ["骰子有时会掷出 3.5", "每次都会接近 3.5", "大量独立投掷的均值趋近 3.5"], "answer": 2, "explanation": "期望不必属于可取值集合；大数定律描述样本均值，而不是每次结果。"}],
        "exercise": {"id": "expectation", "kind": "代码填空", "title": "实现离散期望", "prompt": "补全函数中的 ...，计算给定取值与概率的加权平均。返回数值，不要只打印。", "starter": "def expectation(values, probs):\n    return ...\n\nprint(expectation([0, 1], [0.3, 0.7]))", "hint": "把同一位置的 value 和 probability 相乘，再求和。可以使用 zip 和 sum。", "tests": "assert abs(expectation([0, 1], [0.3, 0.7]) - 0.7) < 1e-8\nassert abs(expectation([1, 2, 3], [0.2, 0.3, 0.5]) - 2.3) < 1e-8\nassert expectation([5], [1]) == 5", "solution": "def expectation(values, probs):\n    return sum(x * p for x, p in zip(values, probs))", "test_count": 3}
    },
    {
        "id": "vectors", "title": "向量、矩阵与点积", "minutes": 18, "prerequisites": [], "visual": "vectors",
        "summary": "把一组特征看成向量，理解矩阵如何把输入映射到输出。", "connection": "神经网络常用矩阵乘法组织特征变换，注意力中的相似度也与点积有关。",
        "steps": [
            {"question": "为什么用向量表示数据？", "explanation": "向量把有顺序的一组数字作为整体。例如 $x=(温度,速度)$。每个分量有自己的语义、单位和位置。维度是分量个数；样本数量和单个样本的维度是不同的概念。", "example": "三张 28×28 灰度图像可以展平成形状 (3,784) 的矩阵：3 是样本数，784 是特征维度。"},
            {"question": "点积计算了什么？", "explanation": "同维向量的点积是对应分量乘积之和：$$a^Tb=\\sum_i a_i b_i$$当使用欧氏几何时，也等于 $\\|a\\|\\|b\\|\\cos\\theta$。它受长度与夹角共同影响，不能直接当作归一化相似度。", "example": "a=(1,2)，b=(3,4)，点积为 1×3+2×4=11。注意这不是逐元素乘积 (3,8)。"},
            {"question": "矩阵乘向量怎么确定形状？", "explanation": "若 $W\\in\\mathbb R^{m\\times n}$、$x\\in\\mathbb R^n$，则 $Wx\\in\\mathbb R^m$。每个输出分量是 W 的一行与 x 的点积。输入维数必须与 W 的列数相同。", "example": "W 有 2 行 3 列，x 有 3 个数，则输出有 2 个数。先检查形状，再调试数值。"}
        ],
        "terms": [{"term": "张量", "definition": "按多个轴组织的数值数组。标量、向量和矩阵分别是常见的零阶、一阶和二阶情况。"}, {"term": "形状", "definition": "各个轴的长度，例如 (batch, features)；轴的语义要根据代码或论文确认。"}],
        "quiz": [{"question": "W 的形状为 (2,3)，x 的形状为 (3,)，Wx 的形状是？", "options": ["(3,2)", "(2,)", "(3,)"], "answer": 1, "explanation": "每一行与 x 做一次点积，2 行产生 2 个输出。"}, {"question": "Python 中 sum(a) * sum(b) 是否等于两个向量的点积？", "options": ["一般不相等，它多出了交叉项", "总是相等", "仅取决于向量长度"], "answer": 0, "explanation": "点积只累加对应位置的乘积，不能把分别求和再相乘当作点积。"}],
        "exercise": {"id": "dot", "kind": "调试改错", "title": "修复点积计算", "prompt": "下面的函数能运行，但结果有逻辑错误。修复它，支持任意相同长度的一维列表。", "starter": "def dot(a, b):\n    return sum(a) * sum(b)\n\nprint(dot([1, 2], [3, 4]))", "hint": "不要分别求和。先把对应位置相乘，最后加起来。", "tests": "assert dot([1, 2], [3, 4]) == 11\nassert dot([0, 1, -1], [2, 3, 5]) == -2\nassert dot([], []) == 0", "solution": "def dot(a, b):\n    return sum(x*y for x, y in zip(a,b))", "test_count": 3}
    },
    {
        "id": "gradient", "title": "损失、梯度与参数更新", "minutes": 20, "prerequisites": ["vectors"], "visual": "gradient",
        "summary": "理解模型如何从一个错误数字，走向下一次参数更新。", "connection": "训练扩散网络、策略网络和分类器时，都需要定义损失并通过梯度更新参数。",
        "steps": [
            {"question": "损失与参数有什么关系？", "explanation": "参数是模型可调整的数，损失是评估预测与目标差异的函数。以 $L(w)=(w-3)^2$ 为例，w=3 时损失最小；w=0 时损失为 9。损失的设计会影响模型学到什么。", "example": "单个预测误差变小不一定说明泛化更好，还需要独立验证数据。"},
            {"question": "梯度告诉我们什么？", "explanation": "一维时导数表示局部变化率；多维时梯度由各偏导数组成。这里 $L'(w)=2(w-3)$。负梯度方向在足够小步长下使局部损失下降。", "example": "w=0 时梯度为 -6。减去这个负数会增大 w，使它朝 3 移动。"},
            {"question": "为什么不能把学习率开得很大？", "explanation": "梯度下降更新为 $$w_{t+1}=w_t-\\eta\\nabla L(w_t)$$学习率 η 控制每次走多远。步子过大可能越过最低点并发散；非凸问题也不能保证找到全局最优。", "example": "w=0，η=0.1，下一步是 0.6；η=1.2，下一步是 7.2，距离 3 反而更远。"}
        ],
        "terms": [{"term": "反向传播", "definition": "使用链式法则高效计算损失对各参数的导数；它计算梯度，本身不等于优化器更新。"}, {"term": "学习率", "definition": "优化器更新的步长系数；与批大小、优化器和损失尺度共同影响训练。"}],
        "quiz": [{"question": "w=0，梯度为 -6，学习率为 0.1，更新后 w 是多少？", "options": ["-0.6", "0.6", "6"], "answer": 1, "explanation": "w_new=0-0.1×(-6)=0.6。更新公式中的减号不能丢。"}, {"question": "训练损失持续下降，可以直接断言模型泛化更好了吗？", "options": ["可以", "不可以，还需要验证集和适当指标"], "answer": 1, "explanation": "训练集上的拟合与未见数据上的表现不同，可能出现过拟合。"}],
        "exercise": {"id": "gradient-step", "kind": "简单函数编写", "title": "写一次梯度下降", "prompt": "实现 step(w, lr)，对 L(w)=(w-3)^2 做一次更新，返回新参数。", "starter": "def step(w, lr):\n    # 写出梯度，再更新参数\n    ...\n\nprint(step(0, 0.1))", "hint": "梯度是 2*(w-3)，新参数是 w-lr*gradient。", "tests": "assert abs(step(0, 0.1)-0.6)<1e-8\nassert step(3, 0.1)==3\nassert abs(step(5, 0.2)-4.2)<1e-8", "solution": "def step(w, lr):\n    gradient = 2*(w-3)\n    return w-lr*gradient", "test_count": 3}
    },
    {
        "id": "conditioning", "title": "条件概率与贝叶斯更新", "minutes": 18, "prerequisites": ["probability"], "visual": "bayes",
        "summary": "看见新证据后，如何调整原来的判断？", "connection": "条件生成使用条件信息约束输出分布；条件概率帮助区分 p(动作|观测) 与 p(观测|动作)。",
        "steps": [
            {"question": "条件概率改变了什么？", "explanation": "当已知 B 发生时，只在 B 的样本空间里重新比较 A 所占比例：$$P(A\\mid B)=\\frac{P(A\\cap B)}{P(B)}$$要求 P(B)>0。条件不是时间先后，也不自动代表因果关系。", "example": "100 人中 20 人戴眼镜，其中 8 人喜欢篮球。已知戴眼镜时，喜欢篮球的概率为 8/20。"},
            {"question": "为什么不能交换条件？", "explanation": "P(A|B) 和 P(B|A) 的分母不同。贝叶斯公式建立联系：$$P(A\\mid B)=\\frac{P(B\\mid A)P(A)}{P(B)}$$P(A) 是先验；P(B|A) 是似然；结合证据得到后验。", "example": "阳性不等于一定患病。若患病率 1%，灵敏度 90%，误报率 10%，则阳性后患病概率约为 0.009/(0.009+0.099)=8.33%。"}
        ],
        "terms": [{"term": "先验", "definition": "纳入当前证据之前的概率判断。"}, {"term": "似然", "definition": "在给定假设下观察到该证据的可能性；不要与假设的后验概率混淆。"}, {"term": "后验", "definition": "利用当前证据更新后的概率判断。"}],
        "quiz": [{"question": "P(阳性|患病)=90%，是否意味着 P(患病|阳性)=90%？", "options": ["是，同一个事件", "否，还取决于患病率与误报率"], "answer": 1, "explanation": "条件不能直接互换，必须考虑基率与其他群体产生证据的可能性。"}],
        "exercise": {"id": "bayes", "kind": "代码分析与实现", "title": "正确计算后验概率", "prompt": "prior 是患病率，sensitivity 是灵敏度，false_positive 是健康人误报率。写出 posterior，返回阳性后患病概率。思考：分母为什么不能只有 sensitivity？", "starter": "def posterior(prior, sensitivity, false_positive):\n    true_positive = prior * sensitivity\n    # 补全所有阳性的概率，再返回后验\n    ...", "hint": "所有阳性 = 患病且阳性 + 健康但误报。后者是 (1-prior)*false_positive。", "tests": "assert abs(posterior(0.01,0.9,0.1)-1/12)<1e-8\nassert abs(posterior(0.5,0.9,0.1)-0.9)<1e-8\nassert posterior(0.1,1,0)==1", "solution": "def posterior(prior, sensitivity, false_positive):\n    true_positive = prior*sensitivity\n    return true_positive/(true_positive+(1-prior)*false_positive)", "test_count": 3}
    },
    {
        "id": "pipeline", "title": "把方法写成可检查的代码", "minutes": 25, "prerequisites": ["vectors", "gradient"], "visual": "pipeline",
        "summary": "从输入、变换到输出，用模块组织一个最小线性预测器。", "connection": "读论文方法时，先把算法拆成输入输出明确的模块，再判断各模块需要的数据、形状和验证条件。",
        "steps": [
            {"question": "为什么先写接口再写实现？", "explanation": "模块接口说明输入、输出及前提条件。线性预测器可写成 $y=Wx+b$。输入、权重、偏置的形状必须兼容；函数只完成一件明确的事，更容易单独验证。", "example": "把 dot、linear、predict_batch 分开：先验证单个向量，再验证单个样本输出，最后验证批处理。"},
            {"question": "如何从代码层面检查理解？", "explanation": "先手算一个小样例，预测代码输出；再运行对照。为零输入、负数与不同样本编写测试。样例通过只证明这些输入上的行为符合预期，不等于复现完整论文。", "example": "W=[[1,0],[0,2]]，x=[3,4]，b=[1,-1]，应输出 [4,7]。批处理两个样本时，每个样本独立通过同一个 linear。"}
        ],
        "terms": [{"term": "批处理", "definition": "把多个样本作为一组处理。要明确 batch 轴，避免把样本数和特征数混淆。"}, {"term": "单元测试", "definition": "针对明确接口与输入，检查程序输出是否符合预期；覆盖有限输入，不证明所有情况正确。"}],
        "quiz": [{"question": "一批 8 个样本，每个样本 3 维，线性层输出 2 维。批输出形状是？", "options": ["(8,2)", "(2,3)", "(3,8)"], "answer": 0, "explanation": "每个样本经过同一个从 3 维到 2 维的变换，batch 数仍为 8。"}],
        "exercise": {"id": "linear-batch", "kind": "模块化编写", "title": "搭建一个最小线性层", "prompt": "依次实现 dot、linear 与 predict_batch。linear 对 W 每一行与 x 做点积并加对应偏置；predict_batch 处理输入样本列表。", "starter": "def dot(a, b):\n    ...\n\ndef linear(x, weights, bias):\n    ...\n\ndef predict_batch(samples, weights, bias):\n    ...\n\nprint(predict_batch([[3,4],[0,1]], [[1,0],[0,2]], [1,-1]))", "hint": "linear = [dot(row,x)+offset for row,offset in zip(weights,bias)]；批处理对每个样本调用 linear。", "tests": "assert dot([1,2],[3,4])==11\nassert linear([3,4],[[1,0],[0,2]],[1,-1])==[4,7]\nassert predict_batch([[3,4],[0,1]],[[1,0],[0,2]],[1,-1])==[[4,7],[1,1]]\nassert predict_batch([],[[1,0]],[0])==[]", "solution": "def dot(a,b):\n    return sum(x*y for x,y in zip(a,b))\n\ndef linear(x,weights,bias):\n    return [dot(row,x)+offset for row,offset in zip(weights,bias)]\n\ndef predict_batch(samples,weights,bias):\n    return [linear(x,weights,bias) for x in samples]", "test_count": 4}
    }
]


LESSONS.extend(DIFFUSION_LESSONS)

def find_lesson(identity):
    return next((lesson for lesson in LESSONS if lesson["id"] == identity), None)


def visible(lesson, features):
    result = dict(lesson)
    result["quiz"] = [{"question": q["question"], "options": q["options"]} for q in lesson["quiz"]] if features.get("quizzes", True) else []
    if not features.get("glossary", True):
        result["terms"] = []
    if not features.get("visuals", True):
        result["visual"] = None
    if not features.get("coding", True):
        result["exercise"] = None
    return result
