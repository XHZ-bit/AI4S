"""Small authored node lessons, separate from source facts and saved AI artifacts.

Selection uses only the node's own title, summary and formula. A guide is a
read-only teaching aid: it neither adds graph dependencies nor fabricates paper
evidence, and it does not contact a model or an external resource.
"""

from __future__ import annotations

from copy import deepcopy
import re

from app.knowledge.foundations import FOUNDATIONS
from app.knowledge.attention_guides import GUIDES as ATTENTION_GUIDES
from app.knowledge.paper_reading_guides import get_paper_guide

VERSION = 'node-guide-v2'
KINDS = {'concept', 'formula', 'method', 'module', 'algorithm', 'experiment', 'finding', 'hypothesis'}

PATTERNS = {
    'multi_head_attention': r'\bmulti[\s\-‐‑–]*head[\s\-‐‑–]*attention\b|多头注意力',
    'cross_attention': r'\bcross[\s\-‐‑–]*attention\b|\bencoder[\s\-‐‑–]*decoder[\s\-‐‑–]*attention\b|交叉注意力|编码器[\s\-‐‑–—]*解码器注意力',
    'self_attention': r'\b(?:self|intra)[\s\-‐‑–]*attention\b|自注意力|句内注意力',
    'scaled_attention': r'scaled[\s\-‐‑–]*(?:dot[\s\-‐‑–]*product|attention)|缩放点积|缩放注意力',
    'softmax': r'\bsoftmax\b|归一化权重|归一化概率',
    'dot_product': r'\b(?:dot|inner)[\s\-‐‑–]*product\b|点积|内积',
    'probability': r'\bprobabilit(?:y|ies)\b|概率|随机事件|样本空间',
    'research_design': r'实验设计|研究设计|对照实验|对照组|控制组|随机分配|混杂|'
                       r'\b(?:study|experimental) design\b|\brandom assignment\b|\bcontrol group\b|'
                       r'\bconfound|retrieval practice|delayed recall|延迟回忆',
    'sampling': r'样本量|样本比例|总体|抽样|代表性|研究对象|受试者|'
                r'\bsample (?:size|proportion)\b|\bsampling\b|\bpopulation\b|\bparticipants\b',
}

