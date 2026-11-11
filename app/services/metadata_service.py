import json

from app.services.llm_service import LLMService


class MetadataService:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def generate_metadata(self, concept: dict, structure: dict):
        prompt = f"""
Sei un social media manager italiano.

Genera metadati per questo video.

Concept:
{json.dumps(concept, ensure_ascii=False, indent=2)}

Struttura:
{json.dumps(structure, ensure_ascii=False, indent=2)}

Restituisci SOLO JSON valido con:
title, description, tags, tiktok_caption, hashtags, thumbnail_text.

La descrizione deve dichiarare che la storia è fictional/drammatizzata.
"""
        return await self.llm.generate_json(prompt)
