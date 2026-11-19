"""The correspondence fixture must retain the actual denominator and region."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'evaluation/research_atlas/prepare_implementation_fixture.py'
SPEC = importlib.util.spec_from_file_location('implementation_fixture_geometry', SCRIPT)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


def native_parts():
    return [
        {'page': 4, 'text': 'Attention(Q, K, V ) = softmax(QKT\n',
         'bbox': [219.97, 464.96, 377.37, 482.95]},
        {'page': 4, 'text': '\u221adk\n)V\n(1)\n', 'bbox': [358.08, 472.56, 504.67, 491.24]},
    ]


def test_native_formula_merge_preserves_both_texts_and_unions_original_region():
    parts = native_parts()
    block = fixture.complete_attention_formula(parts)
    assert block['text'] == ''.join(part['text'] for part in parts)
    assert '\u221adk' in block['text'] and '(1)' in block['text']
    assert '\\sqrt' not in block['text']
    assert block['bbox'] == [219.97, 464.96, 504.67, 491.24]
    assert block['metadata']['latex'] == fixture.ATTENTION_LATEX
    assert block['metadata']['transcription_origin'] == 'developer_assistant'
    assert parts == native_parts()


@pytest.mark.parametrize('damage', ['missing', 'wrong_page', 'missing_denominator', 'distant_region'])
def test_incomplete_formula_never_silently_reverts_to_just_the_numerator(damage):
    parts = native_parts()
    if damage == 'missing':
        parts.pop()
    elif damage == 'wrong_page':
        parts[1]['page'] = 5
    elif damage == 'missing_denominator':
        parts[1]['text'] = ')V\n(1)\n'
    else:
        parts[1]['bbox'] = [358, 600, 504, 630]
    with pytest.raises(ValueError):
        fixture.complete_attention_formula(parts)
