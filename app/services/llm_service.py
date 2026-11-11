import asyncio
import json
import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv

logger = logging.getLogger('uvicorn.error')


class LLMService:
    def __init__(self):
        load_dotenv()
        self.base_url = os.getenv('LMSTUDIO_BASE_URL', 'http://127.0.0.1:1234/v1').rstrip('/')
        self.api_key = os.getenv('LMSTUDIO_API_KEY', 'lm-studio')
        self.model = os.getenv('LMSTUDIO_MODEL', 'local-model')

    async def generate_text(self, prompt: str, temperature: float = 0.8):
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': 'Rispondi in italiano. Fornisci solo il risultato richiesto, senza analisi, ragionamenti o commenti editoriali.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': temperature,
            'max_tokens': int(os.getenv('LMSTUDIO_MAX_TOKENS', '4096')),
            'stream': True,
        }
        started = time.monotonic()
        content = []
        finish_reason = None
        events = 0
        last_log = started
        timeout = httpx.Timeout(connect=15, read=180, write=30, pool=30)
        logger.info('LM Studio: avvio richiesta al modello %s', self.model)
        try:
            async with asyncio.timeout(float(os.getenv('LMSTUDIO_TOTAL_TIMEOUT', '1800'))):
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        'POST', f'{self.base_url}/chat/completions',
                        headers={'Authorization': f'Bearer {self.api_key}'}, json=payload,
                    ) as response:
                        if response.is_error:
                            body = (await response.aread()).decode('utf-8', errors='replace')
                            raise RuntimeError(f'LM Studio HTTP {response.status_code}: {body[:1200]}')
                        async for line in response.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            raw = line[5:].strip()
                            if raw == '[DONE]':
                                break
                            if not raw:
                                continue
                            event = json.loads(raw)
                            if event.get('error'):
                                raise RuntimeError(f'LM Studio: {event["error"]}')
                            choices = event.get('choices', [])
                            if not choices:
                                continue
                            choice = choices[0]
                            delta = choice.get('delta') or {}
                            piece = delta.get('content')
                            if isinstance(piece, str):
                                content.append(piece)
                            events += 1
                            finish_reason = choice.get('finish_reason') or finish_reason
                            now = time.monotonic()
                            if now - last_log >= 15:
                                logger.info('LM Studio attivo: %.0fs, %d eventi, %d caratteri di risposta', now - started, events, sum(map(len, content)))
                                last_log = now
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RuntimeError(
                f'{type(exc).__name__}: LM Studio non ha completato la risposta dopo {time.monotonic() - started:.0f}s. '
                'Controlla i log del modello. Limite totale predefinito 1800s; limite senza dati 180s.'
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f'{type(exc).__name__}: impossibile comunicare con {self.base_url}: {exc!r}') from exc
        text = self._clean_text(''.join(content))
        if finish_reason == 'length':
            raise RuntimeError('Risposta interrotta al limite token. Ridurre il blocco richiesto o configurare LMSTUDIO_MAX_TOKENS; il risultato incompleto non viene usato.')
        if not text:
            raise RuntimeError('LM Studio ha restituito una risposta vuota o solo ragionamento. Verificare modello e impostazioni di generazione.')
        if finish_reason not in ('stop',):
            raise RuntimeError(f'Risposta non completata normalmente: finish_reason={finish_reason!r}. Nessun risultato parziale utilizzato.')
        logger.info('LM Studio: risposta completata in %.0fs', time.monotonic() - started)
        return text

    async def generate_json(self, prompt: str):
        text = await self.generate_text(prompt)
        return self._extract_json(text)

    @staticmethod
    def _clean_text(text: str):
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    @staticmethod
    def _extract_json(text: str):
        text = LLMService._clean_text(text)
        fenced = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        start = text.find('{')
        if start < 0:
            raise ValueError('Il modello non ha restituito un oggetto JSON. Nessun risultato utilizzato.')
        try:
            value, end = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f'JSON del modello non valido: riga {exc.lineno}, colonna {exc.colno}: {exc.msg}') from exc
        if not isinstance(value, dict):
            raise ValueError('Era richiesto un oggetto JSON.')
        return value
