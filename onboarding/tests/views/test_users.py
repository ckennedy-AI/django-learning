from django.urls import reverse

from onboarding.models import Skill, UserSkill
from onboarding.tests.views.base import EndpointFixtures


class UserListApiTests(EndpointFixtures):
    def test_user_list_is_two_queries(self):
        # One COUNT from the paginator, one page query with the department and
        # manager joins folded into the same query via F() lookups, so this
        # does not grow with the number of users. See selectors/users.py.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_user_list_flattens_manager_and_department(self):
        self.manager.first_name = "Morgan"
        self.manager.last_name = "Reyes"
        self.manager.save(update_fields=["first_name", "last_name"])

        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-list"))
        employee = next(row for row in response.data["results"] if row["username"] == "employee")
        self.assertEqual(employee["department_name"], self.department.name)
        self.assertEqual(employee["manager_name"], "Morgan Reyes")

    def test_user_list_manager_name_blank_when_no_manager(self):
        # The fixture manager has no manager of their own, but does have a
        # department, so this isolates the null-FK case to manager_name only.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-list"))
        top_level = next(row for row in response.data["results"] if row["username"] == "manager")
        self.assertEqual(top_level["manager_name"], "")
        self.assertEqual(top_level["department_name"], self.department.name)

    def test_user_list_filters_by_exact_username(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-list"), {"username": "employee"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "employee")

    def test_user_list_username_filter_is_exact_not_partial(self):
        # Only 1 query, not 2: LimitOffsetPagination short-circuits on a zero
        # COUNT and returns an empty page without a second query for it.
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-list"), {"username": "employ"})
        self.assertEqual(response.data["count"], 0)


class UserDetailApiTests(EndpointFixtures):
    def test_user_detail_is_one_query(self):
        # setUp authenticates as self.user, viewing their own record: self,
        # so the full serializer.
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-detail", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.data)

    def test_user_detail_is_trimmed_for_a_non_staff_non_self_caller(self):
        # self.user viewing their manager's record: neither self nor staff.
        response = self.client.get(reverse("user-detail", args=[self.manager.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("email", response.data)
        self.assertNotIn("is_active", response.data)
        self.assertNotIn("date_joined", response.data)
        self.assertIn("department", response.data)
        self.assertIn("manager", response.data)

    def test_user_detail_is_full_for_staff_viewing_anyone(self):
        self.authenticate_as(self.staff)

        response = self.client.get(reverse("user-detail", args=[self.user.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.data)


class UserSkillsApiTests(EndpointFixtures):
    def test_user_skills_is_two_queries(self):
        # One COUNT from the paginator, one page query with the skill joined in.
        # The number that matters is that it does not grow with the number of
        # skills, which is what select_related buys. See
        # `manage.py benchmark_user_skills` for the measured comparison.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-skills", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_user_skills_query_count_does_not_grow_with_skills(self):
        # The N+1 guard. Adding skills must not add queries, otherwise the
        # select_related in the selector has been lost.
        for index in range(5):
            skill = Skill.objects.create(
                name=f"Skill {index}", description="Extra.", embedding=[0.0] * 384
            )
            UserSkill.objects.create(user=self.user, skill=skill)

        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-skills", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 6)


class UserReportsApiTests(EndpointFixtures):
    def test_user_reports_is_two_queries(self):
        # select_related("manager") and prefetch_related("direct_reports") can't
        # collapse into one query, a JOIN can't flatten a reverse FK into a list.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-reports", args=[self.manager.id]))
        self.assertEqual(response.status_code, 200)
