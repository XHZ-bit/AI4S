"""Versioned, offline teaching content. Source inspection is not model reproduction."""

import json
from pathlib import Path

CASE_ID = "diffusion-policy-intro"
VERSION = "1.0.0"
SOURCES = json.loads(
    Path(__file__).with_name("sources.json").read_text(encoding="utf-8")
)
STEP_IDS = ["orient", "interface", "config", "inspect", "reflect"]
CHECK_IDS = [
    "python_version",
    "policy_interface",
    "observation_shape",
    "action_shape",
    "observation_dimension",
    "action_dimension",
    "checkpoint_option",
    "evaluation_log",
]
LIMITATION = "当前只检查固定版本源码与接口，不加载权重、不训练或评估策略；通过不代表复现了论文结果。"
QUESTIONS = [
    {
        "id": "interface",
        "step": "interface",
        "question": "action: B,Ta,Da 表示什么？",
        "options": [
            "批次、动作步数、动作维度",
            "批次、训练轮数、数据集大小",
            "论文报告的成功率",
        ],
        "correct": 0,
        "explanation": "接口注释区分观测与动作序列；输出形状不是效果指标。",
        "source": 0,
    },
    {
        "id": "horizon",
        "step": "interface",
        "question": "To、Ta、T 必须相等吗？",
        "options": ["必须相等", "不必，分别对应观测、动作和预测窗口", "都表示批次大小"],
        "correct": 1,
        "explanation": "示意给出 To=3、Ta=4、T=6，三个窗口作用不同。",
        "source": 0,
    },
    {
        "id": "configuration",
        "step": "config",
        "question": "固定版本的 pusht_lowdim 配置使用多少维观测与动作？",
        "options": ["图像像素与类别标签", "2 维观测、20 维动作", "20 维观测、2 维动作"],
        "correct": 2,
        "explanation": "配置写明 obs_dim: 20 与 action_dim: 2；不能推广到其他任务。",
        "source": 1,
    },
    {
        "id": "scope",
        "step": "reflect",
        "question": "源码检查通过后，可以得出哪项结论？",
        "options": [
            "论文实验已复现",
            "文件与指定版本一致，选定接口检查通过",
            "机器人成功率达到论文水平",
        ],
        "correct": 1,
        "explanation": "检查没有加载权重或运行环境，效果仍需固定设置下的真实评估。",
        "source": 2,
    },
]
MAPPINGS = [
    ("输入观测序列", 0, "obs: B,To,Do", "区分批次、观测步数和观测维度。"),
    ("输出动作序列", 0, "action: B,Ta,Da", "动作形状不等于成功率。"),
    ("三个时间窗口", 0, "To = 3", "示意中的三个窗口不必相等。"),
    ("归一化接口", 0, "def set_normalizer", "基类定义接口；具体机制仍需阅读实现。"),
    ("状态输入维度", 1, "obs_dim: 20", "此配置为 20 维观测。"),
    ("动作维度", 1, "action_dim: 2", "此配置为 2 维动作。"),
    (
        "加载检查点",
        2,
        "payload = torch.load",
        "真实评估需要检查点；源码检查不执行此代码。",
    ),
    (
        "评估结果文件",
        2,
        "out_path = os.path.join",
        "真实评估输出 eval_log.json；文件存在不自动证明实验可比。",
    ),
]


def catalog():
    mappings = []
    for title, index, needle, explanation in MAPPINGS:
        source = SOURCES["files"][index]
        start = next(
            i for i, line in enumerate(source["text"].splitlines(), 1) if needle in line
        )
        mappings.append(
            {
                "title": title,
                "source": index,
                "line": start,
                "url": source["url"] + f"#L{start}",
                "explanation": explanation,
            }
        )
    steps = [
        (
            "orient",
            "确定本次能完成什么",
            3,
            "说清源码检查与策略评估的区别。",
            "无需 GPU 或模型 API。阅读源码、运行只读检查、导入结果；完整评估另需实测环境。",
        ),
        (
            "interface",
            "读懂输入输出与时间窗口",
            8,
            "完成接口与时间窗口两道理解检查。",
            "找到观测输入和动作输出，理解 To、Ta、T；接口约定不能证明模型效果。",
        ),
        (
            "config",
            "核对任务配置",
            5,
            "定位维度和数据路径，回答配置问题。",
            "阅读固定版本 pusht_lowdim.yaml；避免把单个配置当作通用常数。",
        ),
        (
            "inspect",
            "运行本机检查并导入结果",
            5,
            "导入本机 JSON，查看每项检查及限制。",
            "标准库工具只读取少量源码，不执行第三方代码、不需要 torch；支持离线源码包。",
        ),
        (
            "reflect",
            "解释结果与下一步",
            5,
            "完成范围判断题并导出报告。",
            "报告记录检查范围。真实评估仍需独立环境、可信检查点和实验条件。",
        ),
    ]
    troubles = [
        (
            "dependency",
            "Python 或依赖不可用",
            "源码检查仅需 Python 3.10+。真实模型使用独立环境，不修改全局 Anaconda。",
        ),
        (
            "version",
            "版本或散列不符",
            "重新下载固定源码包，不混用最新分支或手工修改文件。",
        ),
        (
            "path",
            "文件路径错误",
            "在工具所在目录运行，--source-dir 指向解压后的源码根目录。",
        ),
        (
            "resource",
            "缺少数据、权重或算力",
            "源码检查不需要这些资源。真实模型评估待实测，不下载未知来源检查点。",
        ),
        (
            "network",
            "下载失败或 TLS 中断",
            "保持本机代理运行，或使用离线源码包；不要关闭证书校验。",
        ),
        (
            "artifact",
            "产物缺失或检查失败",
            "查看 JSON 的 errors 和检查明细，修复后重新运行，使用新文件名保留历史。",
        ),
    ]
    return {
        "id": CASE_ID,
        "version": VERSION,
        "title": "Diffusion Policy：从源码理解到复现准备",
        "scope": "source_inspection",
        "status": "源码教学可用；策略评估待实测",
        "notice": LIMITATION,
        "repository": SOURCES["repository"],
        "commit": SOURCES["commit"],
        "sources": SOURCES["files"],
        "paper_url": "https://arxiv.org/abs/2303.04137",
        "paper_notice": "论文入口供对照阅读。当前要点定位依据是固定源码，尚未标记为人工核验的论文主张。",
        "mappings": mappings,
        "steps": [
            dict(zip(["id", "title", "minutes", "criterion", "body"], row))
            for row in steps
        ],
        "questions": [
            {k: v for k, v in q.items() if k not in ("correct", "explanation")}
            for q in QUESTIONS
        ],
        "troubleshooting": [
            dict(zip(["id", "title", "action"], row)) for row in troubles
        ],
    }
