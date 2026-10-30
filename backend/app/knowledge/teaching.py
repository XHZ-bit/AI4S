"""Reusable teaching references, independent of paper names or research claims."""

GATING = r'''教学数学对照（只有原文采用相同参数化时才可对应当前方法）：
固定独立标量 m,z，c>0，s=σ(z)∈(0,1)。定义两种常见门控残差：
δ_in=c tanh(2sm/c)，δ_out=cs tanh(2m/c)。令u=2sm/c，v=2m/c。
链式法则给出：
∂δ_in/∂z=2ms(1-s)[1-tanh²(u)]，∂δ_out/∂z=cs(1-s)tanh(v)。
∂δ_in/∂m=2s[1-tanh²(u)]，∂δ_out/∂m=2s[1-tanh²(v)]。
有限m,z下 |δ_in|<c，|δ_out|<cs<c；在m=z=0时两种参数化对m的偏导为1，对z的偏导为0。
外置门控路径不额外乘消息tanh的导数；sigmoid仍可能饱和，消息路径也可能趋零。这是局部偏导，不是总训练梯度，也不证明训练收益或消除梯度冲突。
若残差加到高斯策略均值，受此界约束的只有新增均值修正，不是整个均值、随机采样动作或机器人安全。高斯采样在标准差非零时仍有无界支持。
教学代码或交互示例不等于实际源码。未提供实现时不能声称代码硬编码、激活函数、文件或行号已核验。'''


def references(demos):
    return {'gating': GATING} if 'gating' in demos else {}
