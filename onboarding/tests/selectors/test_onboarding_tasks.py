from django.http import Http404
from django.test import TestCase

from onboarding.selectors import task_assignment_get_for_manager
from onboarding.tests.factories import TaskAssignmentFactory, UserFactory


class TaskAssignmentGetForManagerTests(TestCase):
    def test_returns_assignment_when_manager_matches(self):
        manager = UserFactory()
        assignee = UserFactory(manager=manager)
        assignment = TaskAssignmentFactory(assignee=assignee)

        result = task_assignment_get_for_manager(
            task_assignment_id=assignment.id, manager_id=manager.id
        )

        self.assertEqual(result.id, assignment.id)
        self.assertEqual(result.assignee.id, assignee.id)

    def test_raises_http404_when_assignee_belongs_to_different_manager(self):
        manager1 = UserFactory()
        manager2 = UserFactory()
        assignee = UserFactory(manager=manager1)
        assignment = TaskAssignmentFactory(assignee=assignee)

        with self.assertRaises(Http404):
            task_assignment_get_for_manager(
                task_assignment_id=assignment.id, manager_id=manager2.id
            )

    def test_raises_http404_for_nonexistent_assignment_id(self):
        manager = UserFactory()

        with self.assertRaises(Http404):
            task_assignment_get_for_manager(task_assignment_id=99999, manager_id=manager.id)

    def test_includes_assignee_in_select_related(self):
        manager = UserFactory()
        assignee = UserFactory(manager=manager)
        assignment = TaskAssignmentFactory(assignee=assignee)

        with self.assertNumQueries(1):
            result = task_assignment_get_for_manager(
                task_assignment_id=assignment.id, manager_id=manager.id
            )
            # Access the related assignee to ensure select_related worked
            _ = result.assignee.id
