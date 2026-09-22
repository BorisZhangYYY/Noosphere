"""HTTP adapters for library search and batch processing."""
import asyncio
from starlette.responses import JSONResponse
from src.core.search import search_articles, synchronize


async def search(request):
    p = request.query_params
    try:
        result = await asyncio.to_thread(search_articles, p.get('q', ''), scope=p.get('scope', 'all'), collection_id=p.get('collection', ''), platform=p.get('platform', ''), after=p.get('after', ''), before=p.get('before', ''), offset=int(p.get('offset', '0')), limit=int(p.get('limit', '30')), locale=p.get('locale', 'en-US'))
        return JSONResponse(result)
    except (ValueError, TypeError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)


async def rebuild_search(request):
    return JSONResponse(await asyncio.to_thread(synchronize, rebuild=True))


async def search_passage(request):
    from src.core.search import passage
    p = request.query_params
    try:
        return JSONResponse(await asyncio.to_thread(passage, p.get('article', ''), p.get('field', ''), p.get('digest', ''), int(p.get('start', '0'))))
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)


async def batches(request):
    from src.application import batches as service
    try:
        if request.method == 'GET':
            return JSONResponse({'batches': list(reversed(list(service.jobs.values())))})
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Provide a batch object')
        if request.url.path.endswith('/preview'):
            return JSONResponse({'items': await asyncio.to_thread(service.preflight, payload.get('urls'))})
        job = service.create_batch(payload.get('urls'), mode=payload.get('mode', 'capture'), perspective=payload.get('perspective'), language=payload.get('language', 'source'), collection_id=payload.get('collectionId', ''))
        return JSONResponse(job, status_code=202)
    except (ValueError, TypeError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)


async def batch_action(request):
    from src.application import batches as service
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Provide an action object')
        return JSONResponse(service.control_batch(request.path_params['batch_id'], payload.get('action', ''), payload.get('itemIds')))
    except (ValueError, TypeError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
