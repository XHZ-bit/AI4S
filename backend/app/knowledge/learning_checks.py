"""Optional authored teaching checks and explicit, versioned learner feedback."""

import json
from uuid import uuid4

from fastapi import HTTPException

from app.knowledge import learning, store
from app.knowledge.graph_validity import active, current_records
from app.tenancy import current_user


CHECKS = {
    'attention_score': {
        'topics': ['softmax', 'scaled_attention'], 'version': 1,
        'title': '缩放分数和权重',
        'question': '教学输入 Q·K=8、d_k=4，除以 sqrt(d_k) 得到4.0。这个4.0是什么？',
        'choices': [{'id': 'score', 'text': 'softmax之前的一个缩放分数'},
                    {'id': 'probability', 'text': '这个位置已经得到的注意力概率'},
                    {'id': 'uncertain', 'text': '我还需要补充这部分基础'}],
        'correct': 'score', 'topic': 'softmax', 'topic_label': 'Softmax 与注意力权重',
        'explanation': '8 / sqrt(4) = 4.0。还需要把一组分数一起送入softmax，才得到和为1的权重。',
        'misconception': '你把缩放分数与归一化后的权重放在了一起。建议先用一组分数观察softmax，再回到原公式核对顺序。',
    },
    'dot_product': {
        'topics': ['dot_product'], 'version': 1, 'title': '向量点积怎样算',
        'question': '教学向量 x=(1,2)、y=(3,4)。它们的点积是多少？',
        'choices': [{'id': 'eleven', 'text': '11，对应元素相乘再相加'},
                    {'id': 'pair', 'text': '(3,8)，分别保存两个乘积'},
                    {'id': 'uncertain', 'text': '我还需要补充向量点积'}],
        'correct': 'eleven', 'topic': 'dot_product', 'topic_label': '向量点积',
        'explanation': '点积为1×3+2×4=11，结果是标量；(3,8)是逐元素乘积。',
        'misconception': '这个回答保留了逐元素乘积。点积还需要把这些乘积相加，可以先比较两种运算。',
    },
    'probability': {
        'topics': ['probability'], 'version': 1, 'title': '分数能否直接当概率',
        'question': '某模型给三个互斥且穷尽的选项输出原始分数(4,2,0)。这些原始分数能直接当作三个选项的概率吗？',
        'choices': [{'id': 'normalize', 'text': '需要明确概率转换规则，并检查范围与总和'},
                    {'id': 'largest', 'text': '最大的分数就是最大的概率值4'},
                    {'id': 'uncertain', 'text': '我还需要补充概率基础'}],
        'correct': 'normalize', 'topic': 'probability', 'topic_label': '概率、分数与归一化',
        'explanation': '这种离散概率分布的各项在0到1之间，总和为1。原始分数(4,2,0)需要明确的转换规则。',
        'misconception': '分数可以用来排序，但概率值还需要满足范围和归一化条件。建议先看一个离散分布的例子。',
    },
    'research_design': {
        'topics': ['research_design', 'variables_controls'], 'version': 1, 'title': '比较时还要核对哪些条件',
        'question': '一组学生回忆两天前读过的文章，另一组马上回忆刚读完的文章。仅凭两组分数，能把差异都归因于学习策略吗？',
        'choices': [{'id': 'conditions', 'text': '还要核对测试间隔等条件，两组条件同时有差异'},
                    {'id': 'strategy', 'text': '可以，分数更高就能证明学习策略更好'},
                    {'id': 'uncertain', 'text': '我还需要补充变量和对照'}],
        'correct': 'conditions', 'topic': 'research_design', 'topic_label': '变量、对照与研究设计',
        'explanation': '测试间隔也不同，当前信息不足以把分数差异全部归因于学习策略。应回到原文核对比较设计。',
        'misconception': '这次比较还有测试间隔的差异。建议先把研究变量和需要控制的条件逐项列出来。',
    },
    'samples': {
        'topics': ['sampling', 'sample_control', 'sample_generalization'], 'version': 1, 'title': '样本与结论适用范围',
        'question': '研究只招募了某校自愿参加的大学生。结果能直接代表所有年龄和背景的人吗？',
        'choices': [{'id': 'limits', 'text': '需要结合招募方式、人群与研究条件限定解释'},
                    {'id': 'everyone', 'text': '只要人数足够多，就可以直接代表所有人'},
                    {'id': 'uncertain', 'text': '我还需要补充样本与总体'}],
        'correct': 'limits', 'topic': 'sampling', 'topic_label': '样本、总体与适用范围',
        'explanation': '样本量增加不能自动消除招募选择和人群差异，需要核对研究的外部适用条件。',
        'misconception': '除了人数，还要看样本怎样招募、覆盖了谁。可以先区分样本、总体和推广条件。',
    },
}


def context(conn, pid, nid):
    node = store.record(conn, 'kw_nodes', pid, nid)
    source = store.source(conn, pid, node['source_id'], include_removed=True)
    evidence = store.evidence(conn, pid, node.get('evidence_ids', []))
    definitions = [(key, CHECKS[key]) for key in relevant(node)]
    fingerprint = store.identity('learning-check-context-v1', node, source['version'], source['removed'], evidence, definitions)
    return node, source, evidence, fingerprint


def relevant(node):
    topics = set(learning.demos_for(node))
    demo = node.get('metadata', {}).get('demo')
    if demo:
        topics.add(demo)
    return [key for key, item in CHECKS.items() if topics.intersection(item['topics'])]


