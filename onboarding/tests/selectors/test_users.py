from django.http import Http404
from django.test import TestCase

from onboarding.selectors import user_get, user_list, user_reports_get, user_skills_list
from onboarding.tests.factories import (
    DepartmentFactory,
    SkillFactory,
    UserFactory,
    UserSkillFactory,
)


class UserGetTests(TestCase):
    def test_returns_user_with_related_objects(self):
        department = DepartmentFactory()
        manager = UserFactory(department=department)
        user = UserFactory(department=department, manager=manager)

        result = user_get(user_id=user.id)

        self.assertEqual(result.id, user.id)
        self.assertEqual(result.department.id, department.id)
        self.assertEqual(result.manager.id, manager.id)

    def test_is_one_query_with_select_related(self):
        department = DepartmentFactory()
        manager = UserFactory(department=department)
        user = UserFactory(department=department, manager=manager)

        with self.assertNumQueries(1):
            result = user_get(user_id=user.id)
            # Touch the related objects to ensure they're loaded
            _ = result.department.id
            _ = result.manager.id

    def test_raises_http404_for_unknown_id(self):
        with self.assertRaises(Http404):
            user_get(user_id=99999)


class UserListTests(TestCase):
    def test_returns_all_users_unfiltered(self):
        UserFactory.create_batch(3)

        result = list(user_list())

        self.assertEqual(len(result), 3)

    def test_returns_flattened_values_with_annotations(self):
        department = DepartmentFactory(name="Engineering")
        manager = UserFactory(first_name="Morgan", last_name="Reyes", department=department)
        UserFactory(
            username="alice",
            first_name="Alice",
            last_name="Smith",
            department=department,
            manager=manager,
        )

        result = list(user_list())

        row = next(r for r in result if r["username"] == "alice")
        self.assertEqual(row["name"], "Alice Smith")
        self.assertEqual(row["manager_name"], "Morgan Reyes")
        self.assertEqual(row["department_name"], "Engineering")

    def test_manager_name_blank_when_no_manager(self):
        user = UserFactory(first_name="Bob", last_name="Jones", manager=None)

        result = list(user_list())

        row = next(r for r in result if r["username"] == user.username)
        self.assertEqual(row["name"], "Bob Jones")
        self.assertEqual(row["manager_name"], "")

    def test_filters_by_exact_username(self):
        UserFactory(username="alice")
        UserFactory(username="bob")

        result = list(user_list(filters={"username": "alice"}))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["username"], "alice")

    def test_username_filter_is_exact_not_partial(self):
        UserFactory(username="alice")

        result = list(user_list(filters={"username": "alic"}))

        self.assertEqual(len(result), 0)

    def test_returns_expected_columns(self):
        UserFactory()

        result = list(user_list())

        row = result[0]
        self.assertIn("id", row)
        self.assertIn("username", row)
        self.assertIn("name", row)
        self.assertIn("email", row)
        self.assertIn("is_staff", row)
        self.assertIn("is_active", row)
        self.assertIn("manager_name", row)
        self.assertIn("department_name", row)


class UserSkillsListTests(TestCase):
    def test_returns_only_that_user_skills(self):
        user1 = UserFactory()
        user2 = UserFactory()
        skill1 = SkillFactory()
        skill2 = SkillFactory()

        UserSkillFactory(user=user1, skill=skill1)
        UserSkillFactory(user=user1, skill=skill2)
        UserSkillFactory(user=user2, skill=skill1)

        result = list(user_skills_list(user_id=user1.id))

        self.assertEqual(len(result), 2)
        result_skill_ids = [r.skill.id for r in result]
        self.assertIn(skill1.id, result_skill_ids)
        self.assertIn(skill2.id, result_skill_ids)

    def test_is_two_queries_with_select_related(self):
        user = UserFactory()
        skill1 = SkillFactory()
        skill2 = SkillFactory()
        UserSkillFactory(user=user, skill=skill1)
        UserSkillFactory(user=user, skill=skill2)

        with self.assertNumQueries(1):
            list(user_skills_list(user_id=user.id))

    def test_returns_empty_for_user_with_no_skills(self):
        user = UserFactory()

        result = list(user_skills_list(user_id=user.id))

        self.assertEqual(len(result), 0)

    def test_skill_object_accessible_without_extra_query(self):
        user = UserFactory()
        skill = SkillFactory(name="Django", description="Web framework")
        UserSkillFactory(user=user, skill=skill)

        with self.assertNumQueries(1):
            user_skills = list(user_skills_list(user_id=user.id))
            # Access the related skill to ensure select_related worked
            _ = user_skills[0].skill.name


class UserReportsGetTests(TestCase):
    def test_returns_user_with_manager_and_direct_reports(self):
        department = DepartmentFactory()
        manager = UserFactory(department=department)
        report1 = UserFactory(department=department, manager=manager)
        report2 = UserFactory(department=department, manager=manager)

        result = user_reports_get(user_id=manager.id)

        self.assertEqual(result.id, manager.id)
        direct_report_ids = [r.id for r in result.direct_reports.all()]
        self.assertEqual(len(direct_report_ids), 2)
        self.assertIn(report1.id, direct_report_ids)
        self.assertIn(report2.id, direct_report_ids)

    def test_is_two_queries(self):
        manager = UserFactory()
        UserFactory(manager=manager)
        UserFactory(manager=manager)

        with self.assertNumQueries(2):
            user_reports_get(user_id=manager.id)

    def test_works_for_user_with_no_direct_reports(self):
        user = UserFactory()

        result = user_reports_get(user_id=user.id)

        self.assertEqual(result.id, user.id)
        self.assertEqual(list(result.direct_reports.all()), [])

    def test_returns_user_with_manager(self):
        manager = UserFactory()
        user = UserFactory(manager=manager)

        result = user_reports_get(user_id=user.id)

        self.assertEqual(result.manager.id, manager.id)

    def test_raises_http404_for_unknown_id(self):
        with self.assertRaises(Http404):
            user_reports_get(user_id=99999)
