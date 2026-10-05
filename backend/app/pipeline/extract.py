"""抽取服务：论文文本 -> LLM -> 分级候选入库。

分级规则（设计 §4④）：
- 实体：confidence >= 0.5 保留候选，< 0.5 丢弃
- 关系：PREREQUISITE_OF 一律保留（命脉关系零容忍，全量人工）；其余 < 0.5 丢弃
"""
import logging

from app.db.proposals import save_proposal
from app.llm.client import chat, embed
from app.pipeline.prompts import build_messages
from app.pipeline.schemas import parse_extraction

logger = logging.getLogger(__name__)


def canonical_uid(etype: str, name: str) -> str:
    return f"{etype.lower()}:{name.lower().replace(' ', '-')}"


def extract_paper(conn, paper_uid: str, title: str, abstract: str, intro_excerpt: str = "") -> dict:
    messages = build_messages(title, abstract, intro_excerpt)
    raw = chat(messages, json_mode=True)
    result = parse_extraction(raw)

    retained_entities = [ent for ent in result.entities if ent.confidence >= 0.5]
    vectors = embed([ent.name for ent in retained_entities]) if retained_entities else []
    saved_entities = 0
    for ent, embedding in zip(retained_entities, vectors, strict=True):
        save_proposal(
            conn, paper_uid, "entity",
            {"type": ent.type, "name": ent.name, "evidence": ent.evidence},
            ent.confidence, embedding,
        )
        saved_entities += 1

    saved_relations = 0
    ent_type_by_name = {e.name.lower(): e.type for e in result.entities}
    for rel in result.relations:
        is_prereq = rel.rel_type == "PREREQUISITE_OF"
        if rel.confidence < 0.5 and not is_prereq:
            continue
        save_proposal(
            conn, paper_uid, "relation",
            {"rel_type": rel.rel_type, "src_name": rel.src_name, "dst_name": rel.dst_name,
             "src_type": ent_type_by_name.get(rel.src_name.lower(), "concept"),
             "dst_type": ent_type_by_name.get(rel.dst_name.lower(), "concept"),
             "evidence": rel.evidence},
            rel.confidence, None,
        )
        saved_relations += 1

    discarded = len(result.entities) + len(result.relations) - saved_entities - saved_relations
    logger.info("extract %s: entities=%s relations=%s discarded=%s",
                paper_uid, saved_entities, saved_relations, discarded)
    return {"entities": saved_entities, "relations": saved_relations, "discarded": discarded}
