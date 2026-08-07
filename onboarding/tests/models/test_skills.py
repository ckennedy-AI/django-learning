from django.db import IntegrityError, transaction
from django.test import TestCase

from onboarding.tests.factories import SkillFactory, UserFactory, UserSkillFactory


class UserSkillUniquenessTests(TestCase):
    """The constraint on (user, skill) prevents duplicate proficiency records."""

    def test_a_duplicate_user_skill_pair_raises_integrity_error(self):
        user = UserFactory()
        skill = SkillFactory()
        UserSkillFactory(user=user, skill=skill)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserSkillFactory(user=user, skill=skill)

    def test_the_same_user_with_a_different_skill_succeeds(self):
        user = UserFactory()
        skill1 = SkillFactory()
        skill2 = SkillFactory()
        UserSkillFactory(user=user, skill=skill1)

        user_skill = UserSkillFactory(user=user, skill=skill2)

        self.assertIsNotNone(user_skill.id)

    def test_a_different_user_with_the_same_skill_succeeds(self):
        user1 = UserFactory()
        user2 = UserFactory()
        skill = SkillFactory()
        UserSkillFactory(user=user1, skill=skill)

        user_skill = UserSkillFactory(user=user2, skill=skill)

        self.assertIsNotNone(user_skill.id)
