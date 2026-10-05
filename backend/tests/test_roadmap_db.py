from app.db.roadmaps import save_roadmap, get_roadmap, list_roadmaps, update_item_done
from app.db.sqlite import connect
from app.models.roadmap import (
    LearnerProfile, RoadmapItem, RoadmapPhase, InnovationSuggestion, RoadmapResult,
)


def _sample_result():
    return RoadmapResult(
        goal="3个月入门具身智能",
        phases=[
            RoadmapPhase(phase=1, title="RL基础", weeks="第1-2周", items=[
                RoadmapItem(kind="paper", uid="paper:001", title="PPO论文",
                            reason="经典RL算法", evidence="PREREQUISITE_OF链"),
                RoadmapItem(kind="experiment", uid="method:ppo", title="复现PPO",
                            reason="动手理解", evidence="IMPROVES_ON链", difficulty=0.3),
            ]),
            RoadmapPhase(phase=2, title="操作方向", weeks="第3-4周", items=[
                RoadmapItem(kind="paper", uid="paper:002", title="Diffusion Policy",
                            reason="目标方法", evidence="目标实体"),
            ]),
        ],
        innovations=[
            InnovationSuggestion(title="稀疏对比的新方法", rationale="COMPARED_WITH稀疏",
                                 evidence="signal_a"),
        ],
    )


def test_save_and_get_roadmap():
    conn = connect(":memory:")
    rid = save_roadmap(conn, _sample_result(), LearnerProfile(goal="3个月入门具身智能"))
    assert rid >= 1
    got = get_roadmap(conn, rid)
    assert got.goal == "3个月入门具身智能"
    assert len(got.phases) == 2
    assert got.phases[0].items[0].title == "PPO论文"
    assert len(got.innovations) == 1


def test_list_roadmaps():
    conn = connect(":memory:")
    save_roadmap(conn, _sample_result(), LearnerProfile(goal="g1"))
    save_roadmap(conn, _sample_result(), LearnerProfile(goal="g2"))
    items = list_roadmaps(conn)
    assert len(items) == 2
    assert items[0]["id"] == 2 and items[1]["id"] == 1


def test_update_item_done():
    conn = connect(":memory:")
    rid = save_roadmap(conn, _sample_result(), LearnerProfile(goal="g"))
    updated = update_item_done(conn, rid, phase=1, item_index=0, done=True)
    assert updated.phases[0].items[0].done is True
    assert updated.phases[0].items[1].done is False
    reloaded = get_roadmap(conn, rid)
    assert reloaded.phases[0].items[0].done is True
