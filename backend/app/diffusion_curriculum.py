"""Versioned, authored small experiments. These do not reproduce policy training."""
VERSION='dp-learning-v1'
PAPER='https://diffusion-policy.cs.columbia.edu/ '
SOURCE='https://github.com/real-stanford/diffusion_policy/blob/5ba07ac6661db573af695b419a7947ecb704690f/'

def lesson(i,title,summary,explanation,formula,starter,solution,tests,quiz,prerequisites,source):
    return dict(id=f'dp-{i}',title=title,summary=summary,minutes=15,connection='Diffusion Policy：'+summary,
        prerequisites=prerequisites,visual=f'dp-{i}',terms=[],version=VERSION,
        sources=[{'title':'Diffusion Policy 官方论文与项目','url':PAPER.strip()},{'title':'固定版本源码','url':SOURCE+source+{1:'#L10',2:'#L10',3:'#L227',4:'#L248',5:'#L51'}[i]}],
        steps=[dict(question=title,explanation=explanation,example=formula)],quiz=quiz,
        exercise=dict(id=f'dp-exercise-{i}',kind=['短函数','调试','代码填空','模块组合','代码分析'][i-1],title=title+' · 实践',
          prompt=summary+'。先预测输出，补齐代码；再修改边界输入观察变化。',starter=starter,hint='对照本节公式与输入输出；先实现一个样本，再处理整个序列。',solution=solution,tests=tests,test_count=tests.count('assert ')))

def q(question,options,answer,explanation):return dict(question=question,options=options,answer=answer,explanation=explanation)

