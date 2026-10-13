import base64
import json

import pytest

from src.core.config.config import load_config
from src.core.review.image_filter import analyze_images, _parse_image_analysis
from src.core.review.output_contract import ReviewPayload, render_review_payload
from src.graph.graph import run_ai_review_graph
from src.integrations.ai_client import AIClient, AITextResponse, resolve_ai_settings


@pytest.fixture
def workspace():
    config = load_config()
    config.checkpoint.backend = 'memory'
    config.ai.image_provider = 'vision'
    config.ai_providers['vision'] = config.ai_providers['test'].model_copy(update={'model': 'vision-model', 'vision_capable': True})
    folder = config.output_dir_path / 'article'
    assets = folder / 'assets'
    assets.mkdir(parents=True)
    for name in ('diagram', 'promotion'):
        (assets / f'{name}.png').write_bytes(name.encode())
    body = ('## Evidence\n\nThe detailed explanation is complete.\n\n'
            '![Diagram](assets/diagram.png)\n\n![Promotion](assets/promotion.png)\n\n'
            '## Result\n\nThe measured result is 42.\n')
    draft = render_review_payload(ReviewPayload('Article', body, 'The explanation and result'),
                                  '# Article\n\n> Source: https://example.com/article\n> Platform: Web\n> Author: Ada\n> Type: article\n\n---\n')
    (folder / 'raw.md').write_text(draft)
    (folder / 'reviewed.md').write_text(draft)
    manifest = {'schema_version': 1, 'article_id': 'article',
                'article': {'url': 'https://example.com/article', 'title': 'Article', 'platform': 'web',
                            'platform_label': 'Web', 'author': 'Ada', 'content_type': 'article'},
                'paths': {'raw': 'raw.md', 'reviewed': 'reviewed.md', 'assets': 'assets', 'manifest': 'manifest.json'},
                'assets': {'downloaded': [], 'failed': {}}}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    return folder, draft, body


def vision_response(name):
    return json.dumps({'classification': 'REMOVE' if name == 'promotion' else 'RELEVANT',
                       'description': f'Visible {name}', 'function': 'Engagement solicitation' if name == 'promotion' else 'Explains the evidence'})


def install_models(monkeypatch, body, final_plan, calls, vision_hook=None):
    async def text(self, system, user):
        assert self.settings.model == 'test-model'
        if '# Final image coordination protocol' in system:
            calls.append(('layout', json.loads(user)))
            if isinstance(final_plan, Exception):
                raise final_plan
            return AITextResponse(text=json.dumps(final_plan(json.loads(user))), model='test-model', provider='test')
        calls.append(('text', user))
        return AITextResponse(text=json.dumps({'title': 'Article', 'markdown': body, 'summary': 'INTERNAL ARTICLE SUMMARY'}), model='test-model', provider='test')

    async def vision(self, system, content):
        assert self.settings.model == 'vision-model'
        assert 'INTERNAL ARTICLE SUMMARY' in system
        assert 'The measured result' not in system
        name = base64.b64decode(content[0]['source']['data']).decode()
        calls.append(('vision', name))
        if vision_hook:
            vision_hook(name)
        return AITextResponse(text=vision_response(name), model='vision-model', provider='vision')

    monkeypatch.setattr(AIClient, 'generate_text', text)
    monkeypatch.setattr(AIClient, 'generate_vision', vision)


def keep_all(context):
    return {'images': [{'id': image['id'], 'action': 'keep'} for image in context['images']], 'text_edits': []}


@pytest.mark.asyncio
async def test_text_then_vision_then_text_soft_removes_and_moves_without_rewriting(monkeypatch, workspace):
    folder, raw, body = workspace
    calls = []

    def plan(context):
        assert context['summary'] == 'INTERNAL ARTICLE SUMMARY'
        assert context['images'][0]['description'] == 'Visible diagram'
        assert context['images'][0]['function'] == 'Explains the evidence'
        target = next(block['id'] for block in context['blocks'] if block['text'].startswith('The measured result'))
        return {'images': [
            {'id': 'image_001', 'action': 'move', 'target': target, 'reason': 'Supports result'},
            {'id': 'image_002', 'action': 'remove', 'reason': 'Unrelated solicitation'},
        ], 'text_edits': []}

    install_models(monkeypatch, body, plan, calls)
    result = await run_ai_review_graph(folder / 'reviewed.md')
    assert result.ok
    assert [kind for kind, _ in calls] == ['text', 'vision', 'vision', 'layout']
    final = (folder / 'reviewed.md').read_text()
    assert final.index('The measured result is 42.') < final.index('assets/diagram.png')
    assert 'The detailed explanation is complete.' in final
    assert 'assets/promotion.png' not in final
    assert (folder / 'removed/promotion.png').read_bytes() == b'promotion'
    assert (folder / 'raw.md').read_text() == raw
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['image_filter']['promotion_images'] == ['assets/promotion.png']
    assert manifest['image_filter']['image_functions']['assets/diagram.png'] == 'Explains the evidence'
    report = json.loads((folder / 'review.json').read_text())
    assert report['image_layout']['status'] == 'completed'
    assert report['summary'] == 'INTERNAL ARTICLE SUMMARY'
    from src.core.activity import ArticleActivityStore
    assert ArticleActivityStore().summary('article')['reviewCount'] == 1
    from src.application.service import set_article_image_state
    set_article_image_state('article', 'promotion.png', 'active')
    assert (folder / 'assets/promotion.png').is_file()
    assert 'assets/promotion.png' in (folder / 'reviewed.md').read_text()
    assert (folder / 'raw.md').read_text() == raw


