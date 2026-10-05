def prerequisite_closure(target_uids: list[str], edges: list[tuple[str, str]]) -> set[str]:
    adj: dict[str, list[str]] = {}
    for src, dst in edges:
        adj.setdefault(dst, []).append(src)
    result: set[str] = set()
    stack = list(target_uids)
    while stack:
        node = stack.pop()
        if node in result:
            continue
        result.add(node)
        for prereq in adj.get(node, []):
            if prereq not in result:
                stack.append(prereq)
    return result


def topological_sort(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    nodeset = set(nodes)
    indeg: dict[str, int] = {n: 0 for n in nodeset}
    adj: dict[str, list[str]] = {n: [] for n in nodeset}
    for src, dst in edges:
        if src in nodeset and dst in nodeset:
            adj[src].append(dst)
            indeg[dst] += 1
    queue = [n for n in sorted(set(nodes)) if indeg.get(n, 0) == 0]
    order: list[str] = []
    remaining = set(nodeset)
    while queue or remaining:
        if not queue:
            raise ValueError("prerequisite cycle detected")
        node = queue.pop(0)
        if node not in remaining:
            continue
        order.append(node)
        remaining.discard(node)
        for nxt in adj[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0 and nxt in remaining:
                queue.append(nxt)
    return order


def prune_known(order: list[str], known: set[str]) -> list[str]:
    return [n for n in order if n not in known]
