"""Seed data integration uses synthetic, explicitly reviewed test records."""

from tests.test_roadmap_generate import setup_trusted
from app.models.roadmap import LearnerProfile
from app.roadmap.generate import generate_roadmap
from app.db.roadmaps import get_roadmap, update_item_done


def test_seed_reading_progress_survives_reload():
    conn = setup_trusted()
    result = generate_roadmap(
        LearnerProfile(goal="target", target_uid="method:target"), conn
    )
    first = result.phases[0].items[0]
    update_item_done(
        conn, result.id, task_id=first.task_id, version=result.version, done=True
    )
    assert get_roadmap(conn, result.id).phases[0].items[0].done
    assert len(result.knowledge_ids) >= 2


def test_seed_prune_known_skips_basics():
    conn = setup_trusted()
    result = generate_roadmap(
        LearnerProfile(
            goal="target", target_uid="method:target", known_concepts=["concept:basics"]
        ),
        conn,
    )
    assert len(result.phases) == 1
    assert not result.innovations
