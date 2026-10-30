"""Original, offline teaching fixtures for the canonical knowledge workbench.

All writes use the supplied connection/directory. No account-global connection,
network, parser model, or language model is used. Existing records are never reset.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path

from app.db import projects
from app.knowledge import comparison, experience, extraction, learning, practice, store
from app.knowledge.learning_depth import coverage
from app.models.research import ResearchProjectPatch

VERSION = 3
NOTICE = "原创合成教学示例，仅用于软件流程演示；不是论文实验、模型生成结果或科研性能证据。"


def _align_project_context(conn, pid):
    """Upgrade only untouched fixture defaults; append a version, keep snapshots."""
    current = projects.get_project(conn, pid)
    if (current.title, current.research_question, current.constraints.objective) != (
            "[合成验收] 图像异常检测首轮方案", "如何验证工作台能区分同一方法的两个合成实验设置？",
            "仅验证浏览器工作流、版本冻结和依据追踪，不验证算法效果"):
        return
    constraints = current.constraints.model_copy(update={"version": current.constraints.version + 1,
        "objective": "从图谱追溯定义与证据，运行标量教学例子，理解残差边界与导数，并保留真实任务效果的未知项。",
        "allowed_datasets": [], "required_metrics": [],
        "notes": [NOTICE, "历史 SyntheticProbe 方案与快照仅用于旧工作流追溯，与当前教学图谱分别理解。"]})
    projects.update_project(conn, pid, ResearchProjectPatch(expected_version=current.version,
        title="[原创演示] 梯度与有界残差的图谱互动学习",
        research_question="如何沿知识图谱理解链式法则，并通过同条件计算比较线性残差与有界残差？",
        domain="custom", custom_domain="知识图谱互动学习", stage="framing", constraints=constraints))

LESSONS = {
    "foundations": {
        "title": "软件流程演示 · 梯度、链式法则与高斯分布",
        "sections": [
            ("notice", "示例边界", NOTICE),
            ("gradient", "梯度与局部变化", "对标量函数 f(x)，导数描述输入附近的局部变化率。例如 f(x)=x² 时，f′(x)=2x，在 x=2 处为 4。数值差分 (f(x+h)-f(x-h))/(2h) 可检查实现，但浮点误差与步长有关。"),
            ("chain", "链式法则", "若 y=g(u)，u=f(x)，则 dy/dx=(dy/du)(du/dx)。在 y=tanh(2x) 中，局部导数为 1-tanh²(2x)，内层导数为 2，所以 dy/dx=2(1-tanh²(2x))。本示例中链式法则是理解有界残差导数的前置知识。"),
            ("gaussian", "高斯分布的均值与采样", "标量样本可写作 a=μ+σε，其中 ε 服从标准正态分布、σ>0。μ 决定分布中心，σ 决定离散程度；改变 μ 与固定随机种子后的样本变化可以分开观察。有限次样本均值不必等于 μ，这不表示代码错误。本示例不训练策略。"),
            ("limits", "共同边界", "后续比较只针对明确写出的标量函数。线性残差与有界残差都需要理解局部导数；没有真实训练、数据集或硬件计时，因此不能比较任务成功率、收敛速度或推理成本。"),
        ],
    },
    "linear": {
        "title": "软件流程演示 · 方案 A 线性残差",
        "sections": [
            ("notice", "示例边界", NOTICE),
            ("method", "方案 A：线性残差", "定义 y_A(x)=x+αx，标量输入 x、固定 α=0.5。残差 r_A=αx 随 |x| 无界增长；dy_A/dx=1+α=1.5。局部导数是理解该方法的前置知识。该函数是原创教学方案，不是已发表算法。"),
            ("formula", "线性残差公式", "$$y_A=x+\\alpha x,\\qquad \\frac{dy_A}{dx}=1+\\alpha$$"),
            ("example", "可复算例子", "当 α=0.5、x=2 时，残差为 1，输出为 3，导数为 1.5。x 从 2 增至 4 时，残差从 1 增至 2。可以直接用标准库代码计算并核对。"),
            ("limit", "未知与限制", "方案 A 没有残差幅值上界，但不能据此断言它在真实任务上更差。本文没有训练数据、对照实验、测量误差或硬件计时；性能与收敛结论均未知。"),
        ],
    },
    "bounded": {
        "title": "软件流程演示 · 方案 B 有界残差",
        "sections": [
            ("notice", "示例边界", NOTICE),
            ("method", "方案 B：有界残差", "定义 y_B(x)=x+αtanh(x)，固定 α=0.5。残差 r_B=αtanh(x)，所以 |r_B|<|α|。由链式法则得 dy_B/dx=1+α(1-tanh²(x))。链式法则与局部导数是理解本方法的前置知识。残差有界不代表总输出有界，更不代表实际系统安全。"),
            ("formula", "有界残差公式", "$$y_B=x+\\alpha\\tanh(x),\\qquad \\frac{dy_B}{dx}=1+\\alpha(1-\\tanh^2(x))$$"),
            ("example", "可复算例子", "当 α=0.5、x=2 时，tanh(2)≈0.9640，残差≈0.4820，输出≈2.4820，导数≈1.0353。与方案 A 使用同一 x 和 α，只能比较本标量例子的输出、局部导数与残差幅值。"),
            ("figure", "图 1：两种残差随输入变化", "图 1 是按上述定义实际计算的原创教学图。绿色曲线表示 0.5 tanh(x)，灰色直线表示 0.5x；横轴 x 取 [-4,4]。曲线边界只对残差成立，不是任务成功率或安全性证据。"),
            ("limit", "未知与限制", "方案 B 限制残差的幅值；在饱和区域，残差分支的导数趋近 0。它可能改变优化行为，但本文没有真实训练、硬件计时或任务评测，性能、收敛与成本均未知。"),
        ],
    },
}

PRACTICE_CODE = '''# 原创合成教学示例：不是论文复现，不自动判定掌握。
import json
import math
alpha = float(inputs.get("alpha", 0.5))
if not math.isfinite(alpha) or abs(alpha) > 10:
    raise ValueError("本演示要求 alpha 为 [-10,10] 内有限数")
xs = [i / 10 for i in range(-40, 41)]
linear = [[x, alpha*x] for x in xs]
bounded = [[x, alpha*math.tanh(x)] for x in xs]
print("PAPERSTRIDE_VISUAL:" + json.dumps({"type":"line", "title":"实际计算：残差幅值", "x_label":"x", "y_label":"residual", "series":[{"name":"A: alpha*x", "points":linear},{"name":"B: alpha*tanh(x)", "points":bounded}]}))
rows = []
for x in [-2.0, 0.0, 2.0]:
    analytic = 1 + alpha*(1-math.tanh(x)**2)
    h = 0.00001
    candidate = lambda t: t + alpha*math.tanh(t)
    numeric = (candidate(x+h)-candidate(x-h))/(2*h)
    rows.append([x, round(x+alpha*x,6), round(candidate(x),6), round(analytic,6), round(numeric,6)])
    assert abs(analytic-numeric) < 0.00001, "检查链式法则实现与数值差分"
print("PAPERSTRIDE_VISUAL:" + json.dumps({"type":"table", "title":"同条件计算与导数核对", "columns":["x","y_A","y_B","解析导数 B","数值导数 B"], "rows":rows}))
print("计算完成。检查 alpha=0、负值和较大值；残差有界不等于总输出有界。")
'''

GAUSSIAN_CODE = '''# 原创合成教学示例：固定种子只用于复算，不是统计性能评测。
import json
import math
import random
mu = float(inputs.get("mu", 0.0))
sigma = float(inputs.get("sigma", 1.0))
if not (math.isfinite(mu) and math.isfinite(sigma) and abs(mu) <= 10 and 0 < sigma <= 10):
    raise ValueError("要求 |mu|<=10 且 0<sigma<=10")
rng = random.Random(42)
points = [[i, mu + sigma*rng.gauss(0,1)] for i in range(60)]
print("PAPERSTRIDE_VISUAL:" + json.dumps({"type":"scatter", "title":"实际计算：高斯采样", "x_label":"sample index", "y_label":"sample", "series":[{"name":"samples", "points":points}]}))
mean = sum(p[1] for p in points)/len(points)
print("PAPERSTRIDE_VISUAL:" + json.dumps({"type":"bar", "title":"分布中心与有限样本均值", "series":[{"name":"0=mu; 1=sample mean", "points":[[0,mu],[1,mean]]}]}))
print(f"mu={mu}, sigma={sigma}, sample mean={mean:.6f}; 有限样本均值不必等于 mu")
'''


def _chart_image():
    """Rasterize our own computed curves, with no asset/model downloads."""
    import fitz
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=300)
        page.draw_rect(page.rect, fill=(0.98, 0.98, 0.96), color=None)
        page.insert_text((24, 24), "Original teaching example: residuals, alpha=0.5", fontsize=12)
        page.draw_line((44, 150), (560, 150), color=(0.5, 0.5, 0.5))
        page.draw_line((302, 48), (302, 254), color=(0.5, 0.5, 0.5))
        for fn, color in [(lambda x: 0.5*x, (0.5, 0.5, 0.5)), (lambda x: 0.5*math.tanh(x), (0.1, 0.4, 0.3))]:
            page.draw_polyline([(302+x*64, 150-fn(x)*48) for x in [i/20 for i in range(-80, 81)]], color=color, width=2)
        page.insert_text((24, 280), "green: 0.5*tanh(x)   gray: 0.5*x   x in [-4,4]", fontsize=11)
        return base64.b64encode(page.get_pixmap().tobytes("png")).decode()


def _source(conn, directory, final_directory, pid, key, lesson):
    sid = store.identity("portable-knowledge-demo", pid, key)
    old = conn.execute("SELECT data FROM kw_sources WHERE id=?", (sid,)).fetchone()
    if old:
        return json.loads(old[0])
    lines = ["# " + lesson["title"], ""]
    blocks = []
    for section_key, heading, body in lesson["sections"]:
        lines.extend(["## " + heading, "", body, ""])
        blocks.append({"kind": "formula" if section_key == "formula" else "figure" if section_key == "figure" else "text",
            "heading": heading, "text": body, "metadata": {"demo_key": section_key,
                "start_line": len(lines)-1, "end_line": len(lines)-1}})
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    aid = store.identity(digest, ".md")
    relative = Path("knowledge") / "assets" / (aid + ".md")
    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("Existing demo source file changed; it was not replaced")
    path.write_bytes(raw)
    value = {"id": sid, "project_id": pid, "asset_id": aid, "version": "sha256:"+digest,
        "title": lesson["title"], "filename": f"{key}-teaching-demo.md", "kind": "report", "media_type": "text/markdown",
        "paper_uid": None, "url": None, "removed": False, "created_at": store.now(), "demo": True,
        "parser": "original-teaching-fixture", "quality": {"status": "synthetic_demo"}}
    conn.execute("INSERT OR IGNORE INTO kw_assets VALUES(?,?,?,?,?,?)", (aid, digest, str(final_directory / relative), value["filename"], value["media_type"], store.now()))
    for block in blocks:
        if block["kind"] == "figure":
            block["metadata"]["image_base64"] = _chart_image()
        if block["kind"] == "formula":
            block["metadata"]["latex"] = block["text"].strip("$")
    store.put_parse(conn, aid, {"title": value["title"], "blocks": blocks, "parser": value["parser"], "warnings": [NOTICE], "quality": value["quality"]})
    conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (sid, pid, aid, 0, store.encode(value)))
    return value


def seed(conn, directory: Path, pid: str, *, final_directory: Path | None = None):
    """Add a complete demo once; preserve nodes, edits, progress and old snapshots."""
    directory = Path(directory).resolve()
    final_directory = Path(final_directory or directory).resolve()
    _align_project_context(conn, pid)
    store.init(conn)
    # practice.init uses executescript; initialize it before adding any records.
    practice.init(conn)
    experience.init(conn)
    result_id = "portable-knowledge-demo-v3:" + pid
    previous = conn.execute("SELECT data FROM kw_migrations WHERE name=?", (result_id,)).fetchone()
    if previous:
        return json.loads(previous[0])
    nodes, sources, evidence_by_key = {}, {}, {}
    for key, lesson in LESSONS.items():
        src = sources[key] = _source(conn, directory, final_directory, pid, key, lesson)
        blocks = {b["metadata"]["demo_key"]: b for b in store.source_blocks(conn, src["asset_id"])}
        root = extraction.node(src, "root", "report", src["title"], NOTICE,
            [store.add_evidence(conn, pid, src, blocks["notice"])], metadata={"demo": True})
        if not conn.execute("SELECT 1 FROM kw_nodes WHERE id=?", (root["id"],)).fetchone():
            store.put_record(conn, "kw_nodes", root)
        for section_key, heading, body in lesson["sections"]:
            if section_key == "notice":
                continue
            ev = store.add_evidence(conn, pid, src, blocks[section_key])
            evidence_by_key[key+":"+section_key] = ev
            kind = "method" if section_key == "method" else "formula" if section_key == "formula" else "resource" if section_key == "figure" else "limitation" if section_key in {"limit", "limits"} else "concept"
            metadata = {"semantic": True, "demo": True, "heading": heading, "quality_notice": NOTICE}
            if kind == "formula":
                metadata["latex"] = body.strip("$")
            item = extraction.node(src, section_key, kind, heading, body, [ev], parent_id=root["id"], metadata=metadata)
            if not conn.execute("SELECT 1 FROM kw_nodes WHERE id=?", (item["id"],)).fetchone():
                store.put_record(conn, "kw_nodes", item)
            nodes[key+":"+section_key] = store.record(conn, "kw_nodes", pid, item["id"])
            relation = extraction.edge(src, root["id"], item["id"], "CONTAINS", "包含", "该内容位于原创教学资料的对应章节。", [ev])
            if not conn.execute("SELECT 1 FROM kw_edges WHERE id=?", (relation["id"],)).fetchone():
                store.put_record(conn, "kw_edges", relation)
    relations = [("foundations:gradient", "foundations:chain", "PREREQUISITE_OF", "先理解局部变化", "链式法则组合各层局部导数。"),
        ("foundations:gradient", "linear:method", "PREREQUISITE_OF", "共同前置", "原文要求理解局部导数。"),
        ("foundations:gradient", "bounded:method", "PREREQUISITE_OF", "共同前置", "原文要求理解局部导数。"),
        ("foundations:chain", "bounded:method", "PREREQUISITE_OF", "前置知识", "原文使用链式法则计算非线性残差的导数。"),
        ("linear:method", "linear:formula", "DEFINED_BY", "公式定义", "同一教学方案的定义式。"),
        ("bounded:method", "bounded:formula", "DEFINED_BY", "公式定义", "同一教学方案的定义式。"),
        ("bounded:method", "bounded:figure", "ILLUSTRATED_BY", "图示", "图中按定义计算残差，不能推断真实任务性能。")]
    for a, b, kind, label, explanation in relations:
        src = sources[b.split(":")[0]]
        relation = extraction.edge(src, nodes[a]["id"], nodes[b]["id"], kind, label, explanation, nodes[b]["evidence_ids"])
        if not conn.execute("SELECT 1 FROM kw_edges WHERE id=?", (relation["id"],)).fetchone():
            store.put_record(conn, "kw_edges", relation)
    for key in ("foundations:gradient", "foundations:chain", "foundations:gaussian", "linear:method", "bounded:method"):
        _learning_and_practice(conn, pid, key, nodes[key])
    comparison_id = _comparison(conn, pid, sources, nodes)
    result = {"version": VERSION, "notice": NOTICE, "project_id": pid,
        "source_ids": {k: v["id"] for k, v in sources.items()}, "node_ids": {k: n["id"] for k, n in nodes.items()},
        "comparison_id": comparison_id, "model_calls": 0,
        "paths": {"graph": f"/research/{pid}?view=graph", "learning": f"/research/{pid}?view=learning&node={nodes['bounded:method']['id']}",
            "practice": f"/research/{pid}?view=practice&node={nodes['bounded:method']['id']}", "comparison": f"/research/{pid}?view=compare&comparison={comparison_id}"}}
    conn.execute("INSERT INTO kw_migrations VALUES(?,?,?)", (result_id, store.encode(result), store.now()))
    conn.commit()
    return result


def _learning_and_practice(conn, pid, key, node):
    nid = node["id"]
    lesson = learning.basic(conn, pid, nid)
    lesson["sections"]["overview"] = NOTICE + "\n\n" + node["summary"]
    lesson["sections"]["implementation"] = ("在练习中调整 mu 与 sigma 后重新运行，观察同一随机种子下的样本和均值。" if "gaussian" in key else
        "打开实际运行练习，将 alpha 从 0.5 改为 0，再改为 -0.5。程序计算两条残差曲线，并用中心差分核对有界残差的解析导数。运行结果只检验本例代码，不代表已经理解或完成论文复现。")
    lesson["sections"]["limitations"] = "本内容为人工编写的原创软件演示。参数范围、标量近似与浮点误差需要核对；没有真实论文实验或效果评测，不产生科研性能排名。学习状态请自行设置。"
    lesson.update(origin="user", status="basic", demo=True, user_edited_sections=list(lesson["sections"]))
    lesson["coverage"] = coverage(lesson["sections"], node, prerequisites=learning.prerequisites(conn, pid, nid))
    fp = learning.learning_fingerprint(conn, pid, nid)
    previous = conn.execute("SELECT fingerprint,data FROM kw_learning WHERE project_id=? AND node_id=? ORDER BY rowid DESC LIMIT 1", (pid, nid)).fetchone()
    if not previous:
        conn.execute("INSERT OR IGNORE INTO kw_learning VALUES(?,?,?,?)", (pid, nid, fp, store.encode(lesson)))
    elif json.loads(previous[1]).get("demo") and json.loads(previous[1]).get("revision", 1) == 1:
        # The sole change is correcting the original fixture's unrelated question.
        # Keep saved content exactly; user-edited revisions retain their old key.
        conn.execute("UPDATE kw_learning SET fingerprint=? WHERE project_id=? AND node_id=? AND fingerprint=?", (fp, pid, nid, previous[0]))
    fp, current, src, evidence, goal, difficulty, adjustment, _, _ = practice.fingerprint(conn, pid, nid, "", "foundation")
    code = GAUSSIAN_CODE if "gaussian" in key else PRACTICE_CODE
    value = {"id": store.identity("demo-practice", pid, nid), "project_id": pid, "node_id": nid, "node_label": node["label"],
        "node_version": current["version"], "source_version": src["version"], "fingerprint": fp, "goal": goal,
        "difficulty": difficulty, "adjustment": adjustment, "status": "ready", "origin": "user_teaching_demo", "revision": 1,
        "previous_practice_id": None, "previous_context_hash": None, "created_at": store.now(), "cached": False,
        "evidence": evidence, "errors": [], "usage": {}, "demo": True,
        "title": node["label"] + " · 原创可运行演示", "prompt": NOTICE + "\n改变输入参数，先写下预期，再运行并解释结果。",
        "starter_code": code, "draft_code": code, "test_code": "", "reference_code": code,
        "input_json": json.dumps({"mu": 0, "sigma": 1} if "gaussian" in key else {"alpha": 0.5}),
        "hints": ["一次只改一个参数，比较两次运行。", "保留未知项，代码通过不等于已经掌握。"],
        "expected_behavior": "输出实际计算的图表；修改参数后曲线或样本随之改变。", "learning_objectives": [goal],
        "simplifications": [NOTICE, "仅依赖 Python 标准库，不训练模型或执行第三方仓库。"]}
    conn.execute("INSERT OR IGNORE INTO kw_practice VALUES(?,?,?,?,?)", (value["id"], pid, nid, fp, store.encode(value)))


def _comparison(conn, pid, sources, nodes):
    source_ids = [sources[k]["id"] for k in ("linear", "bounded")]
    focus = [nodes[k+":method"]["id"] for k in ("linear", "bounded")]
    dimensions = ["定义与输入", "残差边界", "局部导数", "真实任务效果与成本"]
    entries = [
        ("y_A=x+αx，标量 x，默认 α=0.5。", "y_B=x+αtanh(x)，与 A 使用同一 x 与 α。", "method"),
        ("α 非零时残差 αx 无界增长。", "残差绝对值小于 |α|；总输出仍可无界。", "method"),
        ("dy_A/dx=1+α。", "dy_B/dx=1+α(1-tanh²(x))。", "formula"),
        ("未知：无真实训练、任务评测或硬件计时。", "未知：无真实训练、任务评测或硬件计时。", "limit"),
    ]
    rows = []
    ids = []
    for dimension, (a, b, section) in zip(dimensions, entries, strict=True):
        values = []
        for key, text in [("linear", a), ("bounded", b)]:
            item = nodes[key+":"+section]
            ids += item["evidence_ids"]
            values.append({"source_id": sources[key]["id"], "text": text, "node_ids": [item["id"]], "evidence_ids": item["evidence_ids"], "origin": "user"})
        rows.append({"dimension": dimension, "values": values, "compatibility": "原创标量示例的定性比较，不能推出真实任务排名。"})
    fp = comparison.fingerprint(conn, pid, source_ids, focus, dimensions)
    value = {"id": store.identity("demo-comparison", pid), "source_ids": source_ids, "focus_node_ids": focus,
        "focus_nodes": [{"id": nodes[k+":method"]["id"], "source_id": sources[k]["id"], "label": nodes[k+":method"]["label"]} for k in ("linear", "bounded")],
        "title": "原创教学比较 · 线性残差与有界残差", "dimensions": dimensions, "revision": 1, "rows": rows,
        "evidence": store.evidence(conn, pid, ids), "status": "basic", "cached": True, "stale": False, "usage": {}, "errors": [],
        "fingerprint": fp, "created_at": store.now(), "demo": True, "origin": "user"}
    conn.execute("INSERT OR IGNORE INTO kw_comparisons VALUES(?,?,?,?)", (value["id"], pid, fp, store.encode(value)))
    old = conn.execute("SELECT data FROM kw_comparisons WHERE id=?", (value["id"],)).fetchone()
    saved = json.loads(old[0])
    if saved.get("demo") and saved.get("revision", 1) == 1 and saved.get("fingerprint") != fp:
        saved["fingerprint"] = fp
        conn.execute("UPDATE kw_comparisons SET fingerprint=?,data=? WHERE id=?", (fp, store.encode(saved), value["id"]))
    return value["id"]
