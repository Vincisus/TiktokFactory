import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("uvicorn.error")
S = {"type": "string", "minLength": 1}
L = {"type": "array", "items": S}


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


REVIEW = obj({"ok": {"type": "boolean"}, "issues": {"type": "array", "maxItems": 5, "items": {"type": "string", "minLength": 1, "maxLength": 240}}})
CHARACTER = obj({k: S for k in ("id", "name", "role", "appearance")})
CONCEPT = obj({**{k: S for k in ("title", "logline", "conflict", "turning_point", "resolution", "moral", "setting", "visual_style")}, "characters": {"type": "array", "minItems": 2, "maxItems": 5, "items": CHARACTER}})
PART = obj({"part": {"type": "integer", "minimum": 1}, "title": S, "summary": S, "cliffhanger": S})
CARD = obj({"scene_id": {"type": "integer", "minimum": 1}, "part": {"type": "integer", "minimum": 1}, "pov_id": S, "location": S, "characters_present": L, "facts": L, "knowledge_before": L, "knowledge_after": L, "withhold": L, "visual": S})


def schema_for(prompt):
    if prompt.startswith("Sei un revisore."):
        return REVIEW
    if prompt.startswith("Crea una storia originale di fiction"):
        return CONCEPT
    if prompt.startswith("Pianifica "):
        match = re.match(r"Pianifica (\d+)", prompt)
        count = int(match.group(1)) if match else 4
        return obj({"parts": {"type": "array", "minItems": count, "maxItems": count, "items": PART}})
    if prompt.startswith("Genera la scheda della scena"):
        return CARD
    return {"type": "object"}


def validate(value, schema, path="$ "):
    kind = schema.get("type")
    checks = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list), "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int, "boolean": lambda: type(value) is bool}
    if kind in checks and not checks[kind]():
        raise ValueError(f"{path}: atteso {kind}")
    if kind == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: manca {key}")
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise ValueError(f"{path}: campi non previsti")
        for key in value.keys() & props.keys():
            validate(value[key], props[key], f"{path}.{key}")
    if kind in ("array", "string"):
        lo, hi = ("minItems", "maxItems") if kind == "array" else ("minLength", "maxLength")
        if len(value) < schema.get(lo, 0) or len(value) > schema.get(hi, float("inf")):
            raise ValueError(f"{path}: lunghezza non valida")
    if kind == "array":
        for i, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{i}]")
    if kind == "integer" and value < schema.get("minimum", float("-inf")):
        raise ValueError(f"{path}: valore troppo piccolo")
    return value


class LLMService:
    def __init__(self, transport=None):
        load_dotenv()
        self.base_url = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        if urlparse(self.base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Solo server LLM locali su loopback sono consentiti.")
        self.api_key = os.getenv("LMSTUDIO_API_KEY", "lm-studio")
        self.model = os.getenv("LMSTUDIO_MODEL", "local-model")
        self.transport = transport
        self.diagnostic_dir = Path(os.getenv("LLM_DIAGNOSTIC_DIR", "projects/_diagnostics"))

    async def generate_text(self, prompt, temperature=0.8):
        return await self._request(prompt, temperature)

    async def _request(self, prompt, temperature, schema=None):
        call_id = uuid.uuid4().hex
        self.diagnostic_dir.mkdir(parents=True, exist_ok=True)
        diagnostic = self.diagnostic_dir / f"{call_id}.json"
        content = []
        finish = None
        reasoning_chars = 0
        started = time.monotonic()
        last = started
        error = None
        payload = {"model": self.model, "messages": [{"role": "system", "content": "Rispondi in italiano. Fornisci solo il risultato finale richiesto, senza commenti editoriali."}, {"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": int(os.getenv("LMSTUDIO_MAX_TOKENS", "4096")), "stream": True}
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "factory_response", "strict": True, "schema": schema}}
        logger.info("LM Studio: richiesta %s (%s)", call_id, "JSON vincolato" if schema else "testo")
        try:
            timeout = httpx.Timeout(connect=15, read=float(os.getenv("LMSTUDIO_IDLE_TIMEOUT", "300")), write=30, pool=30)
            async with asyncio.timeout(float(os.getenv("LMSTUDIO_TOTAL_TIMEOUT", "1800"))):
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                    async with client.stream("POST", f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json=payload) as response:
                        if response.is_error:
                            body = (await response.aread()).decode(errors="replace")
                            raise RuntimeError(f"HTTP {response.status_code}: {body[:800]}. Non viene effettuato fallback a JSON libero.")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if raw == "[DONE]":
                                break
                            if not raw:
                                continue
                            event = json.loads(raw)
                            if event.get("error"):
                                raise RuntimeError(str(event["error"]))
                            for choice in event.get("choices", []):
                                delta = choice.get("delta") or {}
                                piece = delta.get("content")
                                if isinstance(piece, str):
                                    content.append(piece)
                                reasoning_chars += len(delta.get("reasoning_content") or "")
                                finish = choice.get("finish_reason") or finish
                            now = time.monotonic()
                            if now - last >= 15:
                                logger.info("LM Studio %s: %.0fs, %d caratteri finali, %d caratteri reasoning", call_id[:8], now-started, sum(map(len, content)), reasoning_chars)
                                last = now
            if finish == "length":
                raise RuntimeError("Limite token raggiunto: risposta incompleta, non utilizzata.")
            if finish != "stop":
                raise RuntimeError(f"Risposta non completata: finish_reason={finish!r}")
            text = self._clean_text("".join(content))
            if not text:
                raise RuntimeError("Risposta finale vuota; eventuale reasoning non viene usato come copione.")
            return text
        except (TimeoutError, httpx.TimeoutException) as exc:
            error = f"{type(exc).__name__}: scaduto tempo di attesa"
            raise RuntimeError(f"{error}. Diagnostica: {diagnostic}") from exc
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"{error}. Diagnostica: {diagnostic}") from exc
        finally:
            diagnostic.write_text(json.dumps({"model": self.model, "response": "".join(content), "finish_reason": finish, "reasoning_characters": reasoning_chars, "elapsed_seconds": round(time.monotonic()-started, 2), "error": error, "structured": schema is not None}, ensure_ascii=False, indent=2), encoding="utf-8")

    async def generate_json(self, prompt):
        schema = schema_for(prompt)
        original = prompt
        last_error = None
        for attempt in range(2):
            text = await self._request(prompt, 0.2, schema)
            try:
                return validate(self._extract_json(text), schema)
            except ValueError as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning("JSON non valido: un solo tentativo di correzione: %s", exc)
                    prompt = f"Correggi solo il formato JSON, senza cambiare i fatti. Errore: {exc}. Richiesta originale: {original}. Risposta da correggere: {text}"
        raise ValueError(f"JSON non valido anche dopo una correzione: {last_error}. Risposte salvate in {self.diagnostic_dir}")

    @staticmethod
    def _clean_text(text):
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _extract_json(text):
        text = LLMService._clean_text(text)
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        start = text.find("{")
        if start < 0:
            raise ValueError("Il modello non ha restituito un oggetto JSON.")
        try:
            value, end = json.JSONDecoder().raw_decode(text[start:])
            if text[start+end:].strip():
                raise ValueError("Testo inatteso dopo l'oggetto JSON.")
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON del modello non valido: riga {exc.lineno}, colonna {exc.colno}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("Era richiesto un oggetto JSON.")
        return value
