import math
from datetime import date


def teaching_score(paper, current_year=None):
    current_year = current_year or date.today().year
    score = 0.0
    if paper.get("citation_count") is not None:
        score += math.log1p(max(0, paper["citation_count"]))
    if paper.get("is_survey") is True:
        score += 1.5
    if paper.get("has_resource") is True:
        score += 0.5
    if paper.get("year"):
        score += 0.8 * max(0.0, min(1.0, 1 - (current_year - paper["year"]) / 10))
    return score


def rank_papers(papers, top_k=2, current_year=None):
    result = [
        {
            **p,
            "score": teaching_score(p, current_year),
            "missing_fields": [
                k for k in ("citation_count", "is_survey", "year") if p.get(k) is None
            ],
        }
        for p in papers
    ]
    return sorted(result, key=lambda p: (-p["score"], p.get("uid", "")))[:top_k]
