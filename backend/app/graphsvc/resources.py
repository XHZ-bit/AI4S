"""Display-only access links. No network requests or invented download URLs."""
import re
from urllib.parse import quote, urlsplit

# First-party project/access pages checked 2026-10-25. Short names are candidates,
# not an assertion that two identically named datasets are the same resource.
PROJECTS = [
    (('bihoi',), 'BiHOI 官方项目与发布状态', 'https://ropedia.github.io/DONIC/'),
    (('ho-cap', 'hocap'), 'HO-Cap 官方项目与数据', 'https://irvlutd.github.io/HOCap/'),
    (('oakink2', 'oakink 2'), 'OakInk2 官方项目与数据', 'https://oakink.net/v2/'),
    (('oakink',), 'OakInk 官方项目与数据', 'https://oakink.net/'),
    (('gigahands',), 'GigaHands 官方代码与数据说明', 'https://github.com/brown-ivl/GigaHands'),
    (('grab',), 'GRAB 官方项目与访问申请', 'https://grab.is.tue.mpg.de/'),
    (('hoi4d', 'hoi4d: a 4d egocentric dataset for category-level human-object interaction'), 'HOI4D 官方项目与数据', 'https://hoi4d.github.io/'),
    (('hot3d',), 'HOT3D 官方项目与下载说明', 'https://facebookresearch.github.io/hot3d/'),
    (('arctic',), 'ARCTIC 官方项目与数据', 'https://arctic.is.tue.mpg.de/'),
    (('taco', 'taco (v1)', 'taco: benchmarking generalizable bimanual tool-action-object understanding'), 'TACO 双手交互数据集官方项目', 'https://taco2024.github.io/'),
    (('h2o', 'h2o: two hands manipulating objects for first person interaction recognition'), 'H2O 双手物体数据集官方仓库', 'https://github.com/taeinkwon/h2odataset'),
    (('isaac gym', 'isaacgym'), 'NVIDIA Isaac Gym 官方下载归档', 'https://developer.nvidia.com/isaac-gym/download'),
]


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r'[\x00-\x20]', value):
        return None
    try:
        p = urlsplit(value)
        return value if p.scheme in ('https', 'http') and p.hostname and not p.username and not p.password else None
    except ValueError:
        return None


def access_links(name, kind, payload=None):
    """Keep quoted links distinct from a name-matched, independently checked page."""
    if kind not in ('dataset', 'benchmark', 'resource'):
        return []
    payload = payload or {}
    links = []
    for key in ('url', 'source_url', 'website', 'homepage', 'download_url'):
        url = safe_url(payload.get(key))
        if url and not any(x['url'] == url for x in links):
            links.append({'url':url,'label':'原文登记链接','origin':'source_record','verified_at':None})
    # Extraction schemas do not always preserve a dedicated URL field. URLs in
    # the same evidence are useful, but must not be presented as a verified site.
    for raw in re.findall(r'https?://[^\s<>"\]\)]+', str(payload.get('evidence') or ''))[:4]:
        url = safe_url(raw.rstrip('.,;，。；'))
        if url and not any(x['url'] == url for x in links):
            links.append({'url':url,'label':'原文片段中的相关链接（需核对）','origin':'source_excerpt','verified_at':None})
    normalized = re.sub(r'\s+', ' ', name.strip().casefold())
    for aliases, label, url in PROJECTS:
        if normalized in aliases and not any(x['url'] == url for x in links):
            links.append({'url':url,'label':label,'origin':'name_match','verified_at':'2026-10-25','note':'按名称匹配的项目入口，请核对是否为论文使用的版本。'})
    links.append({'url':'https://www.bing.com/search?q='+quote(name+' dataset official'),'label':'搜索资源入口','origin':'web_search','verified_at':None})
    return links


def enrich(view):
    for node in view.get('nodes', []):
        if 'access_links' not in node:
            node['access_links'] = access_links(node.get('name',''), node.get('type'))
    return view