LESSONS=[
lesson(1,'条件概率与多种可能动作','同一个观测下，动作可以有多个合理方向',
 r'策略描述给定观测 o 后动作 a 的条件分布 $p(a\mid o)$。例如绕过障碍物，向左与向右都可能有效。直接取动作均值可能走向障碍物。条件概率的分母是当前观测对应的总次数；观测改变，分布也可能改变。频率只是用于理解的有限样本估计，不能当作机器人真实策略。',
 r'$P(a=\mathrm{left}\mid o)=n_{\mathrm{left},o}/n_o$。观测 A 下左转 3 次、右转 1 次，左转频率为 0.75。',
 'def conditional(counts):\n    # 返回归一化概率；空列表或总数为0时返回空列表\n    ...\n\nprint(conditional([3,1]))',
 'def conditional(counts):\n    if any(x<0 for x in counts):\n        raise ValueError("negative count")\n    total=sum(counts)\n    return [x/total for x in counts] if total else []',
 'assert conditional([3,1])==[0.75,0.25]\nassert conditional([])==[]\nassert conditional([0,0])==[]\nassert conditional([0,2])==[0,1]',
 [q('左右绕行都安全，但中间有障碍，为什么平均动作可能失败？',['均值可能落在两种有效模式之间','均值一定是最优动作','样本越多均值越安全'],0,'多峰分布的均值可能不是一个有效动作。'),q('变式：新观测下左转2次、右转6次，左转频率是多少？',['0.75','0.25','0.5'],1,'条件变为新观测，使用该观测的总次数8作为分母。')],['probability','bayes'],'diffusion_policy/policy/base_lowdim_policy.py'),
lesson(2,'张量维度与时间窗口','正确区分批次、时间与特征轴',
 '观测通常组织成 $[B,T_o,D_o]$，预测动作是 $[B,T_a,D_a]$。B 是独立样本数，时间轴包含连续时刻，特征轴表示同一时刻的各维信息。滑动窗口结束位置是当前观测；未来动作不能混入历史输入。示例通过 Python 列表检查窗口边界，不代表模型已学到策略。',
 r'序列 [0,1,2,3,4]，当前索引2、历史长度3，对应窗口 [0,1,2]。',
 'def window(sequence, end, length):\n    # 历史不足或参数越界时抛出 ValueError\n    return sequence[end-length:end]\n\nprint(window([0,1,2,3,4],2,3))',
 'def window(sequence,end,length):\n    if length<1 or end<length-1 or end>=len(sequence):\n        raise ValueError("window out of range")\n    return sequence[end-length+1:end+1]',
 'assert window([0,1,2,3,4],2,3)==[0,1,2]\nassert window([0,1,2],1,1)==[1]\nassert window([0,1,2],2,2)==[1,2]\ntry:\n    window([1],0,2)\n    raise AssertionError("must reject insufficient history")\nexcept ValueError:\n    pass',
 [q('8个样本、3个观测时刻、每个时刻20维，形状是？',['[3,8,20]','[8,20,3]','[8,3,20]'],2,'批次、时间、特征分别占一轴。'),q('变式：当前索引4，历史长度2，应该取哪两个索引？',['4,5','3,4','2,3'],1,'包含当前时刻，不能包含未来时刻5。')],['vectors'],'diffusion_policy/policy/base_lowdim_policy.py'),
lesson(3,'前向加噪与噪声强度','观察信号与噪声比例怎样改变样本',
 r'扩散模型的前向过程逐步破坏数据结构。常用表达为 $x_t=\sqrt{\bar\alpha_t}x_0+\sqrt{1-\bar\alpha_t}\epsilon$，其中标准高斯噪声 $\epsilon$ 的方差为1。$\bar\alpha_t$ 越接近1，原信号保留越多。这里固定一组噪声来比较参数，不能用单个样本推断总体方差。',
 r'$\bar\alpha_t=1$ 时保留原值；$\bar\alpha_t=0$ 时完全成为指定的噪声。',
 'import math\ndef add_noise(x, noise, alpha):\n    ...\n\nprint(add_noise(2.0, -1.0, 0.5))',
 'import math\ndef add_noise(x,noise,alpha):\n    if not 0<=alpha<=1:\n        raise ValueError("alpha must be between 0 and 1")\n    return math.sqrt(alpha)*x+math.sqrt(1-alpha)*noise',
 'assert add_noise(2,-1,1)==2\nassert add_noise(2,-1,0)==-1\nassert abs(add_noise(2,-1,0.5)-2**-0.5)<1e-8\ntry:\n    add_noise(1,1,-0.1)\n    raise AssertionError("invalid alpha")\nexcept ValueError:\n    pass',
 [q('alpha接近1意味着什么？',['原信号权重更大','噪声权重更大','信号权重不变'],0,'系数是alpha的平方根。'),q('变式：x0=0、噪声=2、alpha=0.75，xt是多少？',['2','0','1'],2,'噪声系数sqrt(0.25)=0.5，所以结果为1。')],['dp-1'],'diffusion_policy/policy/diffusion_unet_lowdim_policy.py'),
lesson(4,'简化去噪目标与损失','用已知噪声检查预测误差',
 r'噪声预测网络学习在给定带噪动作、时间步与观测条件时估计噪声。平方误差目标可写为 $L=\frac1n\sum_i(\epsilon_i-\hat\epsilon_i)^2$。训练时加入的噪声已知，因此能够构造监督信号。损失下降不自动保证闭环控制成功；评估还需要任务环境。这里手工提供预测值，仅练习目标计算。',
 r'真实噪声 [1,-1]、预测 [0,0]，均方误差为1。',
 'def squared_errors(target, prediction):\n    ...\n\ndef mse(target, prediction):\n    ...\n\nprint(mse([1,-1],[0,0]))',
 'def squared_errors(target,prediction):\n    if len(target)!=len(prediction) or not target:\n        raise ValueError("nonempty equal lengths required")\n    return [(a-b)**2 for a,b in zip(target,prediction)]\n\ndef mse(target,prediction):\n    errors=squared_errors(target,prediction)\n    return sum(errors)/len(errors)',
 'assert mse([1,-1],[0,0])==1\nassert mse([2,4],[2,4])==0\nassert mse([1,3],[2,1])==2.5\ntry:\n    mse([1],[1,2])\n    raise AssertionError("shape mismatch")\nexcept ValueError:\n    pass',
 [q('训练时监督目标中的噪声来自哪里？',['从实验成功率猜测','由前向加噪过程采样并记录','必须由人工标注'],1,'加噪时噪声已知，可以用于监督预测网络。'),q('变式：两种方法在不同任务上MSE分别0.1和0.2，能断定前者控制更好吗？',['不能，需匹配任务与控制评估','能，任何损失都可以比较','能，数值较小必然更好'],0,'训练误差与任务成功不同，条件和指标含义必须匹配。')],['dp-3','gradients'],'diffusion_policy/policy/diffusion_unet_lowdim_policy.py'),
lesson(5,'动作序列执行与评估','区分预测序列、执行片段与正式评估',
 '滚动执行策略每次预测一段动作，执行其中的一小段，再根据新观测重新规划。执行太长可能忽略环境变化；太短可能增加推理负担。真实任务需要固定环境、初始状态分布、种子和评估次数。下面只模拟执行片段选择，并检查成功率统计，不运行机器人或训练模型。',
 r'$\hat p=\frac{\text{成功次数}}{\text{总评估次数}}$。8/10 与80/100的点估计相同，但不确定性不同。',
 'def execute_chunk(predicted, count):\n    ...\n\ndef success_rate(outcomes):\n    ...\n\nprint(execute_chunk([1,2,3,4],2))',
 'def execute_chunk(predicted,count):\n    if count<1 or count>len(predicted):\n        raise ValueError("invalid execution horizon")\n    return predicted[:count]\n\ndef success_rate(outcomes):\n    if not outcomes:\n        return None\n    return sum(bool(x) for x in outcomes)/len(outcomes)',
 'assert execute_chunk([1,2,3,4],2)==[1,2]\nassert execute_chunk([1],1)==[1]\nassert success_rate([True,False,True,True])==0.75\nassert success_rate([]) is None',
 [q('执行一小段动作后，下一次规划应基于什么？',['最早的观测永远不变','上一次预测的结果冒充观测','新的实际观测'],2,'重新观测才能让后续动作适应实际状态。'),q('变式：两个方法都成功80%，一个评估10次、另一个100次，可以视为完全相同证据吗？',['可以','不可以，样本量与评估条件不同','只看名称'],1,'点估计相同不表示不确定性和条件相同。')],['dp-2','dp-4'],'eval.py')]
