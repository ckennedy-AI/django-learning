from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from onboarding.models import Skill
from onboarding.tests.views.base import EndpointFixtures


class SkillSearchApiTests(EndpointFixtures):
    # Patched at its real location, `onboarding.views.skills`, rather than at
    # `onboarding.views`: the package __init__ re-exports API classes only, so
    # there is no `embed_texts` attribute there to replace.
    @patch("onboarding.views.skills.embed_texts")
    def test_skill_search_is_one_query(self, mock_embed_texts):
        # Matches the fixture's stored vector, so the assertion covers a
        # non-empty result. See the note in base.py on why the fixture vector is
        # not a zero vector.
        mock_embed_texts.return_value = [[0.05] * 384]
        with self.assertNumQueries(1):
            response = self.client.get(reverse("skill-search"), {"q": "orm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [self.skill.id])

    @patch("onboarding.views.skills.embed_texts")
    def test_skill_search_excludes_a_skill_that_is_not_embedded_yet(self, mock_embed_texts):
        """The visible consequence of the nullable vector column.

        A skill created through SkillCreateApi is searchable only once its task
        has run. Until then it has no distance to rank by, so the selector leaves
        it out rather than sorting a NULL into the results.
        """
        mock_embed_texts.return_value = [[0.05] * 384]
        pending = Skill.objects.create(name="Not embedded yet", description="No vector.")

        response = self.client.get(reverse("skill-search"), {"q": "orm"})

        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data}
        self.assertNotIn(pending.id, returned_ids)
        self.assertIn(self.skill.id, returned_ids)


class SkillCreateApiTests(EndpointFixtures):
    """Staff only, per the permissions table.

    The task is patched at `onboarding.services.skills`, where the service
    imported it, for the same reason the search tests patch `embed_texts` at
    `onboarding.views.skills`: a mock has to replace the reference the code under
    test actually holds.
    """

    def test_staff_can_create_a_skill_in_two_queries(self):
        self.authenticate_as(self.staff)

        with patch("onboarding.services.skills.generate_skill_embedding_task"):
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.post(
                    reverse("skill-create"),
                    {"name": "Kubernetes", "description": "Container orchestration."},
                )

        # 2 statements: full_clean's unique check on `name`, then the INSERT. The
        # enqueue is not a query.
        #
        # assertNumQueries would report 4 here and it would not be wrong.
        # TestCase already holds a transaction open, so the service's
        # transaction.atomic can only nest inside it as a SAVEPOINT / RELEASE
        # SAVEPOINT pair, and those are statements on the connection like any
        # other. They are filtered out rather than counted, because the number
        # this test is meant to protect is the endpoint's, and pinning 4 would
        # make it depend on how the test harness manages transactions rather than
        # on what the view does. This is also why the other write endpoint,
        # TaskApprovalApi, asserts no query count at all.
        statements = [
            query["sql"]
            for query in ctx.captured_queries
            if not query["sql"].startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))
        ]
        self.assertEqual(len(statements), 2, statements)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "Kubernetes")
        self.assertTrue(response.data["embedding_task_id"])
        self.assertIsNone(Skill.objects.get(id=response.data["id"]).embedding)

    def test_create_enqueues_the_embedding_task_on_commit(self):
        self.authenticate_as(self.staff)

        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("skill-create"),
                    {"name": "Terraform", "description": "Infrastructure as code."},
                )

        mock_task.apply_async.assert_called_once_with(
            args=[response.data["id"]], task_id=response.data["embedding_task_id"]
        )

    def test_non_staff_gets_403(self):
        """403 rather than 404, deliberately.

        The opposite call from TaskApprovalApi, which 404s so a manager cannot
        learn that someone else's task assignment exists. There is no row here
        whose existence needs hiding, the caller is authenticated, and "you may
        not add to the skills directory" is a rule the client should be able to
        report accurately.
        """
        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            response = self.client.post(
                reverse("skill-create"), {"name": "Nomad", "description": "Scheduling."}
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Skill.objects.filter(name="Nomad").exists())
        mock_task.apply_async.assert_not_called()

    def test_unauthenticated_gets_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse("skill-create"), {"name": "Consul", "description": "Service discovery."}
        )

        self.assertEqual(response.status_code, 401)

    def test_duplicate_name_is_400_naming_the_field(self):
        self.authenticate_as(self.staff)

        with patch("onboarding.services.skills.generate_skill_embedding_task") as mock_task:
            response = self.client.post(
                reverse("skill-create"),
                {"name": self.skill.name, "description": "Duplicate of the fixture."},
            )

        # full_clean's Django ValidationError, normalised by the single handler
        # in api/exception_handlers.py into the same envelope a serializer error
        # produces. Without full_clean this would be an IntegrityError and a 500.
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data["extra"]["fields"])
        mock_task.apply_async.assert_not_called()

    def test_missing_description_is_400(self):
        self.authenticate_as(self.staff)

        response = self.client.post(reverse("skill-create"), {"name": "Vault"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("description", response.data["extra"]["fields"])

    def test_get_is_405(self):
        self.authenticate_as(self.staff)

        response = self.client.get(reverse("skill-create"))

        self.assertEqual(response.status_code, 405)
