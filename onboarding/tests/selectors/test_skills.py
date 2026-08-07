from django.test import TestCase

from onboarding.selectors import skill_search
from onboarding.tests.factories import SkillFactory


class SkillSearchTests(TestCase):
    def test_returns_skills_by_cosine_distance(self):
        # Create skills with embeddings that have controlled distances.
        # Using simple vectors: [1, 0, 0, ...], [0, 1, 0, ...], etc.
        # The first query vector [1, 0, 0, ...] is closest to skill1.
        skill1 = SkillFactory(name="Skill1", embedding=[1.0] + [0.0] * 383)
        skill2 = SkillFactory(name="Skill2", embedding=[0.0] + [1.0] + [0.0] * 382)

        result = list(skill_search(embedding=[1.0] + [0.0] * 383))

        self.assertEqual(len(result), 2)
        # skill1 should be closest to the query embedding
        self.assertEqual(result[0].id, skill1.id)
        self.assertEqual(result[1].id, skill2.id)

    def test_excludes_skills_with_null_embedding(self):
        embedded_skill = SkillFactory(name="Embedded", embedding=[0.1] * 384)
        pending_skill = SkillFactory(name="Pending", embedding=None)

        result = list(skill_search(embedding=[0.1] * 384))

        result_ids = [r.id for r in result]
        self.assertIn(embedded_skill.id, result_ids)
        self.assertNotIn(pending_skill.id, result_ids)

    def test_respects_limit_parameter(self):
        SkillFactory.create_batch(5)

        result = list(skill_search(embedding=[0.1] * 384, limit=3))

        self.assertEqual(len(result), 3)

    def test_default_limit_is_10(self):
        SkillFactory.create_batch(15)

        result = list(skill_search(embedding=[0.1] * 384))

        self.assertEqual(len(result), 10)

    def test_returns_empty_when_no_embedded_skills(self):
        SkillFactory(embedding=None)
        SkillFactory(embedding=None)

        result = list(skill_search(embedding=[0.1] * 384))

        self.assertEqual(len(result), 0)

    def test_includes_skill_with_matching_embedding(self):
        query_embedding = [0.5] * 384
        skill = SkillFactory(embedding=query_embedding)

        result = list(skill_search(embedding=query_embedding))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, skill.id)
