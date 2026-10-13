import json
from pathlib import Path

import pytest

from src.core.review.image_filter import ImageFilterResult
from src.core.review.image_layout import apply_image_layout, body_blocks, image_catalog, layout_context
from src.core.review.output_contract import ReviewPayload, render_review_payload


@pytest.fixture
def article(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    for index in range(1, 5):
        (assets / f'{index}.png').write_bytes(f'image {index}'.encode())
    body = ('## Steps\n\n1. Collect the evidence.\n2. Interpret the result.\n\n'
            + '\n\n'.join(f'![Image {index}](assets/{index}.png)' for index in range(1, 5))
            + '\n\n## Detail\n\nThe complete explanation remains intact.\n')
    markdown = render_review_payload(ReviewPayload('Title', body, 'Internal summary'), '> Source: https://example.com\n')
    return markdown, assets


def keep_plan(catalog):
    return {'images': [{'id': entry.id, 'action': 'keep'} for entry in catalog], 'text_edits': []}


def test_keep_preserves_every_byte_and_header_is_not_an_anchor(article):
    markdown, assets = article
    catalog = image_catalog(markdown, markdown, assets)
    blocks = body_blocks(markdown)
    result = apply_image_layout(markdown, json.dumps(keep_plan(catalog)), catalog, blocks)
    assert result.markdown == markdown
    assert not result.removed_paths
    assert all(block.start >= markdown.index('## Steps') for block in blocks)


def test_moves_images_into_list_items_in_model_order_without_changing_prose(article):
    markdown, assets = article
    catalog = image_catalog(markdown, markdown, assets)
    blocks = body_blocks(markdown)
    first = next(block.id for block in blocks if block.text.startswith('1.'))
    second = next(block.id for block in blocks if block.text.startswith('2.'))
    plan = {'images': [
        {'id': 'image_003', 'action': 'move', 'target': first, 'reason': 'Evidence', 'side': 'after'},
        {'id': 'image_001', 'action': 'move', 'target': first, 'reason': 'Evidence', 'side': 'after'},
        {'id': 'image_004', 'action': 'move', 'target': second, 'reason': 'Result', 'side': 'after'},
        {'id': 'image_002', 'action': 'move', 'target': second, 'reason': 'Result', 'side': 'after'},
    ]}
    result = apply_image_layout(markdown, json.dumps(plan), catalog, blocks)
    assert result.markdown.index('assets/3.png') < result.markdown.index('assets/1.png') < result.markdown.index('2. Interpret')
    assert result.markdown.index('2. Interpret') < result.markdown.index('assets/4.png') < result.markdown.index('assets/2.png')
    assert '   ![Image 3](assets/3.png)' in result.markdown
    for block in blocks:
        assert block.text in result.markdown
    for entry in catalog:
        assert result.markdown.count(entry.path) == 1
    assert result.markdown[:markdown.index('## Steps')] == markdown[:markdown.index('## Steps')]


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown', 'invalid_target', 'missing_reason', 'metadata_edit', 'unrelated_edit'])
def test_invalid_plans_do_not_produce_partial_results(article, mutation):
    markdown, assets = article
    catalog = image_catalog(markdown, markdown, assets)
    blocks = body_blocks(markdown)
    plan = keep_plan(catalog)
    if mutation == 'missing':
        plan['images'].pop()
    elif mutation == 'duplicate':
        plan['images'].append(plan['images'][0])
    elif mutation == 'unknown':
        plan['images'][0]['id'] = 'invented'
    elif mutation == 'invalid_target':
        plan['images'][0].update(action='move', target='metadata', reason='Move')
    elif mutation == 'missing_reason':
        plan['images'][0].update(action='remove')
    elif mutation == 'metadata_edit':
        plan['text_edits'] = [{'id': blocks[0].id, 'text': '> Source: forged', 'reason': 'Change'}]
    else:
        plan['text_edits'] = [{'id': blocks[1].id, 'text': 'Rewritten prose', 'reason': 'Unrelated rewrite'}]
    with pytest.raises(ValueError):
        apply_image_layout(markdown, json.dumps(plan), catalog, blocks)


def test_local_image_transition_edit_preserves_other_blocks(article):
    markdown, assets = article
    catalog = image_catalog(markdown, markdown, assets)
    blocks = body_blocks(markdown)
    target = next(block for block in blocks if block.text.startswith('2.'))
    plan = keep_plan(catalog)
    plan['images'][0].update(action='move', target=target.id, reason='Illustrates the result')
    replacement = '2. Interpret the result using the illustration below.'
    plan['text_edits'] = [{'id': target.id, 'text': replacement, 'reason': 'Refer to the moved image'}]
    result = apply_image_layout(markdown, json.dumps(plan), catalog, blocks)
    assert replacement in result.markdown
    assert replacement + '\n\n   ![Image 1]' in result.markdown
    assert 'The complete explanation remains intact.' in result.markdown


def test_stable_ids_keep_gaps_and_ignore_code_examples_and_external_files(article):
    markdown, assets = article
    source = markdown
    current = markdown.replace('![Image 2](assets/2.png)', '')
    current += '\n```md\n![literal](assets/2.png)\n```\n![private](../private.png)\n'
    (assets.parent.parent / 'private.png').write_bytes(b'outside')
    catalog = image_catalog(current, source, assets)
    assert [entry.id for entry in catalog] == ['image_001', 'image_003', 'image_004']
    assert all('```' not in block.text for block in body_blocks(current))


def test_inline_image_move_can_adjust_its_own_paragraph_without_conflicting_edits(article):
    markdown, assets = article
    markdown = markdown.replace('1. Collect the evidence.', '1. Collect the evidence as shown here: ![Image 1](assets/1.png)')
    markdown = markdown.replace('\n\n![Image 1](assets/1.png)', '')
    catalog = image_catalog(markdown, markdown, assets)
    blocks = body_blocks(markdown)
    source = next(block for block in blocks if block.text.startswith('1.'))
    target = next(block for block in blocks if block.text.startswith('2.'))
    plan = keep_plan(catalog)
    plan['images'][0].update(action='move', target=target.id, reason='Illustrates interpretation')
    plan['text_edits'] = [{'id': source.id, 'text': '1. Collect the evidence.', 'reason': 'Remove the now-invalid image reference'}]
    result = apply_image_layout(markdown, json.dumps(plan), catalog, blocks)
    assert 'as shown here' not in result.markdown
    assert result.markdown.count('assets/1.png') == 1
    assert result.markdown.index('2. Interpret') < result.markdown.index('assets/1.png')


def test_long_context_is_bounded_and_allows_global_image_movement(article):
    markdown, assets = article
    first_part = 'First part. ' * 2200
    second_part = 'Second part. ' * 2200
    markdown = markdown.replace('1. Collect the evidence.', first_part + '\n').replace('2. Interpret the result.', second_part)
    context, catalog, blocks = layout_context(markdown, markdown, assets, None, 'Summary')
    records = json.loads(context)['blocks']
    assert len(context) < 18000
    assert any(record['truncated'] and not record['editable'] for record in records)
    target = next(block for block in blocks if block.text.startswith('First part'))
    plan = keep_plan(catalog)
    plan['images'][3].update(action='move', target=target.id, reason='Related to first part')
    result = apply_image_layout(markdown, json.dumps(plan), catalog, blocks)
    assert first_part in result.markdown and second_part in result.markdown
    assert result.markdown.index('assets/4.png') < result.markdown.index('Second part.')
    plan['text_edits'] = [{'id': target.id, 'text': 'Compressed', 'reason': 'Rewrite'}]
    with pytest.raises(ValueError):
        apply_image_layout(markdown, json.dumps(plan), catalog, blocks)
