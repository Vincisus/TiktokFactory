import unittest

from app.core.story_brain import StoryBrain, validate_parts, validate_card, word_count


class NarrativeValidationTests(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count('Anna chiama Paolo.'), 3)

    def test_part_count(self):
        with self.assertRaises(ValueError):
            validate_parts({'parts': []}, 4)

    def test_unknown_character(self):
        with self.assertRaises(ValueError):
            validate_card({'scene_id': 1, 'pov_id': 'unknown'}, ['anna'], 1)

    def test_valid_card(self):
        card = {'scene_id': 1, 'pov_id': 'anna', 'location': 'casa', 'characters_present': ['anna'], 'facts': ['Legge un messaggio'], 'knowledge_before': ['Crede al marito'], 'knowledge_after': ['Scopre la bugia'], 'withhold': []}
        self.assertIs(validate_card(card, ['anna'], 1), card)

    def test_invalid_project_id(self):
        with self.assertRaises(ValueError):
            StoryBrain.folder({'id': '../outside'})


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_contradictory_review(self):
        class FakeLLM:
            async def generate_json(self, prompt):
                return {'ok': True, 'issues': ['contraddizione']}
        with self.assertRaises(ValueError):
            await StoryBrain(FakeLLM()).review({}, 'test')


if __name__ == '__main__':
    unittest.main()
