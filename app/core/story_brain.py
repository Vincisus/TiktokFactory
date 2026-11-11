import json
import re

from app.services.llm_service import LLMService


class StoryBrain:
    def __init__(self, llm: LLMService):
        self.llm = llm

    async def generate_concept(self, brief: dict):
        prompt = f"""
Sei un showrunner di storie brevi per TikTok e YouTube.

Crea un concept originale in italiano per una storia autoconclusiva.

Tema richiesto: {brief['series']}
Durata target: {brief['duration_minutes']} minuti
Numero clip TikTok: {brief['tiktok_clips']}

Restituisci SOLO JSON valido con queste chiavi:
title, logline, genre, protagonist, antagonist, setting, conflict,
turning_point, resolution, moral, visual_style, target_audience.
"""
        return await self.llm.generate_json(prompt)

    async def generate_structure(self, concept: dict, brief: dict):
        prompt = f"""
Sei uno story architect per video narrativi.

Crea una struttura per una storia da {brief['duration_minutes']} minuti,
divisa in {brief['tiktok_clips']} parti TikTok.

Concept:
{json.dumps(concept, ensure_ascii=False, indent=2)}

Restituisci SOLO JSON valido con questa struttura:
{{
  "parts": [
    {{
      "part": 1,
      "title": "...",
      "duration_seconds": 180,
      "summary": "...",
      "cliffhanger": "...",
      "emotional_beat": "..."
    }}
  ]
}}

Ogni parte deve avere un mini-arco completo e un cliffhanger.
"""
        return await self.llm.generate_json(prompt)

    async def generate_script(self, concept: dict, structure: dict, brief: dict):
        parts = structure.get("parts", [])
        script_sections = []

        for part in parts:
            prompt = f"""
Sei uno scrittore di storie brevi in prima persona.

Scrivi la parte {part.get('part')} della storia, in italiano naturale,
per un video di circa {round(part.get('duration_seconds', 180) / 60, 1)} minuti.

Concept:
{json.dumps(concept, ensure_ascii=False, indent=2)}

Struttura della parte:
{json.dumps(part, ensure_ascii=False, indent=2)}

Parti precedenti:
{chr(10).join(script_sections[-1:]) if script_sections else 'Nessuna'}

Regole:
- Usa frasi brevi e concrete
- Inserisci una rivelazione ogni 20-40 secondi
- Non spiegare troppo
- Termina con questo cliffhanger: {part.get('cliffhanger', '')}
- Non usare titoli, intestazioni o commenti

Restituisci solo il testo narrato.
"""
            section = await self.llm.generate_text(prompt)
            script_sections.append(section.strip())

        return "\n\n".join(script_sections)

    async def generate_storyboard(self, script: str, structure: dict, brief: dict):
        prompt = f"""
Sei un regista e montatore per video verticali.

Trasforma questo script in uno storyboard JSON per un video da {brief['duration_minutes']} minuti.

Script:
{script}

Struttura:
{json.dumps(structure, ensure_ascii=False, indent=2)}

Per ogni scena crea:
scene_id, part, start, end, narration, visual, camera,
on_screen_text, sound, emotion, image_prompt.

Regole:
- start e end devono essere numeri in secondi
- Le scene devono coprire tutta la durata
- Ogni scena dura idealmente 6-12 secondi
- image_prompt deve essere in inglese, dettagliato e coerente
- Non aggiungere fatti non presenti nello script

Restituisci SOLO JSON valido con questa struttura:
{{"scenes": []}}
"""
        return await self.llm.generate_json(prompt)
