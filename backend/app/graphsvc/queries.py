"""Legacy graph query API backed exclusively by canonical SQLite knowledge."""

from app.graphsvc import local


def search_nodes(query, node_type=None, limit=20):
    return local.search(query, node_type, limit)


def overview(limit=100):
    return local.view(limit=limit)


def neighbors(uid, depth=1, limit=100):
    return local.view(limit=limit, uid=uid, depth=depth)
