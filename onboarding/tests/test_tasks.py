from unittest.mock import patch

from django.test import TestCase

from onboarding.models import Skill
from onboarding.tasks import generate_skill_embedding


class GenerateSkillEmbeddingTests(TestCase):
    """Tests for `onboarding/tasks.py`.

    Flat `tests/test_tasks.py` rather than a `tests/tasks/` package, mirroring
    the layer it tests: Celery tasks are a single flat module, not one module per
    sub-domain, so a package here would be a directory holding one file forever.
    It gets promoted the same way `onboarding/tasks.py` would.

    The task is called as a plain function, with no worker, no broker, and no
    eager mode. That is the point of keeping tasks thin: `generate_skill_embedding`
    has nothing in it but an ID, a service call, and a return, so there is
    nothing here that needs Celery's machinery to exercise. Whether Celery
    actually delivers the message is a different question, answered by
    `manage.py inspect_task_result` against a running worker.
    """

    def setUp(self):
        self.skill = Skill.objects.create(name="Kombu", description="Messaging library.")

    @patch("onboarding.services.skills.embed_texts")
    def test_embeds_the_skill_and_returns_the_services_result(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.75] * 384]

        result = generate_skill_embedding(self.skill.id)

        self.skill.refresh_from_db()
        self.assertEqual(len(self.skill.embedding), 384)
        self.assertEqual(result, {"skill_id": self.skill.id, "dimensions": 384})

    @patch("onboarding.services.skills.embed_texts")
    def test_passes_the_description_to_the_embedding_provider(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.0] * 384]

        generate_skill_embedding(self.skill.id)

        # The worker reads current state by ID rather than trusting a snapshot
        # taken at enqueue time, so what gets embedded is whatever the row says
        # now.
        mock_embed_texts.assert_called_once_with(["Messaging library."])

    def test_propagates_a_missing_skill(self):
        missing_id = self.skill.id
        self.skill.delete()

        with self.assertRaises(Skill.DoesNotExist):
            generate_skill_embedding(missing_id)
