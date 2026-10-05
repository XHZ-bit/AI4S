from app.roadmap.scoring import teaching_score, rank_papers


def test_teaching_score_survey_with_resource_newer_is_higher():
    base = {"citation_count": 50, "is_survey": False, "has_resource": False, "year": 2020}
    strong = {"citation_count": 200, "is_survey": True, "has_resource": True, "year": 2025}
    assert teaching_score(strong) > teaching_score(base)


def test_teaching_score_zero_citations_finite():
    p = {"citation_count": 0, "is_survey": False, "has_resource": False, "year": 2026}
    assert teaching_score(p) >= 0.0


def test_rank_papers_top_k():
    papers = [
        {"uid": "p1", "title": "A", "citation_count": 10, "is_survey": False, "has_resource": False, "year": 2024},
        {"uid": "p2", "title": "B", "citation_count": 500, "is_survey": True, "has_resource": True, "year": 2025},
        {"uid": "p3", "title": "C", "citation_count": 100, "is_survey": False, "has_resource": True, "year": 2023},
    ]
    ranked = rank_papers(papers, top_k=2)
    assert len(ranked) == 2
    assert ranked[0]["uid"] == "p2"
    assert "score" in ranked[0]
