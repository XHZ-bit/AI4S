"""Extend an existing isolated teaching fixture via normal HTTP uploads/APIs only."""
import json
import sys
import time
from pathlib import Path

import fitz
import httpx

directory = Path(sys.argv[1] if len(sys.argv) > 1 else '.ui_validation/practice-desk-20261117').resolve()
assert '.ui_validation' in directory.parts
base = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18159'
assert ':18159' in base
fixture = json.loads((directory / 'fixture.json').read_text(encoding='utf-8-sig'))
root = f"{base}/api/projects/{fixture['project_id']}"
output = directory / 'core-space-browser'
output.mkdir(exist_ok=True)
extra_path = output / 'fixture-extra.json'
if extra_path.exists():
    extra=json.loads(extra_path.read_text(encoding='utf-8'))
    with httpx.Client(timeout=45) as client:
        if not extra.get('code_source_id'):
            code=b'import math\n\n# Authored teaching implementation, not paper source code.\ndot = 8\nd_k = 4\nscaled = dot / math.sqrt(d_k)\nprint(scaled)\n'
            response=client.post(root+'/sources',files={'file':('authored_teaching.py',code,'text/x-python')},data={'kind':'code'});response.raise_for_status()
            extra['code_source_id']=response.json()['source']['id']
        items=client.get(root+'/knowledge/comparisons').json()['items']
        comparison=next(c for c in items if c['id']==extra['comparison_id'])
        evidence=next(e for e in comparison['evidence'] if e['source_id']==extra['pdf_source_id'] and e.get('locator',{}).get('page')==3)
        if not extra.get('comparison_pdf_evidence_id'):
            response=client.patch(root+'/knowledge/comparisons/'+comparison['id'],json={'source_ids':comparison['source_ids'],'focus_node_ids':comparison.get('focus_node_ids',[]),'dimensions':comparison.get('dimensions') or [r['dimension'] for r in comparison['rows']],'template':'method','expected_revision':comparison['revision'],'dimension':comparison['rows'][0]['dimension'],'source_id':extra['pdf_source_id'],'text':'教学验收资料第3页展示固定输入与缩放分数，用于核对页码与原文返回。','evidence_ids':[evidence['id']],'reviewed':True});response.raise_for_status()
            extra['comparison_pdf_evidence_id']=evidence['id'];extra['comparison_pdf_dimension']=comparison['rows'][0]['dimension']
    extra_path.write_text(json.dumps(extra,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(extra,ensure_ascii=False))
    raise SystemExit(0)
pdf_path = output / 'authored-teaching-pages.pdf'
doc = fitz.open()
for i in range(1, 5):
    page = doc.new_page(width=595, height=842)
    page.insert_text((42, 54), '这是教学验收资料', fontname='china-s', fontsize=20)
    page.insert_text((42, 90), f'Page {i}: authored engineering fixture - not a research paper', fontsize=12)
    page.insert_text((42, 130), 'Purpose: verify local PDF pages, navigation and evidence return.', fontsize=11)
    page.insert_text((42, 170), f'Fixed teaching score = 8 / sqrt(4) = 4.0; fixture page {i}.', fontsize=12)
    page.insert_text((42, 210), 'No experimental claim or third-party copyrighted content is included.', fontsize=11)
    for row in range(14):
        page.insert_text((42, 260+row*28), f'Teaching reading line {row+1}: compare inputs, conditions, and sources.', fontsize=10)
doc.set_metadata({'title': '这是教学验收资料', 'author': 'PaperStride engineering acceptance'})
doc.save(pdf_path)
extra = {'source_kind': 'authored_teaching_material', 'real_provider_calls': 0, 'pdf_file': str(pdf_path)}
with httpx.Client(timeout=45) as client:
    response = client.post(root+'/sources', files={'file': (pdf_path.name,pdf_path.read_bytes(),'application/pdf')}, data={'kind':'paper'})
    response.raise_for_status()
    extra['pdf_source_id'] = response.json()['source']['id']
    response = client.patch(root+'/sources/'+extra['pdf_source_id'], json={'title':'这是教学验收资料：多页PDF'})
    response.raise_for_status()
    for _ in range(120):
        response=client.get(root+'/sources/'+extra['pdf_source_id']); response.raise_for_status()
        source=response.json()
        if source.get('blocks'):
            break
        time.sleep(.25)
    extra['pdf_blocks'] = len(source.get('blocks',[]))
    extra['pdf_block_id'] = next((b['id'] for b in source.get('blocks',[]) if b.get('page')==3), source.get('blocks',[{}])[0].get('id'))
    response=client.post(root+'/knowledge/comparisons',json={'source_ids':[fixture['source_id'],extra['pdf_source_id']],'template':'method'})
    response.raise_for_status(); comparison=response.json()
    extra['comparison_id']=comparison.get('id'); extra['comparison_rows']=len(comparison.get('rows',[]))
    response=client.get(root+'/knowledge/learning-route');response.raise_for_status();route=response.json()['route']
    if not route:
        response=client.post(root+'/knowledge/learning-route/preview',json={'target_node_id':fixture['nodes']['goal']});response.raise_for_status();preview=response.json()
        response=client.post(root+'/knowledge/learning-route',json={'target_node_id':fixture['nodes']['goal'],'expected_revision':0,'preview_fingerprint':preview['preview_fingerprint']});response.raise_for_status();route=response.json()['route']
    extra['route_revision']=route['revision'];extra['route_steps']=len(route['steps'])
extra_path.write_text(json.dumps(extra,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(extra,ensure_ascii=False))
