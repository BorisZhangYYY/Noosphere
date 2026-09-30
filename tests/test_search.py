"""Search relevance, isolation and file reconciliation regressions."""
import json
from test_web_api import web_client
from src.core.search import search_articles, synchronize, passage, excerpt
from src.application import service


def test_excerpt_keeps_image_reference_when_markdown_crosses_window_edge():
    text = 'needle' + 'x' * 260 + '![figure](assets/diagram.png)'
    result = excerpt(text, ['needle'])
    assert result['images'] == [{'alt': 'figure', 'path': 'assets/diagram.png'}]
    assert '![figure](assets/diagram.png)' in result['text']


def test_excerpt_keeps_markdown_blocks_and_image_at_its_original_position():
    text = '## 标题\n\n**关键词** 前文。\n\n![示意图](assets/diagram.png)\n\n- 后续列表'
    result = excerpt(text, ['关键词'], field='reviewed')

    assert result['text'].index('**关键词**') < result['text'].index('![示意图]') < result['text'].index('- 后续列表')
    hit = result['highlights'][0]
    assert result['text'][hit[0]:hit[1]] == '关键词'


def test_excerpt_keeps_table_header_and_code_fence_around_hits():
    table = '| 名称 | 说明 |\n| --- | --- |\n' + ''.join(f'| Agent {index} | 前文内容 |\n' for index in range(8)) + '| MCP | 关键词 |\n| A2A | 后文 |'
    result = excerpt('介绍\n\n' + table + '\n\n结尾', ['关键词'], field='reviewed')
    assert '| 名称 | 说明 |' in result['text']
    assert '| --- | --- |' in result['text']
    assert '| A2A | 后文 |' in result['text']

    code = '```python\n' + ''.join(f'print("before {index}")\n' for index in range(8)) + 'print("关键词")\nprint("after")\n```'
    result = excerpt('介绍\n\n' + code + '\n\n结尾', ['关键词'], field='reviewed')
    assert '```python' in result['text']
    assert 'print("after")\n```' in result['text']


def test_reviewed_excerpt_starts_after_article_metadata():
    text = (
        '# 碎星将军\n\n'
        '> Source: [link](https://example.com/long-source)\n'
        '> Captured: 2026-07-29T10:40:43+08:00\n\n'
        '---\n\n'
        '## AI 摘要\n\n'
        '文章以“拉塔恩”为原型。\n'
        '- 描述拉塔恩的生平。'
    )
    result = excerpt(text, ['拉塔恩'], field='reviewed')

    assert result['text'].startswith('\n## AI 摘要')
    assert 'Captured' not in result['text']
    assert '2026-07-29' not in result['text']
    hit = result['highlights'][0]
    assert result['text'][hit[0]:hit[1]] == '拉塔恩'
    assert text[result['start'] + hit[0]:result['start'] + hit[1]] == '拉塔恩'


def test_chinese_two_character_and_mixed_phrase(web_client):
    _, config, article_id = web_client
    service.save_reviewed_markdown(article_id, '# Knowledge\n\n知识管理帮助理解 Agent v0.3.2.6 的变化。\n\nOther paragraph.')
    for text in ['知识', '管理', 'Agent', 'v0.3.2.6', '"知识管理"', '"Agent v0.3.2.6"']:
        result = search_articles(text)
        assert result['total'] == 1, text
        assert result['results'][0]['article']['id'] == article_id
    assert search_articles('"管理知识"')['total'] == 0
    assert search_articles('nonexistent')['total'] == 0


def test_separate_scopes_and_raw_is_opt_in(web_client):
    _, config, article_id = web_client
    directory = config.parent / 'articles' / article_id
    (directory / 'reflection.md').write_text('Private reflectionneedle')
    (directory / 'annotations.json').write_text(json.dumps({'annotations': [{'note': 'annotationneedle', 'quote': 'A quote'}]}))
    assert search_articles('reflectionneedle', scope='reflection')['total'] == 1
    assert search_articles('reflectionneedle', scope='reviewed')['total'] == 0
    assert search_articles('annotationneedle')['total'] == 1
    assert search_articles('Raw')['total'] == 0
    assert search_articles('Raw', scope='raw')['total'] == 1


def test_external_edits_rebuild_and_stale_passage(web_client):
    _, config, article_id = web_client
    directory = config.parent / 'articles' / article_id
    service.save_reviewed_markdown(article_id, '# Locate\n\noriginalneedle')
    result = search_articles('originalneedle')['results'][0]['matches'][0]
    assert not passage(article_id, result['field'], result['digest'], result['start'])['changed']
    (directory / 'reviewed.md').write_text('# New\n\nreplacementneedle')
    assert search_articles('originalneedle')['total'] == 0
    assert search_articles('replacementneedle')['total'] == 1
    assert passage(article_id, result['field'], result['digest'])['changed']
    assert synchronize(rebuild=True)['articles'] == 1


def test_trash_and_restore_search_visibility(web_client):
    _, _, article_id = web_client
    assert search_articles('Context')['total'] == 1
    service.trash_articles([article_id])
    assert search_articles('Context')['total'] == 0
    service.restore_trashed_articles([article_id])
    assert search_articles('Context')['total'] == 1
    service.trash_articles([article_id])
    service.permanently_delete_trashed_articles([article_id])
    assert search_articles('Context')['total'] == 0


def test_http_search_validation_and_literal_query(web_client):
    client, _, _ = web_client
    assert client.get('/api/v1/search?q=Context').json()['total'] == 1
    for params in ['q=test&scope=unknown', 'q=test&offset=-1', 'q=test&limit=0', 'q=test&limit=no']:
        assert client.get('/api/v1/search?' + params).status_code == 400
    assert client.get('/api/v1/search', params={'q': '" OR * <script>'}).status_code == 200
    assert client.post('/api/v1/search/rebuild').status_code == 200


def test_collection_source_and_date_filters(web_client):
    _, _, article_id = web_client
    root = service.create_collection(name='Search test')
    service.place_article(article_id, collection_id=root['id'])
    assert search_articles('Context', collection_id=root['id'])['total'] == 1
    assert search_articles('Context', collection_id='missing')['total'] == 0
    assert search_articles('Context', platform='x')['total'] == 0
    assert search_articles('Context', after='2099-01-01')['total'] == 0


def test_explicit_rebuild_recovers_a_corrupt_index(web_client):
    from src.core.paths import runtime_home
    search_articles('Context')
    (runtime_home() / 'search.sqlite3').write_bytes(b'corrupt index')
    assert synchronize(rebuild=True)['articles'] == 1
    assert search_articles('Context')['total'] == 1


def test_permanent_deletion_marker_excludes_leftover_files(web_client):
    from src.core.content import ArticleContentStore
    _, _, article_id = web_client
    assert search_articles('Context')['total'] == 1
    ArticleContentStore().mark_deleted(article_id)
    assert search_articles('Context')['total'] == 0
