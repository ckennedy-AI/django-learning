from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from onboarding.models import Skill
from onboarding.services import skill_create, skill_embedding_set


class SkillCreateTests(TestCase):
    """First test module in the services layer, hence the new package.

    These do not inherit EndpointFixtures. That fixture set exists so the view
    tests can assert exact query counts against one known database state, and a
    service test asserts behaviour rather than counts, so inheriting it would
    only couple this file to rows it never reads.

    Every test here patches the task at `onboarding.services.skills`, the module
    that imported it, rather than at `onboarding.tasks` where it is defined. The
    service holds its own reference from a module-level `from ... import`, so
    replacing the name at the definition site would leave that reference intact
    and the mock would never be consulted.
    """

    def test_creates_the_row(self):
        with patch("onboarding.services.skills.generate_skill_embedding_task"):
            skill, _ = skill_create(name="Postgres", description="Query planning and indexes.")

        skill.refresh_from_db()
        self.assertEqual(skill.name, "Postgres")
        # The whole point of the async path: the row is complete except for the
        # vector, which the worker has not written yet.
        self.assertIsNone(skill.embedding)

    def test_does_not_enqueue_before_commit(self):
        """The on_commit half of gotcha 2, from the other direction.

        Django's TestCase wraps each test in a transaction it rolls back, so
        nothing here ever commits. A bare .delay() would have fired anyway and
        this assertion would fail, which is exactly the production bug: the
        worker gets a message referring to a row no other connection can see.
        """
        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            skill_create(name="Redis", description="Caching and queues.")

            mock_task.apply_async.assert_not_called()

    def test_enqueues_once_on_commit_with_the_returned_task_id(self):
        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            # captureOnCommitCallbacks(execute=True) is the only way to see an
            # on_commit callback fire under TestCase (gotcha 5).
            with self.captureOnCommitCallbacks(execute=True):
                skill, task_id = skill_create(name="Celery", description="Background jobs.")

        mock_task.apply_async.assert_called_once_with(args=[skill.id], task_id=task_id)

    def test_enqueues_an_id_not_an_instance(self):
        """Pins gotcha 3 at the call site rather than trusting the serializer.

        CELERY_TASK_SERIALIZER = "json" would reject a Skill instance at enqueue
        time, but only against a real broker. This asserts the contract without
        one.
        """
        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            with self.captureOnCommitCallbacks(execute=True):
                skill, _ = skill_create(name="Docker", description="Containers.")

        args = mock_task.apply_async.call_args.kwargs["args"]
        self.assertEqual(args, [skill.id])
        self.assertIsInstance(args[0], int)

    def test_rejects_a_duplicate_name(self):
        Skill.objects.create(name="Django ORM", description="Existing.", embedding=[0.1] * 384)

        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            with self.assertRaises(ValidationError) as ctx:
                skill_create(name="Django ORM", description="Duplicate.")

        self.assertIn("name", ctx.exception.message_dict)
        self.assertEqual(Skill.objects.filter(name="Django ORM").count(), 1)
        # The atomic block rolled back, so on_commit never registered a callback
        # in the first place.
        mock_task.apply_async.assert_not_called()


class SkillEmbeddingSetTests(TestCase):
    def setUp(self):
        self.skill = Skill.objects.create(name="pgvector", description="Vector similarity.")

    @patch("onboarding.services.skills.embed_texts")
    def test_stores_the_vector_and_returns_a_json_safe_summary(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.5] * 384]

        result = skill_embedding_set(skill_id=self.skill.id)

        self.skill.refresh_from_db()
        self.assertEqual(len(self.skill.embedding), 384)
        # The return value goes into the result backend, so it has to survive a
        # JSON round trip.
        self.assertEqual(result, {"skill_id": self.skill.id, "dimensions": 384})

    @patch("onboarding.services.skills.embed_texts")
    def test_running_twice_leaves_the_same_vector(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.25] * 384]

        first = skill_embedding_set(skill_id=self.skill.id)
        second = skill_embedding_set(skill_id=self.skill.id)

        self.assertEqual(first, second)
        self.skill.refresh_from_db()
        self.assertEqual(list(self.skill.embedding), [0.25] * 384)

    def test_raises_for_a_missing_skill(self):
        """The DoesNotExist is deliberately uncaught, so this pins that choice.

        A swallowed exception here would turn "the task was enqueued before its
        transaction committed" into a silent no-op instead of a FAILURE in the
        worker log and the result backend.
        """
        missing_id = self.skill.id
        self.skill.delete()

        with self.assertRaises(Skill.DoesNotExist):
            skill_embedding_set(skill_id=missing_id)
