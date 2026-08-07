from django.core.exceptions import PermissionDenied
from django.test import TestCase

from onboarding.selectors import activity_event_list
from onboarding.tests.factories import ActivityEventFactory, UserFactory


class ActivityEventListTests(TestCase):
    def test_returns_requesting_user_events_without_filter(self):
        user = UserFactory()
        other_user = UserFactory()

        ActivityEventFactory(user=user, event_type="login")
        ActivityEventFactory(user=other_user, event_type="logout")

        result = list(activity_event_list(requesting_user=user))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user.id, user.id)

    def test_returns_requesting_user_events_when_user_id_is_self(self):
        user = UserFactory()
        other_user = UserFactory()

        ActivityEventFactory(user=user, event_type="login")
        ActivityEventFactory(user=other_user, event_type="logout")

        result = list(activity_event_list(requesting_user=user, filters={"user_id": user.id}))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user.id, user.id)

    def test_manager_can_view_direct_report_events(self):
        manager = UserFactory()
        report = UserFactory(manager=manager)
        other_user = UserFactory()

        ActivityEventFactory(user=report, event_type="login")
        ActivityEventFactory(user=other_user, event_type="logout")

        result = list(activity_event_list(requesting_user=manager, filters={"user_id": report.id}))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user.id, report.id)

    def test_manager_raises_permission_denied_for_unrelated_user(self):
        manager = UserFactory()
        other_manager = UserFactory()
        unrelated = UserFactory(manager=other_manager)

        with self.assertRaises(PermissionDenied):
            activity_event_list(requesting_user=manager, filters={"user_id": unrelated.id})

    def test_staff_can_view_any_user_events(self):
        staff = UserFactory(is_staff=True)
        target_user = UserFactory()

        ActivityEventFactory(user=target_user, event_type="login")

        result = list(
            activity_event_list(requesting_user=staff, filters={"user_id": target_user.id})
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user.id, target_user.id)

    def test_filters_by_event_type(self):
        user = UserFactory()

        ActivityEventFactory(user=user, event_type="login")
        ActivityEventFactory(user=user, event_type="logout")
        ActivityEventFactory(user=user, event_type="page_view")

        result = list(activity_event_list(requesting_user=user, filters={"event_type": "login"}))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].event_type, "login")

    def test_combines_user_id_and_event_type_filters(self):
        user1 = UserFactory()
        user2 = UserFactory()

        ActivityEventFactory(user=user1, event_type="login")
        ActivityEventFactory(user=user1, event_type="logout")
        ActivityEventFactory(user=user2, event_type="login")

        result = list(
            activity_event_list(
                requesting_user=user1, filters={"user_id": user1.id, "event_type": "login"}
            )
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].event_type, "login")
        self.assertEqual(result[0].user.id, user1.id)

    def test_staff_can_filter_by_event_type_on_any_user(self):
        staff = UserFactory(is_staff=True)
        target_user = UserFactory()

        ActivityEventFactory(user=target_user, event_type="login")
        ActivityEventFactory(user=target_user, event_type="logout")

        result = list(
            activity_event_list(
                requesting_user=staff,
                filters={"user_id": target_user.id, "event_type": "logout"},
            )
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].event_type, "logout")

    def test_returns_empty_when_no_matching_events(self):
        user = UserFactory()

        result = list(
            activity_event_list(requesting_user=user, filters={"event_type": "nonexistent"})
        )

        self.assertEqual(len(result), 0)