@pytest.mark.asyncio
async def test_vision_removal_is_advisory_and_noop_keeps_draft_bytes(monkeypatch, workspace):
    folder, raw, body = workspace
    calls = []
    install_models(monkeypatch, body, keep_all, calls)
    await run_ai_review_graph(folder / 'reviewed.md')
    assert (folder / 'reviewed.md').read_text() == raw
    assert (folder / 'assets/promotion.png').is_file()
    assert not (folder / 'removed/promotion.png').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['provider', 'invalid_plan'])
async def test_last_stage_failure_preserves_first_draft_and_all_images(monkeypatch, workspace, failure):
    folder, raw, body = workspace
    calls = []
    final = RuntimeError('Text API unavailable') if failure == 'provider' else lambda context: {'images': []}
    install_models(monkeypatch, body, final, calls)
    await run_ai_review_graph(folder / 'reviewed.md')
    assert (folder / 'reviewed.md').read_text() == raw
    assert (folder / 'assets/promotion.png').is_file()
    assert not (folder / 'removed/promotion.png').exists()
    assert json.loads((folder / 'review.json').read_text())['image_layout']['status'] == 'preserved'


@pytest.mark.asyncio
async def test_nonvision_text_model_works_without_image_provider(monkeypatch, workspace):
    folder, raw, body = workspace
    load_config().ai.image_provider = None
    calls = []
    install_models(monkeypatch, body, keep_all, calls)
    await run_ai_review_graph(folder / 'reviewed.md')
    assert [kind for kind, _ in calls] == ['text', 'layout']
    assert all(image['vision_failed'] for image in calls[-1][1]['images'])
    assert (folder / 'reviewed.md').read_text() == raw


@pytest.mark.asyncio
async def test_unavailable_vision_cannot_trigger_removal(monkeypatch, workspace):
    folder, raw, body = workspace
    calls = []

    def failed_vision(_):
        raise RuntimeError('Vision unavailable')

    def plan(context):
        plan = keep_all(context)
        plan['images'][0].update(action='remove', reason='Unsupported guess')
        return plan

    install_models(monkeypatch, body, plan, calls, failed_vision)
    await run_ai_review_graph(folder / 'reviewed.md')
    assert (folder / 'reviewed.md').read_text() == raw
    assert (folder / 'assets/diagram.png').is_file()
    assert len(json.loads((folder / 'manifest.json').read_text())['image_filter']['failed_images']) == 2


@pytest.mark.asyncio
async def test_concurrent_edit_during_vision_is_not_overwritten_or_soft_removed(monkeypatch, workspace):
    from src.core.workspace import RevisionConflict
    folder, raw, body = workspace
    calls = []
    user_draft = raw + '\nUser saved a new paragraph.\n'

    def changed(_):
        (folder / 'reviewed.md').write_text(user_draft)

    def plan(context):
        plan = keep_all(context)
        plan['images'][1].update(action='remove', reason='Unrelated promotion')
        return plan

    install_models(monkeypatch, body, plan, calls, changed)
    with pytest.raises(RevisionConflict):
        await run_ai_review_graph(folder / 'reviewed.md')
    assert (folder / 'reviewed.md').read_text() == user_draft
    assert (folder / 'assets/promotion.png').is_file()
    assert (folder / 'raw.md').read_text() == raw


@pytest.mark.asyncio
async def test_rereview_starts_from_current_draft_and_preserves_manual_removal(monkeypatch, workspace):
    folder, raw, body = workspace
    (folder / 'removed').mkdir()
    (folder / 'assets/promotion.png').rename(folder / 'removed/promotion.png')
    body = body.replace('![Promotion](assets/promotion.png)', '').replace('42', '43')
    current = render_review_payload(ReviewPayload('Article', body, 'Summary'), raw)
    (folder / 'reviewed.md').write_text(current)
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['image_filter'] = {'manual_removed_images': ['assets/promotion.png'], 'removed_files': ['removed/promotion.png']}
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    calls = []
    install_models(monkeypatch, body, keep_all, calls)
    await run_ai_review_graph(folder / 'reviewed.md')
    assert '43' in calls[0][1]
    assert 'assets/promotion.png' not in calls[0][1]
    assert (folder / 'removed/promotion.png').is_file()
    assert json.loads((folder / 'manifest.json').read_text())['image_filter']['manual_removed_images'] == ['assets/promotion.png']


@pytest.mark.asyncio
async def test_vision_cache_depends_on_summary_prompt_and_model(monkeypatch, workspace):
    folder, _, _ = workspace
    client = AIClient(resolve_ai_settings(load_config(), 'vision'))
    calls = []

    async def vision(self, system, content):
        calls.append(system)
        return AITextResponse(text=vision_response('diagram'), model=self.settings.model, provider='vision')

    monkeypatch.setattr(AIClient, 'generate_vision', vision)
    args = dict(markdown='![Diagram](assets/diagram.png)', article_title='Title', assets_dir=folder / 'assets', client=client)
    first = await analyze_images(**args, article_summary='Summary A', image_review_prompt='Prompt A {summary}')
    await analyze_images(**args, article_summary='Summary A', image_review_prompt='Prompt A {summary}')
    await analyze_images(**args, article_summary='Summary B', image_review_prompt='Prompt A {summary}')
    await analyze_images(**args, article_summary='Summary B', image_review_prompt='Prompt B {summary}')
    assert len(calls) == 3
    assert first.image_functions['assets/diagram.png'] == 'Explains the evidence'


@pytest.mark.parametrize('response', ['RELEVANT because unclear', '{}', '{"classification":"REMOVE","description":"x"}', 'not JSON'])
def test_invalid_vision_response_is_not_a_removal_judgment(response):
    with pytest.raises(ValueError):
        _parse_image_analysis(response)
