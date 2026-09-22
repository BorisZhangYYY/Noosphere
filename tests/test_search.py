"""Search relevance, isolation and file reconciliation regressions."""
import json
from test_web_api import web_client
from src.core.search import search_articles, synchronize, passage
from src.application import service


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