SELF_ATTENTION = {
    'topic': 'self_attention',
    'title': '自注意力：让序列中的位置互相参考',
    'overview': '自注意力让同一序列中的一个位置，按当前需要，从允许访问的位置收集信息，'
                '形成带有上下文的新表示。“自”指查询与被参考的信息来自同一序列，'
                '并不是说一个位置只能看自己。',
    'why_it_matters': '理解它可以先回答三个问题：信息从哪里来，哪些位置允许被看到，'
                     '收集的信息怎样更新当前表示。这样可以把一句英文定义接到模型的数据流，'
                     '也更容易区分编码器、解码器和跨序列交互的设计。',
    'flow': [
        {'label': '从同一序列出发', 'text': '输入包含多个位置的表示。对于某个待更新位置，'
         '参考对象仍来自这一序列；输出通常为各查询位置分别保留更新后的表示。'},
        {'label': '区分查询、键和值', 'text': '查询Q表达当前在找什么，键K用于计算匹配程度，值V是被汇总的内容。'
         '常见Transformer写法从同一输入X用不同投影得到Q、K、V；来源相同不要求三个数值相同。'},
        {'label': '计算匹配并限制可见位置', 'text': '为查询和候选键计算分数。打分函数决定怎样比较，'
         '掩码决定哪些候选可以参与；用于自回归解码的因果掩码会屏蔽未来位置。'},
        {'label': '形成权重并汇总值', 'text': '在允许的候选位置上将分数转成权重，再按权重汇总V。'
         '缩放点积是常见打分实现，多头是并行组织多个注意力计算的方式，二者都不是“自”的定义。'},
    ],
    'example': {
        'title': '两位置教学例：只观察信息聚合',
        'body': '设位置1可以参考位置1和位置2，已经得到的注意力权重是0.75和0.25，'
                '对应的标量值分别为2和6。更新结果为 '
                r'$z=0.75\times2+0.25\times6=3$。'
                '\n\n这里的权重和数值是自编教学输入。它展示“按权重收集信息”这一步；'
                '没有从这些数值反推查询和键，也没有模拟训练过程。若掩码不允许访问位置2，'
                '就不能直接沿用这组双位置权重。',
    },
    'key_points': [
        '先看Q与K、V各自来自哪份序列，判断自注意力还是交叉注意力。',
        '同一序列可以形成不同的查询、键和值表示，不能把“同源”理解为“相等”。',
        '输出是汇总后的表示；注意力权重、打分和最终表示是不同对象。',
        '实际可用上下文由掩码和数据组织决定，不能从“自注意力”一词推断可以看全部位置。',
    ],
    'common_confusions': [
        {'claim': '“自注意力就是只关注自己的位置。”',
         'explanation': '它可以参考同一序列中的其他允许位置。“自”描述来源，不描述只剩一条自连接。'},
        {'claim': '“自注意力、缩放点积注意力和多头注意力是同一个名称。”',
         'explanation': '自注意力说明信息来源；缩放点积说明一类打分与归一化实现；多头说明并行组织方式。'
                        '这些属性可以同时出现，也需要分别检查。'},
        {'claim': '“用了掩码就变成交叉注意力。”',
         'explanation': '掩码改变可访问位置；交叉注意力则通常让Q来自一份序列，K、V来自另一份序列。'},
    ],
    'questions': [
        '在当前方法中，Q、K、V分别来自哪份输入？',
        '更新一个位置时，哪些位置被掩码排除？',
        '如果固定V，只改变一项注意力权重，输出会怎样变化？',
    ],
    'demo_ids': [],
    'boundary': '以上流程适用于理解序列中的信息聚合。具体打分函数、归一化轴、'
                '位置编码、掩码及多头投影需要分别检查；交叉注意力的查询来源与键值来源不同。',
    'references': [{'title': 'Attention Is All You Need', 'url': 'https://arxiv.org/abs/1706.03762v7'}],
}

