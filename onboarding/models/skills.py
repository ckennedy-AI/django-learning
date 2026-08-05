from django.db import models
from pgvector.django import HnswIndex, VectorField

from onboarding.models.users import User


class Skill(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField()
    embedding = VectorField(dimensions=384)

    class Meta:
        ordering = ["name"]
        indexes = [
            HnswIndex(
                name="skill_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self) -> str:
        return self.name


class UserSkill(models.Model):
    class Proficiency(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        EXPERT = "expert", "Expert"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_skills")
    proficiency = models.CharField(
        max_length=20, choices=Proficiency.choices, default=Proficiency.BEGINNER
    )

    class Meta:
        ordering = ["user", "skill"]
        constraints = [models.UniqueConstraint(fields=["user", "skill"], name="unique_user_skill")]

    def __str__(self) -> str:
        return f"{self.user} - {self.skill}"
