from django.test import TestCase

from onboarding.tests.factories import UserFactory


class UserGetDirectReportsTests(TestCase):
    """Direct reports are a self-referential relationship through the manager FK."""

    def test_returns_all_direct_reports_when_they_exist(self):
        manager = UserFactory()
        report1 = UserFactory(manager=manager)
        report2 = UserFactory(manager=manager)

        reports = manager.get_direct_reports()

        self.assertCountEqual(list(reports), [report1, report2])

    def test_returns_empty_when_user_has_no_direct_reports(self):
        user = UserFactory()

        reports = user.get_direct_reports()

        self.assertEqual(list(reports), [])


class UserStrTests(TestCase):
    """The string representation uses the full name when available."""

    def test_returns_full_name_when_both_first_and_last_are_set(self):
        user = UserFactory(first_name="John", last_name="Doe")

        self.assertEqual(str(user), "John Doe")

    def test_returns_first_name_only_when_last_name_is_blank(self):
        user = UserFactory(first_name="John", last_name="")

        self.assertEqual(str(user), "John")

    def test_returns_last_name_only_when_first_name_is_blank(self):
        user = UserFactory(first_name="", last_name="Doe")

        self.assertEqual(str(user), "Doe")

    def test_falls_back_to_username_when_both_names_are_blank(self):
        user = UserFactory(first_name="", last_name="", username="jdoe123")

        self.assertEqual(str(user), "jdoe123")
