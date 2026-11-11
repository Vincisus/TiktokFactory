import json
import os
import re

import httpx


class LLMService:
    def __init__(self):
        self.base_url = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
        self.api_key = os.getenv("LMSTUDIO_API_KEY", "lm-studio")
        self.model = os.getenv("LMSTUDIO_MODEL", "local-model")

    async def generate_text(self, prompt: str, temperature: float = 0.8):
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Sei un assistente creativo italiano specializzato in storie brevi, suspense e narrazione cinematografica.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def generate_json(self, prompt: str):
        text = await self.generate_text(prompt)
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str):
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Il modello non ha restituito JSON valido.")

        return json.loads(text[start : end + 1])
