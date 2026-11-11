import json


class MetadataService:
    def __init__(self, llm):
        self.llm = llm

    async def generate_metadata(self, concept, structure):
        data = await self.llm.generate_json(
            "Sei un social media manager italiano. Genera metadati JSON con title, title_options "
            "(cinque titoli italiani differenti, massimo 100 caratteri ciascuno), description, tags, "
            "tiktok_caption, hashtags, thumbnail_text. Non inventare eventi. La descrizione deve "
            "dichiarare che la storia e fiction/drammatizzata. Concept: " + json.dumps(concept, ensure_ascii=False) + ". Piano: " + json.dumps(structure, ensure_ascii=False)
        )
        titles = data.get("title_options")
        if not isinstance(titles, list) or len(titles) != 5 or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 100 for x in titles) or len({x.strip().casefold() for x in titles}) != 5:
            base = str(concept.get("title") or "Una scelta difficile").strip()[:65]
            titles = [base, base + " — La mia versione", base + " — Quello che non sapevo", base + " — La scelta finale", base + " — Fiducia e conseguenze"]
            data["title_options_source"] = "template_fallback"
        data["title_options"] = [x.strip() for x in titles]
        return data
