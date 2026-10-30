"""Grounded, versioned node learning and reusable prerequisite/demo catalog."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from fastapi import HTTPException

from app.config import get_settings
from app.db import projects
from app.knowledge import extraction, model, store
from app.knowledge.unified import active

CATALOG = {
    "chain_rule": {"pattern": r"chain.?rule|链式|反向传播|backprop|局部导数", "label": "链式法则",
                   "summary": "复合函数的导数由沿计算路径的局部导数相乘得到；多条路径的贡献需要相加。",
                   "url": "https://docs.pytorch.org/tutorials/beginner/basics/autogradqs_tutorial.html"},
    "activations": {"pattern": r"sigmoid|tanh|饱和|激活函数|门控|gating|bounded|有界|限幅", "label": "sigmoid 与 tanh",
                    "summary": "sigmoid 将标量映射到 0 至 1；tanh 映射到 -1 至 1。饱和区域的局部导数较小。",
                    "url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.Tanh.html"},
    "gating": {"pattern": r"门控|gating|gated|bounded.?residual|有界残差|限幅", "label": "门控与有界残差",
               "summary": "门控控制信息或残差的作用幅度；放在非线性变换之前或之后，会改变局部梯度和幅值边界。",
               "url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.Sigmoid.html"},
    "gaussian": {"pattern": r"gaussian|高斯|正态分布|策略均值|normal distribution", "label": "高斯策略的均值与采样",
                 "summary": "均值确定采样分布中心，标准差确定扰动尺度；策略均值与实际采样动作应分别理解。",
                 "url": "https://docs.pytorch.org/docs/stable/distributions.html"},
    "ppo": {"pattern": r"\bppo\b|策略比率|联合裁剪|clipp|likelihood.?ratio", "label": "PPO 策略比率与裁剪",
            "summary": "PPO 使用新旧策略在观测动作上的概率比率构造裁剪目标；目标函数裁剪并不构成物理安全保证。",
            "url": "https://spinningup.openai.com/en/latest/algorithms/ppo.html"},
    "branches": {"pattern": r"分支|共享主干|双头|multi.?head|branch|shared.?trunk|cross.?branch", "label": "共享主干与分支信息路径",
                 "summary": "共享表示、分支输出与显式跨分支通路描述不同的信息路径。分支划分本身不等于独立智能体。",
                 "url": "https://docs.pytorch.org/docs/stable/generated/torch.nn.Module.html"},
}


def demos_for(node):
    text = node["label"] + " " + node.get("summary", "") + " " + str(node.get("metadata", {}).get("heading", ""))
    result = [key for key, value in CATALOG.items() if re.search(value["pattern"], text, re.I)]
    if node["kind"] == "formula":
        latex = str(node.get("metadata", {}).get("latex", ""))
        if "\\partial" in latex:
            result.append("chain_rule")
        if "tanh" in latex:
            result.append("activations")
            if "\\delta" in latex or "\\sigma" in latex:
                result.append("gating")
        if "clip" in latex:
            result.append("ppo")
    return list(dict.fromkeys(result))


def add_prerequisites(conn, pid, sid):
    src = store.source(conn, pid, sid)
    nodes = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_nodes WHERE project_id=? AND source_id=? AND hidden=0", (pid, sid))]
    for item in nodes:
        if not (item.get("metadata", {}).get("semantic") or item["kind"] == "formula") or item["kind"] not in {"method", "module", "formula", "algorithm", "concept"}:
            continue
        keys = demos_for(item)
        if "gating" in keys:
            keys += ["activations", "chain_rule"]
        for key in dict.fromkeys(keys):
            lesson = CATALOG[key]
            if item["label"].casefold() == lesson["label"].casefold():
                continue
            prerequisite = extraction.node(src, "prerequisite:" + key, "concept", lesson["label"], lesson["summary"], item["evidence_ids"],
                                            parent_id=store.identity(pid, sid, "root"), origin="inference",
                                            metadata={"educational": True, "demo": key, "url": lesson["url"]})
            store.put_record(conn, "kw_nodes", prerequisite)
            store.put_record(conn, "kw_edges", extraction.edge(src, prerequisite["id"], item["id"], "PREREQUISITE_OF", "帮助理解",
                "系统按知识类型匹配的教学建议，可按需展开或修订；不表示作者明确声明该学习依赖。", item["evidence_ids"], origin="inference"))


def prerequisites(conn, pid, node_id, max_depth=3):
    rows = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0", (pid,))]
    visited, frontier, result = {node_id}, {node_id}, []
    for _ in range(max_depth):
        ids = {e["source"] for e in rows if active(e) and e["kind"] == "PREREQUISITE_OF" and e["target"] in frontier} - visited
        frontier = set()
        for nid in sorted(ids):
            value = store.record(conn, "kw_nodes", pid, nid)
            if active(value) and not value["source_missing"]:
                result.append(value)
                frontier.add(nid)
            visited.add(nid)
            if len(result) >= 30:
                return result
        if not frontier:
            break
    return result


def resources_for(node):
    resources = []
    for key in demos_for(node):
        item = CATALOG[key]
        resources.append({"title": item["label"] + " · 官方资料", "url": item["url"], "reason": "与当前节点匹配的补充学习资料，非论文本身的结论", "type": "official_doc", "fetched": False})
    if node.get("metadata", {}).get("url"):
        resources.append({"title": "节点关联资源", "url": node["metadata"]["url"], "reason": "资料中保存的资源链接", "type": "source_link", "fetched": False})
    return list({r["url"]: r for r in resources}.values())


def discover_resources(pid, node, initial):
    """Discover real source links and scholarly metadata; never invent URLs."""
    from urllib.parse import urlencode
    from app.knowledge.sources import download
    resources = list(initial)
    with store.connection(pid) as conn:
        src = store.source(conn, pid, node["source_id"], blocks=True, include_removed=True)
        evidence = store.evidence(conn, pid, node["evidence_ids"])
        block_ids = {e["block_id"] for e in evidence}
        relevant = [b for b in src["blocks"] if b["id"] in block_ids]
        for block in relevant:
            meta = block.get("metadata", {})
            urls = re.findall(r"https://[^\s<>\[\]{}]+", block.get("text", ""))
            if isinstance(meta.get("url"), str):
                urls.append(meta["url"])
            for entry in meta.get("links") or []:
                if isinstance(entry, str):
                    urls.append(entry)
                elif isinstance(entry, dict) and entry.get("url"):
                    urls.append(entry["url"])
            for url in urls[:4]:
                url = url.rstrip('.,;，。；)')
                if not url.startswith('https://'):
                    continue
                resources.append({"title": "来源中提供的" + ("代码链接" if "github.com/" in url else "资料链接"), "url": url,
                                  "reason": "来自实际资料或已保存的代码快照；需核对版本和适用范围", "type": "code" if "github.com/" in url else "source_link", "fetched": False})
        conn.execute("CREATE TABLE IF NOT EXISTS kw_resource_search(fingerprint TEXT PRIMARY KEY,data TEXT NOT NULL)")
        query = node["label"][:120]
        key = store.identity(query, "semantic-scholar-search-v1")
        cached = conn.execute("SELECT data FROM kw_resource_search WHERE fingerprint=?", (key,)).fetchone()
    # Established educational modules already have direct official sources.
    if node["kind"] in {"concept", "algorithm", "method"} and len(initial) < 2:
        discovered = json.loads(cached[0]) if cached else []
        if not cached:
            try:
                url = get_settings().s2_api_base.rstrip('/') + '/paper/search?' + urlencode({'query': query, 'limit': 3, 'fields': 'title,url,openAccessPdf,externalIds'})
                raw, _, _ = download(url, max_bytes=200000)
                for item in json.loads(raw).get('data', []):
                    ids = item.get('externalIds') or {}
                    target = (item.get('openAccessPdf') or {}).get('url') or ('https://arxiv.org/abs/' + ids['ArXiv'] if ids.get('ArXiv') else item.get('url'))
                    if isinstance(target, str) and target.startswith('https://'):
                        discovered.append({'title': str(item.get('title') or '相关论文'), 'url': target, 'reason': '学术检索返回的相关资料；相关性需结合内容核对', 'type': 'paper', 'fetched': False})
                with store.connection(pid) as conn:
                    conn.execute("INSERT OR REPLACE INTO kw_resource_search VALUES(?,?)", (key, store.encode(discovered)))
            except Exception:
                pass
        resources.extend(discovered)
    return list({r['url']: r for r in resources if r.get('url')}.values())[:8]


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "footer"}:
            self.ignore += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer"}:
            self.ignore = max(0, self.ignore - 1)

    def handle_data(self, data):
        if not self.ignore and data.strip():
            self.parts.append(data.strip())


def fetch_resources(pid, resources):
    from app.knowledge.sources import download
    result = []
    with store.connection(pid) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kw_external_resources(url TEXT PRIMARY KEY,data TEXT NOT NULL)")
    for resource in resources[:4]:
        resource = dict(resource)
        with store.connection(pid) as conn:
            row = conn.execute("SELECT data FROM kw_external_resources WHERE url=?", (resource["url"],)).fetchone()
        if row:
            result.append({**resource, **json.loads(row[0])})
            continue
        try:
            raw, media, final_url = download(resource["url"], max_bytes=2_000_000)
            if "html" in media:
                parser = PlainHTML()
                parser.feed(raw.decode("utf-8", errors="replace"))
                text = "\n".join(parser.parts)
            elif raw.startswith(b"%PDF-"):
                import pymupdf
                with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                    text = "\n".join(pdf[i].get_text() for i in range(min(pdf.page_count, 8)))
            else:
                text = raw.decode("utf-8", errors="replace")
            # Prefer matching body content rather than documentation navigation.
            terms = re.findall(r"[A-Za-z]{4,}", resource["title"].casefold())
            lines = text.splitlines()
            indices = [i for i, line in enumerate(lines) if any(term in line.casefold() for term in terms)]
            if indices:
                start = indices[-1] if len(indices) > 10 else indices[0]
                text = "\n".join(lines[max(0, start - 3):start + 160])
            value = {"fetched": bool(text.strip()), "content": text[:10000], "final_url": final_url, "retrieved_at": store.now()}
            resource.update(value)
            with store.connection(pid) as conn:
                conn.execute("INSERT OR REPLACE INTO kw_external_resources VALUES(?,?)", (resource["url"], store.encode(value)))
        except Exception:
            resource["fetched"] = False
            resource["notice"] = "暂未读取到正文，此项仅作为资源入口"
        result.append(resource)
    return result + [dict(r) for r in resources[4:]]


def detail(conn, pid, nid):
    current = store.record(conn, "kw_nodes", pid, nid)
    adjacent = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0 AND (source=? OR target=?)", (pid, nid, nid))]
    adjacent = [edge for edge in adjacent if active(edge)]
    neighbor_ids = list(dict.fromkeys(x for e in adjacent for x in [e["source"], e["target"]] if x != nid))
    neighbors = [store.record(conn, "kw_nodes", pid, x) for x in neighbor_ids[:40]]
    neighbors = [n for n in neighbors if active(n) and not n['source_missing']]
    valid_ids = {nid} | {n['id'] for n in neighbors}
    adjacent = [edge for edge in adjacent if edge['source'] in valid_ids and edge['target'] in valid_ids]
    ids = current["evidence_ids"] + [i for e in adjacent for i in e["evidence_ids"]]
    evidence = store.evidence(conn, pid, ids)
    own_ids = set(current["evidence_ids"])
    return {"node": current, "edges": adjacent, "neighbors": neighbors, "evidence": evidence,
            "formula_sources": [e["formula"] for e in evidence if e["id"] in own_ids and e.get("formula")],
            "prerequisites": prerequisites(conn, pid, nid), "resources": resources_for(current), "demos": demos_for(current)}


def _learning_dependencies(conn, pid, nid):
    node = store.record(conn, "kw_nodes", pid, nid)
    edges = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0 AND (source=? OR target=?)", (pid, nid, nid))]
    base = prerequisites(conn, pid, nid)
    ids = {n["id"] for n in base} | {endpoint for e in edges for endpoint in (e["source"], e["target"])}
    related = [store.record(conn, "kw_nodes", pid, rid) for rid in sorted(ids) if rid != nid]
    # Do not traverse file-root containment into every unrelated node in the space.
    related = [n for n in related if n.get("parent_id") and not n.get("hidden")]
    source_ids = {node["source_id"]} | {n["source_id"] for n in related}
    source_versions = [(sid, store.source(conn, pid, sid, include_removed=True)) for sid in sorted(source_ids)]
    return node, related, edges, source_versions


def learning_fingerprint(conn, pid, nid, goal="", depth="deep"):
    from app.knowledge.learning_depth import RULES_VERSION, parameters
    goal, depth = parameters(goal, depth)
    node, related, edges, versions = _learning_dependencies(conn, pid, nid)
    project = projects.get_project(conn, pid)
    evidence_ids = node['evidence_ids'] + [eid for item in related + edges for eid in item.get('evidence_ids', [])]
    return store.identity(node, [(n["id"], n["version"], n.get("hidden")) for n in related], edges, store.evidence(conn, pid, evidence_ids),
        [(sid, s["version"], s["removed"], s["title"]) for sid, s in versions],
        {"question": project.research_question, "objective": project.constraints.objective},
        {"mode": store.preferences(conn, pid)["mode"], "goal": goal, "depth": depth},
        get_settings().llm_model, get_settings().llm_api_base, RULES_VERSION)


def basic(conn, pid, nid, goal="", depth="deep"):
    from app.knowledge.learning_depth import RULES_VERSION, coverage, parameters
    from app.knowledge.math_content import learning_quote, usable_latex
    goal, depth = parameters(goal, depth)
    data = detail(conn, pid, nid)
    n = data["node"]
    own = store.evidence(conn, pid, n["evidence_ids"])
    latex = usable_latex(n["metadata"].get("latex"))
    sections = {"overview": n["summary"] if n["kind"] != "formula" else "",
        "definition": "\n\n".join(learning_quote(e) for e in own[:3] if not e.get("formula")),
        "derivation": ("$$" + latex + "$$") if latex and not data["formula_sources"] else "",
        "prerequisites": "\n".join(p["label"] + "：" + p["summary"] for p in data["prerequisites"]),
        "implementation": "", "limitations": "基础内容来自当前资料。深入讲解属于教学补充，需结合原文的条件和范围理解。"}
    return {"id": store.identity(pid, nid, n["version"], goal, depth), "node_id": nid, "node_version": n["version"],
        "goal": goal, "depth": depth, "rules_version": RULES_VERSION, "status": "basic", "stale": False, "cached": False,
        "revision": 1, "origin": "source", "user_edited_sections": [], "hidden_sections": [], "sections": sections,
        "evidence": data["evidence"], "formula_sources": data["formula_sources"], "resources": data["resources"],
        "demos": data["demos"], "usage": {}, "errors": [],
        "coverage": coverage(sections, n, depth=depth, prerequisites=data["prerequisites"])}


def get_learning(conn, pid, nid, goal=None, depth=None):
    from app.knowledge.learning_depth import parameters, safe_presentation, variant
    from app.knowledge.math_content import project_learning
    node = store.record(conn, "kw_nodes", pid, nid)
    rows = [(r[0], json.loads(r[1])) for r in conn.execute("SELECT fingerprint,data FROM kw_learning WHERE project_id=? AND node_id=? ORDER BY rowid DESC", (pid, nid))]
    if goal is None and depth is None and rows:
        goal, depth = variant(rows[0][1])
    goal, depth = parameters(goal, depth)
    fp = learning_fingerprint(conn, pid, nid, goal, depth)
    candidates = [(key, value) for key, value in rows if variant(value) == (goal, depth)]
    match = next(((key, value) for key, value in candidates if key == fp), candidates[0] if candidates else None)
    if match:
        key, value = match
        ids = list(dict.fromkeys(node["evidence_ids"] + [e["id"] for e in value.get("evidence", [])]))
        evidence = store.evidence(conn, pid, ids)
        result = project_learning({**value, "goal": goal, "depth": depth, "cached": True,
            "stale": key != fp or bool(value.get("retained_from", {}).get("stale"))}, evidence)
        own = set(node["evidence_ids"])
        result["formula_sources"] = [e["formula"] for e in evidence if e["id"] in own and e.get("formula")]
        result["evidence"] = evidence
    else:
        result = basic(conn, pid, nid, goal, depth)
    unique = {}
    for _, value in rows:
        pair = variant(value)
        unique.setdefault(pair, {"id": value["id"], "goal": pair[0], "depth": pair[1], "status": value["status"]})
    result["variants"] = list(unique.values())[:20]
    return safe_presentation(result)


def revise(pid, nid, expected_revision, sections=None, hidden_sections=None, goal=None, depth=None):
    from app.knowledge.learning_depth import variant
    with model.operation(pid, 'learning:' + nid), store.connection(pid) as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = get_learning(conn, pid, nid, goal, depth)
        if current.get('revision', 1) != expected_revision:
            from fastapi import HTTPException
            raise HTTPException(409, '讲解已有新修订，请刷新后重试')
        pair = variant(current)
        fp = learning_fingerprint(conn, pid, nid, *pair)
        existing = [(r[0], json.loads(r[1])) for r in conn.execute('SELECT fingerprint,data FROM kw_learning WHERE project_id=? AND node_id=? ORDER BY rowid DESC', (pid, nid))]
        matching = [r for r in existing if variant(r[1]) == pair]
        match = next((r for r in matching if r[0] == fp), matching[0] if matching else None)
        if match:
            fp = match[0]
        conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)', (pid, nid, 'kw_learning', store.encode(current), store.now()))
        sections = sections or {}
        current['sections'].update(sections)
        current['user_edited_sections'] = sorted(set(current.get('user_edited_sections', [])) | set(sections))
        if hidden_sections is not None:
            current['hidden_sections'] = sorted(set(hidden_sections))
        current.update(revision=expected_revision + 1, origin='user', edited_at=store.now(), cached=True)
        _persist_learning(conn, pid, nid, fp, current)
        return current


def related_source_context(conn, pid, node, max_blocks=24):
    terms = set(re.findall(r"[A-Za-z][A-Za-z_\d-]{2,}", (node["label"] + " " + node["summary"]).casefold()))
    for pattern, words in [(r"门控", ["gate", "gating"]), (r"残差", ["residual"]), (r"分支", ["branch", "head"]), (r"裁剪", ["clip", "ratio"])]:
        if re.search(pattern, node["label"] + node["summary"]):
            terms.update(words)
    cited = store.evidence(conn, pid, node['evidence_ids'])
    ordinals = [e['locator']['ordinal'] for e in cited if e['source_id'] == node['source_id'] and e['locator'].get('ordinal') is not None]
    headings = {e['locator'].get('heading') for e in cited if e['source_id'] == node['source_id']}
    own, other = [], []
    # Shared terminology establishes comparison context, not implementation
    # identity. Pull foreign code only through an explicit implementation link.
    implementation_sources = set()
    implementation_blocks = set()
    for row in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0 AND (source=? OR target=?)", (pid, node['id'], node['id'])):
        edge = json.loads(row[0])
        if not active(edge):
            continue
        if edge['kind'] in {'IMPLEMENTS', 'IMPLEMENTED_BY'}:
            neighbor = store.record(conn, 'kw_nodes', pid, edge['target'] if edge['source'] == node['id'] else edge['source'])
            if not active(neighbor) or neighbor['source_missing']:
                continue
            implementation_sources.add(neighbor['source_id'])
            implementation_blocks.update(e['block_id'] for e in store.evidence(conn, pid, neighbor['evidence_ids']))
    for src in store.sources(conn, pid):
        blocks = store.source_blocks(conn, src["asset_id"])
        relevant_blocks = {e['block_id'] for e in cited if e['source_id'] == src['id']} | implementation_blocks
        referenced = set()
        owners = set()
        for item in blocks:
            if item['id'] in relevant_blocks and item.get('metadata', {}).get('symbol_kind') == 'function':
                referenced.update(re.findall(r'\bself\.([A-Za-z_]\w*)', item.get('text', '')))
                symbol = item['metadata'].get('symbol', '')
                if '.' in symbol:
                    owners.add(symbol.rsplit('.', 1)[0])
        for block in blocks:
            text = block.get("text", "")
            score = sum(min(text.casefold().count(t), 5) for t in terms)
            distance = min((abs(block['ordinal']-o) for o in ordinals), default=9999)
            meta = block.get('metadata', {})
            symbol = meta.get('symbol', '')
            function_definition = meta.get('symbol_kind') == 'function' and any(
                re.search(r'\bself\.' + re.escape(name) + r'\s*(?::[^=\n]+)?=', text) for name in referenced)
            if function_definition and (not owners or symbol.rsplit('.', 1)[0] in owners):
                score += 160
            if block['id'] in relevant_blocks:
                score += 200
            if src['id'] == node['source_id']:
                # Neighboring definitions and equations are essential even when
                # their mathematical symbols contain none of the label's words.
                score += 50 if distance <= 2 else 0
                score += 25 if block.get('heading') in headings else 0
                score += 20 if block['kind'] == 'formula' and distance <= 16 else 0
                score += 18 if distance <= 20 and re.search(r'初始化|初始策略|不能|不代表|不保证|边界|局部|limit|caveat|initializ', text, re.I) else 0
                own.append((score, -distance, src, block))
            elif src['id'] in implementation_sources and block['kind'] == 'code':
                other.append((score + (100 if block['id'] in implementation_blocks else 0), -distance, src, block))
    own.sort(key=lambda item: (-item[0], -item[1]))
    other.sort(key=lambda item: -item[0])
    ranked = own[:max_blocks-4] + other[:4]
    evidence = []
    for _, _, src, block in ranked:
        eid = store.add_evidence(conn, pid, src, block)
        for item in store.evidence(conn, pid, [eid]):
            item['context_role'] = 'linked_implementation' if src['id'] in implementation_sources else 'current_source'
            meta = block.get('metadata', {})
            if block['kind'] == 'code' and meta.get('symbol_kind') == 'function':
                item['code_context'] = {'text': block['text'], 'complete': True, 'kind': 'function',
                                        'symbol': meta.get('symbol', ''), 'start_line': meta.get('start_line'),
                                        'end_line': meta.get('end_line')}
            evidence.append(item)
    return evidence


def _linked_implementations(conn, pid, node, evidence):
    source_ids = set()
    for row in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0 AND (source=? OR target=?)", (pid, node["id"], node["id"])):
        edge = json.loads(row[0])
        if active(edge) and edge["kind"] in {"IMPLEMENTS", "IMPLEMENTED_BY"}:
            neighbor = store.record(conn, "kw_nodes", pid, edge["target"] if edge["source"] == node["id"] else edge["source"])
            if active(neighbor) and not neighbor["source_missing"]:
                source_ids.add(neighbor["source_id"])
    source_ids.add(node["source_id"])
    supplied = []
    for sid in sorted(source_ids):
        src = store.source(conn, pid, sid, include_removed=True)
        if src["removed"] or src["kind"] != "code":
            continue
        blocks = {b["id"]: b for b in store.source_blocks(conn, src["asset_id"]) if b["kind"] == "code"}
        matched = [e for e in evidence if e["source_id"] == sid and e["block_id"] in blocks]
        if matched:
            supplied.append({"id": sid, "title": src["title"], "version": src["version"],
                "relation": "current_code" if sid == node["source_id"] else "explicit_implementation_link",
                "evidence_ids": [e["id"] for e in matched], "locations": [e["locator"] for e in matched]})
    return supplied


def _prerequisite_context(conn, pid, nid):
    nodes = prerequisites(conn, pid, nid)[:10]
    ids = {nid} | {n["id"] for n in nodes}
    edges = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_edges WHERE project_id=? AND hidden=0", (pid,))]
    return {"nodes": [{k: n[k] for k in ("id", "label", "kind", "summary", "evidence_ids")} for n in nodes],
            "edges": [{k: e[k] for k in ("id", "source", "target", "label", "origin")} for e in edges
                      if active(e) and e["kind"] == "PREREQUISITE_OF" and e["source"] in ids and e["target"] in ids]}


def generate(pid, nid, refresh=False, goal="", depth="deep"):
    from app.knowledge.learning_depth import parameters
    goal, depth = parameters(goal, depth)
    with store.connection(pid) as conn:
        node = store.record(conn, 'kw_nodes', pid, nid)
        if not active(node) or node['source_missing']:
            raise HTTPException(409, '当前知识或来源已撤回，请先检查历史依据')
    with model.operation(pid, "learning:" + nid):
        from app.knowledge.formulas import ensure_node
        budget = model.Budget(pid, store.identity(pid, nid, goal, depth, store.now()), 4)
        errors = []
        try:
            ensure_node(pid, nid, budget)
        except model.ModelUnavailable as exc:
            errors.append(str(exc))
        return _generate(pid, nid, refresh, budget, errors, goal=goal, depth=depth)


def _generate(pid, nid, refresh=False, budget=None, initial_errors=None, *, goal="", depth="deep"):
    from app.knowledge.learning_depth import (GENERATION_PROMPT, REVIEW_PROMPT, RULES_VERSION,
        bounded_payload, coverage, model_sources, pack_evidence, parameters, requirements, safe_presentation)
    goal, depth = parameters(goal, depth)
    with store.connection(pid) as conn:
        fp = learning_fingerprint(conn, pid, nid, goal, depth)
        saved = get_learning(conn, pid, nid, goal, depth)
        if saved["status"] == "ready" and not saved["stale"] and not refresh:
            return saved
        value = basic(conn, pid, nid, goal, depth)
        current = store.record(conn, "kw_nodes", pid, nid)
        retrieved = related_source_context(conn, pid, current, max_blocks=24 if depth == 'deep' else 18)
        direct = store.evidence(conn, pid, current["evidence_ids"])
        prerequisite_graph = _prerequisite_context(conn, pid, nid)
        prereq_evidence = store.evidence(conn, pid, list(dict.fromkeys(e for n in prerequisite_graph['nodes'] for e in n['evidence_ids'])))
        value["evidence"] = pack_evidence(direct, sorted(retrieved, key=lambda e: e.get('context_role') != 'linked_implementation') + prereq_evidence, value["evidence"], depth=depth)
        by_id = {e["id"]: e for e in value["evidence"]}
        implementations = _linked_implementations(conn, pid, current, value["evidence"])
        prefs = store.preferences(conn, pid)
        project = projects.get_project(conn, pid)
        src = store.source(conn, pid, current['source_id'])
        from app.knowledge.teaching import references
        teaching = references(value['demos'])
        source_versions = {e['source_id']: e['source_version'] for e in value['evidence']}
    budget = budget or model.Budget(pid, value["id"], 4)
    value.update(errors=list(initial_errors or []), model_run_id=budget.run_id,
        rules_version=RULES_VERSION, generated_at=store.now(),
        context_summary={"evidence_count": len(value["evidence"]), "prerequisite_count": len(prerequisite_graph["nodes"]),
                         "linked_code_sources": [{k: item[k] for k in ("id", "title", "version")} for item in implementations],
                         "source_versions": [{"id": sid, "version": version} for sid, version in source_versions.items()]})
    code_supplied = bool(implementations)
    generation_failed = None
    if not model.available():
        generation_failed = "平台模型当前不可用；已保留可阅读内容"
    else:
        resources = fetch_resources(pid, discover_resources(pid, current, value["resources"]))
        value["resources"] = [{k: v for k, v in r.items() if k != "content"} for r in resources]
        protected = set(saved.get('user_edited_sections', [])) | set(saved.get('curated_sections', []))
        payload = {"node": {"id": current['id'], "label": current['label'], "kind": current['kind'],
                    "summary": current['summary'][:3000], "metadata": {k: current['metadata'][k] for k in ('latex', 'heading', 'symbol', 'path', 'start_line', 'end_line') if k in current['metadata']}},
            "goal": goal, "depth": depth, "mode": prefs["mode"], "research_question": project.research_question,
            "current_source": {"id": src['id'], "kind": src['kind'], "title": src['title'], "version": src['version'],
                "reported_at": src.get('reported_at'), "implementation_code_supplied": code_supplied},
            "linked_implementations": implementations, "prerequisite_graph": prerequisite_graph,
            "verified_teaching_reference": teaching, "sources": model_sources(value["evidence"]),
            "external_resources": [{**r, "content": r.get("content", "")[:2000]} for r in resources[:2]],
            "preserved_sections": {k: saved['sections'][k][:3000] for k in protected if k in saved['sections']},
            "coverage_requirements": requirements(current, depth=depth, code_supplied=code_supplied, prerequisites=prerequisite_graph['nodes']),
            "sections_required": list(value["sections"])}
        try:
            output_tokens = 10000 if depth == 'deep' else 6500
            result = model.structured(GENERATION_PROMPT, bounded_payload(payload, GENERATION_PROMPT, get_settings().research_model_max_input_chars, max_tokens=output_tokens), budget, "node_learning", max_tokens=output_tokens)
            sections = result.get("sections", {})
            if not isinstance(sections, dict) or any(not isinstance(sections.get(k), str) for k in value["sections"]):
                raise model.ModelUnavailable("学习讲解结构不完整")
            cited = result.get("evidence_ids", [])
            if not isinstance(cited, list) or (by_id and not cited) or any(e not in by_id for e in cited):
                raise model.ModelUnavailable("学习讲解包含未提供的来源标识")
            value['sections'] = {k: sections[k][:30000] for k in value['sections']}
            assessed = coverage(value['sections'], current, depth=depth, code_supplied=code_supplied, prerequisites=prerequisite_graph['nodes'])
            # One targeted expansion can use spare budget; the final source review is reserved.
            if assessed['missing'] and budget.calls + 2 <= budget.limit:
                expansion_prompt = GENERATION_PROMPT + '\n这是针对缺项的补充：只返回需要补充的section完整内容，保留既有正确内容；不能编造缺少的来源。'
                expanded = model.structured(expansion_prompt,
                    bounded_payload({**payload, 'sections': value['sections'], 'missing_teaching_content': assessed['missing']}, expansion_prompt, get_settings().research_model_max_input_chars, max_tokens=output_tokens),
                    budget, 'learning_expand', max_tokens=output_tokens)
                updates = expanded.get('sections', {})
                if isinstance(updates, dict) and all(k in value['sections'] and isinstance(v, str) for k, v in updates.items()):
                    value['sections'].update({k: v[:30000] for k, v in updates.items()})
            checked = model.structured(REVIEW_PROMPT, bounded_payload({**payload, 'sections': value['sections']}, REVIEW_PROMPT, get_settings().research_model_max_input_chars, max_tokens=8000), budget, 'learning_review', max_tokens=8000)
            corrections = checked.get('corrections', {})
            if not isinstance(corrections, dict) or any(k not in value['sections'] or not isinstance(v, str) for k, v in corrections.items()):
                raise model.ModelUnavailable('讲解校核返回格式不完整')
            issues = checked.get('issues', []) if isinstance(checked.get('issues'), list) else []
            if corrections:
                value['sections'].update({k: v[:30000] for k, v in corrections.items()})
            if checked.get('accepted') is not True and corrections and budget.calls < budget.limit:
                checked = model.structured(REVIEW_PROMPT, bounded_payload({**payload, 'sections': value['sections'], 'previous_issues': issues}, REVIEW_PROMPT, get_settings().research_model_max_input_chars, max_tokens=8000), budget, 'learning_review', max_tokens=8000)
                corrections = checked.get('corrections', {})
                if isinstance(corrections, dict) and all(k in value['sections'] and isinstance(v, str) for k, v in corrections.items()):
                    value['sections'].update({k: v[:30000] for k, v in corrections.items()})
            if checked.get('accepted') is not True:
                value['quality'] = {'review': 'failed', 'issues': issues[:12]}
                raise model.ModelUnavailable('讲解与原文的一致性检查未通过')
            value['quality'] = {'review': 'model_checked_not_independent', 'issues_addressed': issues[:12]}
            value['status'] = 'ready' if not value['errors'] else 'partial'
            if current['kind'] == 'formula' and not current.get('metadata', {}).get('latex'):
                value['status'] = 'partial'
                value['errors'].append('原始公式尚未可靠转写，已保留原图和可确定的学习说明')
        except model.ModelUnavailable as exc:
            generation_failed = str(exc)
    if generation_failed:
        # Keep this variant's good lesson; a failed refresh must not erase it.
        prior_rich = saved['status'] == 'ready' or any(len(saved['sections'].get(k, '')) >= 200 for k in ('derivation', 'implementation'))
        if prior_rich:
            value['sections'] = dict(saved['sections'])
            value['retained_from'] = {'id': saved['id'], 'node_version': saved['node_version'], 'stale': saved.get('stale', False)}
            value['quality'] = {**saved.get('quality', {}), 'last_attempt': 'failed_previous_content_retained'}
            value['errors'].append(generation_failed + '；上一版深入内容已保留')
        else:
            value['sections'] = basic_from_value(value, current)
            value['errors'].append(generation_failed + '；基础内容与原文已保留')
        value['status'] = 'partial'
    value['usage'] = budget.usage
    _preserve_learning_edits(value, saved)
    value['coverage'] = coverage(value['sections'], current, depth=depth, code_supplied=code_supplied, prerequisites=prerequisite_graph['nodes'])
    if value['coverage']['missing']:
        value['status'] = 'partial'
        value['errors'].append('仍需补充：' + '、'.join(value['coverage']['missing']))
    with store.connection(pid) as conn:
        if fp != learning_fingerprint(conn, pid, nid, goal, depth):
            value['stale'] = True
        _persist_learning(conn, pid, nid, fp, value)
        value['variants'] = get_learning(conn, pid, nid, goal, depth)['variants']
    return safe_presentation(value)


def basic_from_value(value, node):
    # This fallback never keeps rejected generated mathematics.
    from app.knowledge.math_content import learning_quote, usable_latex
    latex = usable_latex(node.get('metadata', {}).get('latex'))
    return {'overview': node['summary'] if node['kind'] != 'formula' else '',
        'definition': '\n\n'.join(learning_quote(e) for e in value['evidence'] if e['id'] in node['evidence_ids'] and not e.get('formula')),
        'derivation': '$$' + latex + '$$' if latex else '', 'prerequisites': '', 'implementation': '',
        'limitations': '基础内容来自当前资料。深入讲解属于教学补充，需结合原文的条件和范围理解。'}


def _persist_learning(conn, pid, nid, fp, value):
    old = conn.execute('SELECT data FROM kw_learning WHERE project_id=? AND node_id=? AND fingerprint=?', (pid, nid, fp)).fetchone()
    if old:
        conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)', (pid, nid, 'learning', old[0], store.now()))
    stored = {k: v for k, v in value.items() if k not in {'variants', 'cached'}}
    conn.execute('INSERT OR REPLACE INTO kw_learning VALUES(?,?,?,?)', (pid, nid, fp, store.encode(stored)))


def _preserve_learning_edits(value, previous):
    edited, curated = previous.get('user_edited_sections', []), previous.get('curated_sections', [])
    for key in edited:
        if key in previous['sections']:
            value['sections'][key] = previous['sections'][key]
    for key in set(curated) - set(edited):
        old = previous['sections'].get(key, '')
        new = value['sections'].get(key, '').strip()
        if not old:
            continue
        addition = new.replace(old, '').strip()
        value['sections'][key] = old + ('\n\n### 本次深入补充\n' + addition if addition and addition not in old else '')
    value['user_edited_sections'], value['curated_sections'] = edited, curated
    value['hidden_sections'] = previous.get('hidden_sections', [])
    value['revision'] = previous.get('revision', 1) + 1
    value['origin'] = 'user' if edited or value['hidden_sections'] else 'inference'
