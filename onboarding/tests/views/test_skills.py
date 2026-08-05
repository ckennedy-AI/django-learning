from unittest.mock import patch

from django.urls import reverse

from onboarding.tests.views.base import EndpointFixtures


class SkillSearchApiTests(EndpointFixtures):
    # Patched at its real location, `onboarding.views.skills`, rather than at
    # `onboarding.views`: the package __init__ re-exports API classes only, so
    # there is no `embed_texts` attribute there to replace.
    @patch("onboarding.views.skills.embed_texts")
    def test_skill_search_is_one_query(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.0] * 384]
        with self.assertNumQueries(1):
            response = self.client.get(reverse("skill-search"), {"q": "orm"})
        self.assertEqual(response.status_code, 200)
