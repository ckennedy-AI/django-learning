from django.test import TestCase
from django.urls import reverse


class InvalidInputTests(TestCase):
    """Locks in the invalid-input policy documented in CLAUDE.md.

    The decision is 4xx rather than a safe default: a missing or malformed
    parameter is a client bug, and silently substituting a default would return
    a plausible-looking response for a question the caller did not ask. The one
    exception is a serializer field that declares a default, which is a
    documented part of the contract rather than a guess.

    Deliberately not split by sub-domain like the rest of this package, and
    deliberately not inheriting the shared fixtures. What it pins is the single
    error envelope in `api/exception_handlers.py`, which is one policy rather than
    one endpoint's behaviour, and it reaches four different endpoints to prove the
    shape is the same at each. Splitting it per endpoint would scatter one
    decision across four files. It needs no fixtures because every case here is
    rejected before a query runs.
    """

    def test_missing_required_filter_is_400_not_a_default(self):
        response = self.client.get(reverse("my-dashboard"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("user_id", response.data["extra"]["fields"])

    def test_malformed_filter_is_400(self):
        response = self.client.get(reverse("my-dashboard"), {"user_id": "not-an-integer"})

        self.assertEqual(response.status_code, 400)

    def test_limit_above_the_upper_bound_is_rejected(self):
        # The upper bound on a limit parameter is enforced, not clamped, so a
        # caller asking for 5,000 rows learns that it was refused.
        response = self.client.get(reverse("skill-search"), {"q": "orm", "limit": 5000})

        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.data["extra"]["fields"])

    def test_pagination_limit_above_max_clamps_rather_than_erroring(self):
        # DRF's own paginator clamps to max_limit instead of erroring. Noting the
        # inconsistency with the serializer-validated limit above deliberately:
        # this one is DRF's behaviour, not a choice this project made.
        response = self.client.get(reverse("module-list"), {"limit": 5000})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit"], 50)

    def test_error_responses_share_one_shape(self):
        response = self.client.get(reverse("my-dashboard"))

        self.assertIn("message", response.data)
        self.assertIn("extra", response.data)

    def test_unknown_id_is_404_in_the_same_shape(self):
        response = self.client.get(reverse("module-detail", args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertIn("message", response.data)
        self.assertIn("extra", response.data)