DETAILS = {
    'scaled_attention': {
        'title': '缩放点积：先比较，再归一化，最后汇总',
        'why_it_matters': '把公式拆成不同的中间量，可以核对代码究竟返回了点积分数、'
                         '缩放后的分数、归一化权重还是最终输出，并用简单数字检查运算顺序。',
        'flow': [
            {'label': '逐个候选算点积', 'text': '对一个查询q与各候选键k计算匹配分数。教学输入先给定一组分数[8,4,0]。'},
            {'label': '按键维度缩放', 'text': '给定d_k=4，每项除以sqrt(4)=2，得到[4,2,0]。单个4.0仍是分数。'},
            {'label': '在候选轴上归一化', 'text': '对整组缩放分数做softmax，得到约[0.8668,0.1173,0.0159]；掩码决定允许参与的位置。'},
            {'label': '按权重汇总V', 'text': '权重用于对各候选值加权求和。没有V的数值，就不能仅从上述分数给出完整注意力输出。'},
        ],
        'key_points': ['d_k是正的键向量维度，缩放分母是它的平方根。',
                       '分数可以为负或大于1，归一化权重是另一个计算阶段。',
                       '一组权重需要说明计算轴、候选范围及掩码。'],
        'common_confusions': [
            {'claim': '“4.0就是模型分配的注意力概率。”', 'explanation': '本教学输入中的4.0位于softmax之前，归一化权重还依赖同组其他分数。'},
            {'claim': '“把d_k增大，所有注意力结果都会更好。”', 'explanation': '固定点积时增大分母会压小分数；这只能说明当前计算，不能直接推出模型效果。'},
        ],
        'questions': ['固定点积8，把d_k由4改成16，缩放分数是多少？',
                      '当前代码返回值处于公式哪一步？', 'softmax沿哪个轴计算，哪些位置被屏蔽？'],
        'boundary': '教学数值没有包含训练、掩码和V的加权结果。完整实现需要核对张量维度、归一化轴和允许访问的位置。',
    },
    'softmax': {
        'title': 'Softmax：把一组分数转换为相对权重',
        'why_it_matters': '研究中的一个分数经常需要与其他候选一起解释。理解归一化，'
                         '可以看清一个位置变化为何影响整组权重，也能检查实现中的计算轴和数值稳定性。',
        'flow': [
            {'label': '确定一组可比较分数', 'text': '先说明候选范围和归一化轴。教学组使用[4,2,0]，分数本身不要求位于0到1之间。'},
            {'label': '减去相同的最大值', 'text': '将[4,2,0]写成[0,-2,-4]，保持结果不变，减少指数计算溢出的风险。'},
            {'label': '指数后除以总和', 'text': '指数约为[1,0.1353,0.0183]，各项除以总和后得到约[0.8668,0.1173,0.0159]。'},
        ],
        'key_points': ['有限实数输入的数学结果为正且总和为1。',
                       '所有分数同时加相同常数，权重保持不变。',
                       '归一化权重不能单独证明预测已经校准。'],
        'common_confusions': [
            {'claim': '“只知道一个位置的分数，就能算它的softmax权重。”', 'explanation': '分母包含同组所有候选的指数，需要知道其余分数及候选范围。'},
            {'claim': '“代码显示权重为0，说明数学上该指数恰好等于0。”', 'explanation': '有限精度和显示舍入可能让很小的权重呈现为0，需区分数学定义和计算表示。'},
        ],
        'questions': ['给所有分数加10后，权重为什么不变？',
                      '若新增一个候选，其他分数不变，原权重是否保持？', '当前实现用哪个轴计算总和？'],
        'boundary': '掩码、温度、精度和候选集合都可能影响实际计算。权重总和为1本身不证明它能解释因果贡献或预测可信度。',
    },
    'dot_product': {
        'title': '向量点积：逐项相乘，再把贡献相加',
        'why_it_matters': '点积经常出现在特征打分、线性层和注意力中。把它拆成逐维贡献，'
                         '可以检查维度是否对齐、哪一项改变了分数，以及长度尺度怎样影响结果。',
        'flow': [
            {'label': '对齐分量含义', 'text': '两组向量长度一致，同一位置的分量必须能对应。教学向量取q=[1,2]、k=[2,3]。'},
            {'label': '逐项计算贡献', 'text': '第一维贡献是1×2=2，第二维贡献是2×3=6。'},
            {'label': '相加并解释单位', 'text': '得到标量8。这个数的意义取决于输入表示、尺度和后续运算，不会自动成为概率。'},
        ],
        'key_points': ['点积把两个等长向量变成一个标量。', '交换两个实向量的顺序，点积值相同。',
                       '点积受方向和向量长度共同影响；与只看夹角的归一化相似度需要区分。'],
        'common_confusions': [
            {'claim': '“点积就是逐元素相乘后的向量。”', 'explanation': '逐元素乘法还保留每维结果；点积继续把这些乘积求和，得到一个标量。'},
            {'claim': '“点积越大，两个输入一定越接近。”', 'explanation': '增大向量长度也会增大点积。使用它比较相似性时，需要说明归一化、距离定义和任务。'},
        ],
        'questions': ['哪个分量对当前点积分数贡献最大？', '若q整体乘2，点积如何变化？',
                      '当前公式还会对点积进行缩放或归一化吗？'],
        'boundary': '这里讨论等长实向量。矩阵批量乘法需要额外核对形状、转置、广播和计算轴，复向量还涉及共轭约定。',
    },
    'probability': {
        'title': '概率与频率：先说清随机过程，再解释数字',
        'why_it_matters': '同一个数值只有放回具体随机机制中才有概率含义。阅读采样、'
                         '模型输出或实验计数时，这能帮助区分理论概率、有限观察频率和未经校准的打分。',
        'flow': [
            {'label': '列出随机过程与结果', 'text': '教学袋中有3个红球、2个蓝球和1个白球，约定每个球等可能被抽到。'},
            {'label': '确定关心的事件', 'text': '事件“抽到红球”包含3个有利结果，单次概率为3/6=0.5。'},
            {'label': '说明重复规则', 'text': '每次放回会保持袋中比例；不放回时后续概率会随已抽结果改变。'},
            {'label': '比较理论与观察', 'text': '12次有放回抽取不保证恰好出现6次红球，观察频率可能高于或低于0.5。'},
        ],
        'key_points': ['概率描述给定机制下的事件，频率来自实际计数。',
                       '互斥且穷尽的全部结果，其概率总和为1。', '事件是否独立需要按机制判断，不能只靠事件名称。'],
        'common_confusions': [
            {'claim': '“概率0.5意味着每两次必定发生一次。”', 'explanation': '概率描述随机过程中的可能性，有限次数可以出现连续相同结果。'},
            {'claim': '“处于0到1之间的模型分数都是真实概率。”', 'explanation': '数值范围只是必要形式之一，其定义、归一化和校准仍需检查。'},
        ],
        'questions': ['当前事件的所有可能结果是什么？', '是否放回、是否独立会改变哪一步计算？',
                      '文中的数字来自理论定义、样本计数还是模型打分？'],
        'boundary': '等可能计数依赖每个基本结果等可能这一前提。连续变量不能直接用有限球数比例代替，预测概率还需检查校准与数据分布。',
    },
    'research_design': {
        'title': '研究设计：把比较因素、测量和条件连起来',
        'why_it_matters': '读懂结论需要知道研究实际比较了什么。把因素、结果和其他条件列开，'
                         '可以判断观察到的差异还可能由哪些因素解释，也能为后续实验或文献比较保留一致口径。',
        'flow': [
            {'label': '写出比较因素与测量', 'text': '教学问题比较反复阅读和主动回忆，结果可定义为随后回忆出的项目数。'},
            {'label': '对齐关键条件', 'text': '分别列出材料、学习时长、测试间隔和评分办法，先找各组哪些相同、哪些不同。'},
            {'label': '核对分组方式', 'text': '随机分配讨论样本内如何进入处理组；自主选择可能使原有动机或基础与组别同时变化。'},
            {'label': '限定结论解释', 'text': '若学习时长和测试间隔同时不同，不能仅把组间差异归因于学习方式。先说明设计能够支持哪一种比较。'},
        ],
        'key_points': ['研究问题、干预或比较因素、测量指标应当能彼此对应。',
                       '即时表现和延迟表现可能回答不同的问题。', '随机分配和随机抽样分别处理分组与代表性问题。'],
        'common_confusions': [
            {'claim': '“只要两组平均值不同，就证明干预有效。”', 'explanation': '还要检查组间条件、分配、测量误差和统计不确定性，观察差异本身不足以确定原因。'},
            {'claim': '“随机分配后，就能代表所有人群。”', 'explanation': '随机分配发生在已有样本内；能推广到谁，仍取决于招募、样本和研究环境。'},
        ],
        'questions': ['该研究改变了什么，记录了什么？', '组间有哪些条件同时变化？',
                      '延迟测试与即时测试是否支持相同的结论？'],
        'boundary': '有对照组不等于所有条件都受控。结论解释还依赖执行过程、失访、样本规模、测量效度及不确定性；观察性设计需要另外检查混杂。',
    },
    'sampling': {
        'title': '样本与总体：看清观察了谁、想解释谁',
        'why_it_matters': '样本比例计算很简单，推广范围却取决于样本怎样进入研究。'
                         '将招募渠道、实际观察对象和目标总体分开，可以避免把某个群体的结果直接套给所有人。',
        'flow': [
            {'label': '界定目标总体', 'text': '先说明希望讨论的人群或对象范围，再看实际能联系到的抽样框。'},
            {'label': '记录怎样进入样本', 'text': '随机抽取、便利招募和志愿报名会带来不同的选择机制，还应记录未回应与失访。'},
            {'label': '计算已观察样本的量', 'text': '教学样本为100人，其中30人支持方案，样本比例为30/100=30%。'},
            {'label': '核对推广条件', 'text': '如果目标总体有1000人，上述计数并未告诉我们其余900人的选择；需要结合抽样与不确定性再推断。'},
        ],
        'key_points': ['总体、抽样框、进入研究的样本和最终分析样本可能不同。',
                       '样本量与抽样方式共同影响解释，数量大不会自动消除选择偏差。',
                       '样本统计量是已观察数据的描述，总体参数通常需要额外推断。'],
        'common_confusions': [
            {'claim': '“只要调查人数足够多，样本就一定有代表性。”', 'explanation': '同一便利渠道中的大样本仍可能系统性漏掉某些群体。'},
            {'claim': '“样本支持率30%，说明总体支持率就是30%。”', 'explanation': '30%是当前样本的描述，推断总体需要抽样条件与不确定性信息。'},
        ],
        'questions': ['实际观察对象从哪里招募？', '谁可能没有进入或没有完成研究？',
                      '结论希望推广到哪些人，样本覆盖了他们吗？'],
        'boundary': '本例讨论统计抽样与推广，不是神经网络的随机动作采样。随机分配不保证样本有代表性，便利样本的比例也不能直接当作总体参数。',
    },
}


