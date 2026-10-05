"""Add non-destructive paper-to-approved-entity MENTIONS relationships."""

from app.db.proposals import list_proposals
from app.db.sqlite import connect
from app.graphsvc import entities
from app.pipeline.extract import canonical_uid


def main() -> None:
    conn = connect()
    created = set()
    for proposal in list_proposals(conn, status="approved"):
        payload = proposal["payload"]
        candidates = []
        if proposal["kind"] == "entity":
            entity_type = payload["type"]
            uid = payload.get("canonical_uid") or entities.find_entity_uid_by_name(
                conn, payload["name"], entity_type
            ) or canonical_uid(entity_type, payload["name"])
            candidates.append(uid)
        elif proposal["kind"] == "relation":
            for side in ("src", "dst"):
                entity_type = payload.get(f"{side}_type", "concept")
                name = payload[f"{side}_name"]
                uid = entities.find_entity_uid_by_name(conn, name, entity_type) or canonical_uid(
                    entity_type, name
                )
                candidates.append(uid)
        for uid in candidates:
            edge = (proposal["paper_uid"], uid)
            if edge not in created:
                entities.merge_relation("MENTIONS", *edge)
                created.add(edge)
    print(f"paper mention relationships ensured: {len(created)}")


if __name__ == "__main__":
    main()