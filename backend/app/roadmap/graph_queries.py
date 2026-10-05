from app.db.neo4j_client import get_driver


def resolve_target(name):
    with get_driver().session() as session:
        rows = list(
            session.run(
                "MATCH (n:Entity) WHERE (toLower(n.name)=toLower($name) OR n.uid=$name) AND n.type IN ['concept','method'] RETURN n.uid AS uid LIMIT 2",
                name=name,
            )
        )
        return rows[0]["uid"] if len(rows) == 1 else None


def get_prerequisite_edges():
    with get_driver().session() as session:
        return [
            (r["src"], r["dst"])
            for r in session.run(
                "MATCH (a)-[r:PREREQUISITE_OF]->(b) WHERE r.quality_status='human_verified' RETURN a.uid AS src,b.uid AS dst"
            )
        ]


def get_papers_for_concept(concept_uid):
    query = (
        "MATCH (p:Paper)-[r:PROPOSES|USES|MENTIONS]->(c {uid:$uid}) "
        "WHERE r.quality_status='human_verified' AND r.passage_id IS NOT NULL "
        "RETURN p.uid AS uid,p.title AS title,p.year AS year,p.code_url AS code_url,"
        "collect(DISTINCT r.passage_id) AS evidence_ids,collect(DISTINCT r.knowledge_id) AS knowledge_ids,"
        "p.citation_count AS citation_count,p.is_survey AS is_survey"
    )
    with get_driver().session() as session:
        return [
            {**dict(r), "has_resource": bool(r.get("code_url"))}
            for r in session.run(query, uid=concept_uid)
        ]


def get_improves_on_chain(method_uid):
    query = (
        "MATCH path=(m {uid:$uid})-[:IMPROVES_ON*0..5]->(base) "
        "WHERE ALL(r IN relationships(path) WHERE r.quality_status='human_verified') "
        "WITH path ORDER BY length(path) DESC LIMIT 1 "
        "UNWIND reverse(nodes(path)) AS n RETURN n.uid AS uid,n.name AS name,n.type AS type"
    )
    with get_driver().session() as session:
        return [
            {**dict(r), "has_resource": None, "difficulty": None}
            for r in session.run(query, uid=method_uid)
        ]


def get_method_stats():
    query = (
        "MATCH (m:Method) OPTIONAL MATCH (m)-[comparison:COMPARED_WITH]-() "
        "WITH m,count(DISTINCT comparison) AS cw OPTIONAL MATCH (m)<-[improvement:IMPROVES_ON]-() "
        "RETURN m.uid AS uid,m.name AS name,cw AS compared_with_count,m.citation_count AS citation_count,"
        "count(DISTINCT improvement) AS improves_on_successors"
    )
    with get_driver().session() as session:
        return [dict(r) for r in session.run(query)]


def get_benchmark_coverage():
    with get_driver().session() as session:
        return [
            dict(r)
            for r in session.run(
                "MATCH (b:Benchmark) OPTIONAL MATCH (method:Method)-[:EVALUATES_ON]->(b) RETURN b.uid AS uid,b.name AS name,count(DISTINCT method) AS method_count"
            )
        ]