def _matches(topic, text):
    if not re.search(PATTERNS[topic], text, re.I):
        return False
    if topic == 'sampling' and re.search(r'gaussian|normal distribution|高斯|正态|策略|动作|policy|action', text, re.I):
        return bool(re.search(r'总体|研究对象|受试者|志愿|\bpopulation\b|\bparticipants\b', text, re.I))
    return True


def _available(node):
    return not (node.get('hidden') or node.get('source_missing')
            or node.get('quality_status') in {'withdrawn', 'rejected', 'disputed'}
            or node.get('metadata', {}).get('source_withdrawn'))


def _topic(node):
    if node.get('kind') not in KINDS or node.get('metadata', {}).get('structural') or not _available(node):
        return None
    label = node.get('label', '')
    for topic in PATTERNS:
        if _matches(topic, label):
            return topic
    summary = node.get('summary', '')
    latex = str(node.get('metadata', {}).get('latex', ''))
    if re.search(r'QK\s*(?:\^|\\top)|\\sqrt\s*\{?d_?k', latex) and 'softmax' in latex:
        return 'scaled_attention'
    text = summary + ' ' + latex
    for topic in PATTERNS:
        # A contrasting mechanism mentioned in context is not the node's topic.
        if topic in ATTENTION_GUIDES:
            continue
        if topic in {'research_design', 'sampling'} and node.get('kind') not in {'method', 'experiment', 'finding', 'hypothesis'}:
            continue
        if _matches(topic, text):
            return topic
    return None


def get_guide(node):
    """Return a fresh, versioned teaching guide, or None for an unrelated node."""
    if node.get('kind') == 'paper' and _available(node):
        return {**get_paper_guide(node), 'version': VERSION, 'origin': 'authored_teaching'}
    topic = _topic(node)
    if topic is None:
        return None
    if topic in ATTENTION_GUIDES:
        value = deepcopy(ATTENTION_GUIDES[topic])
    elif topic == 'self_attention':
        value = deepcopy(SELF_ATTENTION)
    else:
        foundation = FOUNDATIONS[topic]
        value = deepcopy(DETAILS[topic])
        value.update({
            'topic': topic,
            'overview': foundation['sections']['overview'],
            'example': {'title': '自编教学例',
                        'body': foundation['sections']['definition'] + '\n\n' + foundation['sections']['derivation']},
            'demo_ids': [topic],
            'references': [{'title': foundation['label'] + ' · 参考资料', 'url': foundation['url']}],
        })
    return {**value, 'version': VERSION, 'origin': 'authored_teaching'}
