"""User-directed, local topic exploration. No model calls or invented findings."""

import re
from contextlib import closing
from urllib.parse import quote
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.db.sqlite import connect
from app.api.workbench import initialize, project_or_404

router = APIRouter(prefix="/api/workbench", tags=["topic-exploration"])

# Explicit lexical hints help Chinese queries find English paper metadata.
# These are search clues, not inferred research interests or relevance claims.
LANGUAGE_HINTS = {
    "机器人": ["robot"],
    "扩散": ["diffusion"],
    "协作": ["collaboration", "human-robot"],
    "人机": ["human", "interaction"],
    "视觉": ["vision", "visual"],
    "语言模型": ["language model"],
    "医学": ["medical", "clinical"],
    "生物": ["biolog"],
    "教育": ["education", "classroom"],
    "数字人文": ["digital humanities"],
    "社会": ["social"],
    "时间序列": ["time series"],
    "异常检测": ["anomaly detection"],
}


class ExplorationBrief(BaseModel):
    interests: str = Field(default="", max_length=1500)
    background: str = Field(default="", max_length=1500)
    resources: str = Field(default="", max_length=1500)
    project_id: str | None = Field(default=None, max_length=100)


@router.post("/topic-exploration")
def explore_topics(req: ExplorationBrief):
    with closing(connect()) as c:
        initialize(c)
        if req.project_id:
            project_or_404(c, req.project_id)
        rows = c.execute(
            "SELECT uid,title,abstract,year FROM papers ORDER BY created_at DESC,uid LIMIT 1000"
        ).fetchall()
        tokens = [
            x.casefold()
            for x in re.findall(
                r"[A-Za-z0-9][A-Za-z0-9-]{1,}|[\u4e00-\u9fff]{2,}", req.interests
            )
        ]
        for term, hints in LANGUAGE_HINTS.items():
            if term in req.interests:
                tokens.extend(hints)
        tokens = list(dict.fromkeys(tokens))
        ranked = []
        for row in rows:
            text = (row["title"] + " " + (row["abstract"] or "")).casefold()
            hits = [t for t in tokens if t in text]
            if tokens and not hits:
                continue
            ranked.append((len(hits), row, hits))
        ranked.sort(key=lambda x: x[0], reverse=True)
        papers = [
            {
                "uid": r["uid"],
                "title": r["title"],
                "year": r["year"],
                "reason": "题名或摘要包含：" + ", ".join(hits)
                if hits
                else "来自你已有的资料，尚未判断是否符合兴趣",
                "url": "/papers/" + quote(r["uid"], safe="") + "?tab=reading",
            }
            for _, r, hits in ranked[:6]
        ]
    topic = req.interests.strip() or (
        "“" + papers[0]["title"][:120] + "”涉及的研究主题"
        if papers
        else "你感兴趣的一个现象或应用场景"
    )
    sources = [p["uid"] for p in papers]
    directions = [
        {
            "id": "landscape",
            "title": "先看清这个方向在研究什么",
            "question": f"围绕{topic}，现有工作分别解决什么问题，哪些限制反复出现？",
            "why": "适合刚接触领域、还不清楚问题边界时。",
            "first_step": "对两至三篇资料分别记录：研究对象、问题、方法、局限。先找共性，再选关注点。",
            "needed": "综述或入门资料；不会要求你现在填写实验指标。",
            "paper_uids": sources,
        },
        {
            "id": "scenario",
            "title": "从具体场景里找问题",
            "question": f"在{topic}的一个实际使用场景中，现有方法在哪些条件下不够好用？",
            "why": "适合有应用兴趣，但还没有可研究问题时。",
            "first_step": "选一个你熟悉的场景，描述期望与实际表现的差别；在原文中查找是否已有解释。",
            "needed": "场景描述和可核对的失败或限制证据，暂不假定存在研究空白。",
            "paper_uids": sources,
        },
        {
            "id": "feasible",
            "title": "从可用资源选择一个小切口",
            "question": f"结合目前可获得的资源，{topic}中哪个小问题值得先做一次低成本观察或验证？",
            "why": "适合希望动手，但不确定从哪里开始时。",
            "first_step": "先确认资料、数据或工具能否获得，再选一个可观察的现象；暂不做完整训练。",
            "needed": req.resources.strip()
            or "时间、数据、工具和算力均可先标为未知，再逐项确认。",
            "paper_uids": sources,
        },
    ]
    return {
        "kind": "guided_exploration",
        "directions": directions,
        "papers": papers,
        "brief": req.model_dump(),
        "notice": "这些是基于你的输入和本地资料整理的探索切口，不是已证实的研究空白；选择后仍可修改。没有调用模型。",
        "search_url": "/manage?q=" + quote(req.interests.strip() or "", safe=""),
    }
