import asyncio
import json
import logging
import os
import shutil
import sys

import httpx
from app.services.llm_service import LLMService


async def main():
    logging.basicConfig(level=logging.INFO)
    service = LLMService()
    print('Server locale:', service.base_url)
    print('Modello configurato:', service.model)
    print('FFmpeg nel PATH:', bool(shutil.which('ffmpeg')))
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(service.base_url + '/models', headers={'Authorization': 'Bearer ' + service.api_key})
        response.raise_for_status()
        print('Identificatori restituiti:', [m.get('id') for m in response.json().get('data', [])])
    os.environ['LMSTUDIO_TOTAL_TIMEOUT'] = '180'
    os.environ['LMSTUDIO_MAX_TOKENS'] = '1024'
    result = await service.generate_json('Sei un revisore. Test tecnico del formato: restituisci esattamente {"ok":true,"issues":[]}. Nessun altro testo.')
    if result != {'ok': True, 'issues': []}:
        raise RuntimeError('Schema valido ma risultato del test inatteso: ' + json.dumps(result))
    print('OK: test JSON strutturato superato. Questo non collauda voce, rendering o qualita narrativa.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