def _history(conn, pid, nid):
    rows = conn.execute("SELECT data FROM kw_history WHERE project_id=? AND record_id=? AND kind='learning_check' ORDER BY id DESC LIMIT 20", (pid, nid))
    return [json.loads(row[0]) for row in rows]


def _dismissed(conn, pid, nid):
    rows = conn.execute("SELECT data FROM kw_history WHERE project_id=? AND record_id=? AND kind='learning_check_feedback' ORDER BY id DESC", (pid, nid))
    return {json.loads(row[0])['attempt_id'] for row in rows}


def get_checks(conn, pid, nid):
    node, source, _, fingerprint = context(conn, pid, nid)
    available = not source['removed'] and bool(current_records(conn, pid, [node]))
    dismissed = _dismissed(conn, pid, nid)
    questions = []
    for key in relevant(node):
        value = CHECKS[key]
        questions.append({k: value[k] for k in ('version', 'title', 'question', 'choices')} | {'id': key})
    history = []
    for attempt in _history(conn, pid, nid):
        definition = CHECKS.get(attempt['check_id'])
        stale = not available or attempt['context_fingerprint'] != fingerprint or not definition or attempt['check_version'] != definition['version']
        history.append({**attempt, 'stale': stale, 'dismissed': attempt['id'] in dismissed})
    return {'questions': questions, 'history': history, 'context_fingerprint': fingerprint,
            'available': available, 'origin': 'authored_teaching'}


def submit(conn, pid, nid, check_id, answer_id, expected_context, explanation=''):
    conn.execute('BEGIN IMMEDIATE')
    node, source, evidence, fingerprint = context(conn, pid, nid)
    if fingerprint != expected_context or source['removed'] or not current_records(conn, pid, [node]):
        raise HTTPException(409, '当前教学题、知识或来源已有变化，请重新读取本题后回答')
    definition = CHECKS.get(check_id)
    if not definition or check_id not in relevant(node):
        raise HTTPException(422, '这道教学检查不属于当前知识点')
    choice = next((item for item in definition['choices'] if item['id'] == answer_id), None)
    if not choice:
        raise HTTPException(422, '请选择题面中的一个回答')
    correct = answer_id == definition['correct']
    if correct:
        feedback = definition['explanation'] + ' 可以回到论文核对这些量的具体含义。'
    elif answer_id == 'uncertain':
        feedback = '可以先补充' + definition['topic_label'] + '，再回到当前问题。'
    else:
        feedback = definition['misconception']
    user = current_user.get()
    result = {'id': uuid4().hex, 'node_id': nid, 'node_label': node['label'], 'check_id': check_id,
              'check_version': definition['version'], 'question': definition['question'], 'answer_id': answer_id,
              'answer': choice['text'], 'correct': correct, 'feedback': feedback, 'explanation': explanation,
              'suggested_topic': None if correct else definition['topic'], 'suggested_label': definition['topic_label'],
              'context_fingerprint': fingerprint, 'source_id': source['id'], 'source_version': source['version'],
              'evidence': evidence, 'origin': 'authored_teaching_check', 'created_at': store.now(),
              'actor': (user.get('username') or user['id']) if user else '本机用户'}
    conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                 (pid, nid, 'learning_check', store.encode(result), result['created_at']))
    return {**result, 'stale': False, 'dismissed': False}


def dismiss(conn, pid, nid, attempt_id):
    store.record(conn, 'kw_nodes', pid, nid)
    row = conn.execute("SELECT id FROM kw_history WHERE project_id=? AND record_id=? AND kind='learning_check' AND json_extract(data,'$.id')=?", (pid, nid, attempt_id)).fetchone()
    if not row:
        raise HTTPException(404, '这条教学记录不在当前节点')
    value = {'attempt_id': attempt_id, 'created_at': store.now(), 'reason': '用户认为建议不适合当前需要'}
    conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                 (pid, nid, 'learning_check_feedback', store.encode(value), value['created_at']))
    return {'dismissed': True}


def recommendation(conn, pid):
    rows = conn.execute("SELECT data FROM kw_history WHERE project_id=? AND kind='learning_check' ORDER BY id DESC LIMIT 50", (pid,)).fetchall()
    latest = {}
    for row in rows:
        attempt = json.loads(row[0])
        pair = (attempt['node_id'], attempt['check_id'])
        latest.setdefault(pair, attempt)
    for attempt in latest.values():
        if attempt['correct'] or attempt['id'] in _dismissed(conn, pid, attempt['node_id']):
            continue
        try:
            node, source, _, fingerprint = context(conn, pid, attempt['node_id'])
        except HTTPException:
            continue
        definition = CHECKS.get(attempt['check_id'])
        if (not definition or definition['version'] != attempt['check_version'] or source['removed']
                or fingerprint != attempt['context_fingerprint'] or not active(node) or not current_records(conn, pid, [node])):
            continue
        candidates = [json.loads(row[0]) for row in conn.execute('SELECT data FROM kw_nodes WHERE project_id=? AND source_id=? AND hidden=0', (pid, node['source_id']))]
        foundations = [value for value in current_records(conn, pid, candidates)
                       if value.get('metadata', {}).get('demo') == attempt['suggested_topic']]
        target = foundations[0] if foundations else node
        return {'recommendation': {'attempt_id': attempt['id'], 'node_id': target['id'], 'label': target['label'],
                'source_node_id': node['id'], 'source_node_label': node['label'], 'reason': attempt['feedback'],
                'answer': attempt['answer'], 'question': attempt['question'], 'origin': 'authored_teaching_check'}}
    return {'recommendation': None}
